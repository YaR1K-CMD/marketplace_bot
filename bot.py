import os
import logging
import aiohttp
from aiogram import Bot, Dispatcher, types, executor
from aiogram.types import ParseMode, InlineKeyboardMarkup, InlineKeyboardButton
from bs4 import BeautifulSoup
import urllib.parse
import json
from fastapi import FastAPI
import threading
import os

app = FastAPI()

@app.get("/health")
async def health():
    return {"status": "ok"}

def run_health_server():
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

# Запускаем FastAPI в отдельном потоке, чтобы основной бот не блокировался
threading.Thread(target=run_health_server, daemon=True).start()
# 1) Получаем токен бота из переменной окружения
#    Либо прямо вставьте строку: "123456:ABC-DEF..."
TELEGRAM_TOKEN = os.getenv("7953525862:AAGDiMFPLa0SMfnEApFwfYGnYZmwVEsXIkg") or "7953525862:AAGDiMFPLa0SMfnEApFwfYGnYZmwVEsXIkg"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TELEGRAM_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher(bot)

HEADERS = {'User-Agent': 'Mozilla/5.0'}

# 2) Задайте свой Telegram user_id (integer), чтобы получать доступ к /stats
ADMINS = [6052622344]  
USERS_LOG = set()

# Поиск на Wildberries
async def search_wildberries(query: str):
    url = (
        'https://search.wb.ru/exactmatch/ru/common/v4/search?'
        f'appType=1&query={urllib.parse.quote(query)}&curr=rub&sort=price_asc'
    )
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=HEADERS) as resp:
            data = await resp.json()
    prods = data.get('data', {}).get('products', [])[:20]
    return [{
        'name': p['name'],
        'price': p['salePriceU'] / 100,
        'link': f"https://www.wildberries.ru/catalog/{p['id']}/detail.aspx",
        'source': 'Wildberries'
    } for p in prods]

# Поиск на Ozon
async def search_ozon(query: str):
    url = f"https://www.ozon.ru/search/?text={urllib.parse.quote(query)}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=HEADERS) as resp:
            html = await resp.text()
    soup = BeautifulSoup(html, "lxml")
    items = []
    for tag in soup.select('a[href^="/product/"]')[:20]:
        name = tag.text.strip()
        href = tag['href']
        price_tag = tag.find_next("span")
        if name and price_tag:
            price_text = ''.join(filter(str.isdigit, price_tag.text))
            if price_text:
                items.append({
                    'name': name,
                    'price': float(price_text),
                    'link': f"https://www.ozon.ru{href}",
                    'source': 'Ozon'
                })
    return items

# Поиск на Яндекс.Маркете
async def search_yandex_market(query: str):
    url = f"https://market.yandex.ru/search?text={urllib.parse.quote(query)}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=HEADERS) as resp:
            html = await resp.text()
    soup = BeautifulSoup(html, "lxml")
    items = []
    for link in soup.select('a._1f4y6')[:20]:
        name = link.get('title')
        href = link.get('href')
        price_tag = link.find_next("span", {"data-auto": "price-value"})
        if name and price_tag and href:
            price = ''.join(filter(str.isdigit, price_tag.text))
            if price:
                items.append({
                    'name': name,
                    'price': float(price),
                    'link': f"https://market.yandex.ru{href}",
                    'source': 'Яндекс.Маркет'
                })
    return items

# Агрегируем и сортируем
async def aggregate_results(query: str):
    import asyncio
    results = await asyncio.gather(
        search_wildberries(query),
        search_ozon(query),
        search_yandex_market(query)
    )
    all_items = [it for sub in results for it in sub if it.get("price")]
    all_items.sort(key=lambda x: x['price'])
    if len(all_items) < 5:
        return all_items
    step = max(len(all_items) // 5, 1)
    return [all_items[i] for i in range(0, len(all_items), step)][:5]

# Команда /start и /help
@dp.message_handler(commands=['start', 'help'])
async def start(message: types.Message):
    await message.answer(
        "Привет! Я Имперский работник — бот для поиска товаров на Wildberries, Ozon и Яндекс.Маркете.\n\n"
        "Напиши название товара, и я найду для тебя лучшие предложения 🔎"
    )

# Команда /stats для админов
@dp.message_handler(commands=['stats'])
async def stats(message: types.Message):
    if message.from_user.id not in ADMINS:
        return
    await message.answer(f"Всего пользователей: {len(USERS_LOG)}")

# Обработка любого текста — поиск
@dp.message_handler()
async def search_handler(message: types.Message):
    USERS_LOG.add(message.from_user.id)
    query = message.text.strip()
    await message.answer("поиск🔎")
    results = await aggregate_results(query)
    if not results:
        await message.answer("Ничего не найдено.")
        return

    await message.answer("найдено:")
    for item in results:
        # Кнопка «Купить»
        kb = InlineKeyboardMarkup().add(
            InlineKeyboardButton(f"🛒 Купить на {item['source']}", url=item['link'])
        )
        await message.answer(
            f"<b>{item['name']}</b>\nЦена: {item['price']} ₽",
            reply_markup=kb,
            disable_web_page_preview=True
        )

# Запуск бота
if __name__ == '__main__':
    from aiogram import executor
    executor .start_polling(dp, skip_updates=True)
from aiogram import executor

async def on_startup(dp):
    # Снимаем webhook и сбрасываем старые апдейты
    await bot.delete_webhook(drop_pending_updates=True)

if _name_ == '_main_':
    # Передаем on_startup в polling
    executor.start_polling(
        dp,
        skip_updates=True,
        on_startup=on_startup
    )
