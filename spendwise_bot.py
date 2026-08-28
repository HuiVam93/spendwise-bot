import asyncio
import logging
import sqlite3
import html
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import WebAppInfo

# ==================== НАСТРОЙКИ ====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8684510280:AAFfAbSAebKszpdI1S_EkTqbpu4XjwHQ88U")

# ==================== БАЗА ДАННЫХ ====================
DB_NAME = "spendwise.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        created_at TEXT
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS envelopes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        name TEXT,
        icon TEXT DEFAULT "📁",
        budget INTEGER,
        created_at TEXT
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        envelope_id INTEGER,
        amount INTEGER,
        note TEXT DEFAULT "",
        created_at TEXT
    )''')
    
    conn.commit()
    conn.close()

def get_conn():
    return sqlite3.connect(DB_NAME)

# ==================== УТИЛИТЫ ====================
def fmt_money(value):
    """Форматирует число с пробелами: 15000 → 15 000"""
    return f"{value:,}".replace(",", " ")

def make_progress_bar(spent, budget, length=10):
    if budget <= 0:
        return "⬜" * length
    ratio = spent / budget
    filled = int(ratio * length)
    if filled > length:
        filled = length
    empty = length - filled
    
    if ratio < 0.5:
        block = "🟩"
    elif ratio < 0.8:
        block = "🟨"
    elif ratio < 1.0:
        block = "🟧"
    else:
        block = "🟥"
    
    return block * filled + "⬜" * empty

# ==================== КЛАВИАТУРЫ ====================
WEBAPP_URL = "https://HuiVam93.github.io/spendwise-bot/webapp/index.html"

main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📱 Открыть приложение", web_app=WebAppInfo(url=WEBAPP_URL))],
        [KeyboardButton(text="📊 Мои конверты"), KeyboardButton(text="➕ Добавить трату")],
        [KeyboardButton(text="🆕 Новый конверт"), KeyboardButton(text="💳 Дашборд")],
        [KeyboardButton(text="↩️ Отменить трату"), KeyboardButton(text="📈 Статистика")]
    ],
    resize_keyboard=True
)

# ==================== ЛОГИКА ====================
logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username
    
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, username, created_at) VALUES (?, ?, ?)",
              (user_id, username, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    
    await message.answer(
        f"👋 Привет, {html.escape(message.from_user.first_name or 'друг')}!\n\n"
        f"Я <b>SpendWise</b> — бот для метода конвертов.\n"
        f"Раздели деньги по категориям и трать осознанно.\n\n"
        f"Быстрый старт:\n"
        f"1. Нажми <b>🆕 Новый конверт</b>\n"
        f"2. Напиши: <code>Продукты 15000</code>\n"
        f"3. Нажми <b>➕ Добавить трату</b>\n\n"
        f"Погнали! 💰",
        reply_markup=main_kb
    )

@dp.message(F.text == "🆕 Новый конверт")
async def new_envelope_prompt(message: types.Message):
    await message.answer(
        "✏️ Напиши название конверта и бюджет через пробел:\n\n"
        "<code>Продукты 15000</code>\n"
        "<code>Кафе 4000</code>\n"
        "<code>🥕 Продукты 15000</code> — с иконкой",
        parse_mode=ParseMode.HTML
    )

@dp.message(F.text.regexp(r"^(.+?)\s+(\d+)$"))
async def create_envelope(message: types.Message):
    user_id = message.from_user.id
    parts = message.text.strip().split()
    
    if len(parts) < 2:
        return
    
    budget = int(parts[-1])
    name_parts = parts[:-1]
    
    if budget <= 0:
        await message.answer("❌ Бюджет должен быть больше 0")
        return
    
    if len(name_parts) >= 2 and len(name_parts[0]) <= 3:
        icon = name_parts[0]
        name = " ".join(name_parts[1:])
    else:
        icon = "📁"
        name = " ".join(name_parts)
    
    safe_name = html.escape(name)
    
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO envelopes (user_id, name, icon, budget, created_at) VALUES (?, ?, ?, ?, ?)",
              (user_id, safe_name, icon, budget, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    
    await message.answer(
        f"✅ Конверт создан!\n\n"
        f"{icon} <b>{safe_name}</b>\n"
        f"💵 Бюджет: <code>{fmt_money(budget)} ₽</code>",
        reply_markup=main_kb
    )

@dp.message(F.text == "📊 Мои конверты")
async def show_envelopes(message: types.Message):
    user_id = message.from_user.id
    
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, name, icon, budget FROM envelopes WHERE user_id = ?", (user_id,))
    envelopes = c.fetchall()
    
    if not envelopes:
        await message.answer("У тебя пока нет конвертов. Нажми 🆕 Новый конверт", reply_markup=main_kb)
        conn.close()
        return
    
    text = "📂 <b>Твои конверты:</b>\n\n"
    
    for env_id, name, icon, budget in envelopes:
        c.execute("SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE envelope_id = ?", (env_id,))
        spent = c.fetchone()[0]
        remaining = budget - spent
        
        bar = make_progress_bar(spent, budget)
        
        if remaining < 0:
            status = f"⚠️ превышение на {fmt_money(abs(remaining))} ₽"
        elif remaining == 0:
            status = "✅ лимит исчерпан"
        else:
            status = f"осталось {fmt_money(remaining)} ₽"
        
        c.execute("SELECT COUNT(*) FROM transactions WHERE envelope_id = ?", (env_id,))
        operations = c.fetchone()[0]
        
        safe_name = html.escape(name)
        
        text += (
            f"{icon} <b>{safe_name}</b>\n"
            f"<code>{fmt_money(spent)}</code> ₽ / <code>{fmt_money(budget)}</code> ₽ · {status}\n"
            f"{bar}\n"
            f"<i>{operations} операций</i>\n\n"
        )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🗑 Удалить {html.escape(name[:15])}", callback_data=f"del_{env_id}")]
        for env_id, name, icon, budget in envelopes
    ])
    
    conn.close()
    await message.answer(text, reply_markup=kb)

@dp.callback_query(F.data.startswith("del_"))
async def delete_envelope(callback: types.CallbackQuery):
    envelope_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    
    conn = get_conn()
    c = conn.cursor()
    
    c.execute("SELECT name, icon FROM envelopes WHERE id = ? AND user_id = ?", (envelope_id, user_id))
    row = c.fetchone()
    
    if not row:
        await callback.answer("Конверт не найден")
        conn.close()
        return
    
    name, icon = row
    
    c.execute("DELETE FROM transactions WHERE envelope_id = ?", (envelope_id,))
    c.execute("DELETE FROM envelopes WHERE id = ?", (envelope_id,))
    conn.commit()
    conn.close()
    
    await callback.message.edit_text(
        f"🗑 Конверт удалён:\n{icon} <b>{html.escape(name)}</b>\n\nНажми 📊 Мои конверты, чтобы обновить список."
    )
    await callback.answer("Удалено")

@dp.message(F.text == "➕ Добавить трату")
async def add_expense_prompt(message: types.Message):
    user_id = message.from_user.id
    
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, name, icon FROM envelopes WHERE user_id = ?", (user_id,))
    envelopes = c.fetchall()
    conn.close()
    
    if not envelopes:
        await message.answer("Сначала создай конверт через 🆕 Новый конверт", reply_markup=main_kb)
        return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{icon} {html.escape(name)}", callback_data=f"spend_{env_id}")]
        for env_id, name, icon in envelopes
    ])
    
    await message.answer("Выбери конверт:", reply_markup=kb)

user_pending = {}

@dp.callback_query(F.data.startswith("spend_"))
async def choose_envelope(callback: types.CallbackQuery):
    envelope_id = int(callback.data.split("_")[1])
    
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT name, icon FROM envelopes WHERE id = ?", (envelope_id,))
    row = c.fetchone()
    conn.close()
    
    if not row:
        await callback.answer("Конверт не найден")
        return
    
    name, icon = row
    safe_name = html.escape(name)
    
    await callback.message.answer(
        f"Выбран: {icon} <b>{safe_name}</b>\n"
        f"Напиши сумму траты (можно с комментарием):\n\n"
        f"<code>500</code>\n"
        f"<code>450 кафе с друзьями</code>",
        parse_mode=ParseMode.HTML
    )
    
    user_pending[callback.from_user.id] = envelope_id
    await callback.answer()

@dp.message(F.text.regexp(r"^(\d+)(?:\s+(.+))?$"))
async def process_expense(message: types.Message):
    user_id = message.from_user.id
    
    if user_id not in user_pending:
        await message.answer("Сначала выбери конверт через ➕ Добавить трату", reply_markup=main_kb)
        return
    
    envelope_id = user_pending[user_id]
    parts = message.text.strip().split(maxsplit=1)
    amount = int(parts[0])
    note = parts[1] if len(parts) > 1 else ""
    
    safe_note = html.escape(note)
    
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO transactions (envelope_id, amount, note, created_at) VALUES (?, ?, ?, ?)",
              (envelope_id, amount, note, datetime.now().isoformat()))
    
    c.execute("SELECT name, icon, budget FROM envelopes WHERE id = ?", (envelope_id,))
    name, icon, budget = c.fetchone()
    
    c.execute("SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE envelope_id = ?", (envelope_id,))
    spent = c.fetchone()[0]
    remaining = budget - spent
    
    conn.commit()
    conn.close()
    
    del user_pending[user_id]
    
    safe_name = html.escape(name)
    
    if remaining < 0:
        status = f"⚠️ превышение на {fmt_money(abs(remaining))} ₽"
    elif remaining == 0:
        status = "✅ лимит исчерпан"
    else:
        status = f"осталось {fmt_money(remaining)} ₽"
    
    note_text = f" ({safe_note})" if safe_note else ""
    
    await message.answer(
        f"✅ Трата записана!\n\n"
        f"{icon} <b>{safe_name}</b>\n"
        f"− <code>{fmt_money(amount)}</code> ₽{note_text}\n"
        f"Итого: <code>{fmt_money(spent)}</code> / <code>{fmt_money(budget)}</code> ₽\n"
        f"{status}",
        reply_markup=main_kb
    )

@dp.message(F.text == "↩️ Отменить трату")
async def undo_last(message: types.Message):
    user_id = message.from_user.id
    conn = get_conn()
    c = conn.cursor()
    
    c.execute('''SELECT t.id, t.amount, t.envelope_id, e.name, e.icon 
                 FROM transactions t
                 JOIN envelopes e ON t.envelope_id = e.id
                 WHERE e.user_id = ?
                 ORDER BY t.created_at DESC
                 LIMIT 1''', (user_id,))
    
    row = c.fetchone()
    if not row:
        await message.answer("Нет трат для отмены.", reply_markup=main_kb)
        conn.close()
        return
    
    trans_id, amount, env_id, env_name, icon = row
    
    c.execute("DELETE FROM transactions WHERE id = ?", (trans_id,))
    conn.commit()
    conn.close()
    
    await message.answer(
        f"↩️ Трата отменена!\n\n"
        f"{icon} <b>{html.escape(env_name)}</b>\n"
        f"Возвращено: <code>{fmt_money(amount)}</code> ₽",
        reply_markup=main_kb
    )

@dp.message(F.text == "💳 Дашборд")
async def show_dashboard(message: types.Message):
    user_id = message.from_user.id
    
    conn = get_conn()
    c = conn.cursor()
    
    c.execute("SELECT COALESCE(SUM(budget), 0) FROM envelopes WHERE user_id = ?", (user_id,))
    total_budget = c.fetchone()[0]
    
    c.execute('''SELECT COALESCE(SUM(t.amount), 0) 
                 FROM transactions t
                 JOIN envelopes e ON t.envelope_id = e.id
                 WHERE e.user_id = ?''', (user_id,))
    total_spent = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM envelopes WHERE user_id = ?", (user_id,))
    env_count = c.fetchone()[0]
    
    c.execute('''SELECT COUNT(*) FROM transactions t
                 JOIN envelopes e ON t.envelope_id = e.id
                 WHERE e.user_id = ?''', (user_id,))
    trans_count = c.fetchone()[0]
    
    conn.close()
    
    remaining = total_budget - total_spent
    
    if remaining < 0:
        status = f"⚠️ Перерасход: {fmt_money(abs(remaining))} ₽"
    else:
        status = f"💰 Осталось: {fmt_money(remaining)} ₽"
    
    await message.answer(
        f"┌─────────────────────┐\n"
        f"│  💳 <b>ДАШБОРД</b>          │\n"
        f"├─────────────────────┤\n"
        f"│                     │\n"
        f"│  📥 <b>БЮДЖЕТ</b>          │\n"
        f"│  <code>{fmt_money(total_budget)}</code> ₽          │\n"
        f"│                     │\n"
        f"│  📤 <b>ПОТРАЧЕНО</b>       │\n"
        f"│  <code>{fmt_money(total_spent)}</code> ₽          │\n"
        f"│                     │\n"
        f"│  {status}       │\n"
        f"│                     │\n"
        f"│  📁 Конвертов: {env_count}      │\n"
        f"│  📝 Операций: {trans_count}      │\n"
        f"└─────────────────────┘",
        reply_markup=main_kb
    )

@dp.message(F.text == "📈 Статистика")
async def show_stats(message: types.Message):
    await show_dashboard(message)

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "📖 <b>Команды:</b>\n\n"
        "/start — Начать\n"
        "/help — Помощь\n\n"
        "<b>Кнопки:</b>\n"
        "🆕 Новый конверт — создать категорию\n"
        "➕ Добавить трату — записать расход\n"
        "📊 Мои конверты — список с прогресс-барами\n"
        "🗑 Удалить — кнопка под списком конвертов\n"
        "↩️ Отменить трату — отмена последней операции\n"
        "💳 Дашборд — общая сводка\n\n"
        "<b>Форматы:</b>\n"
        "<code>Продукты 15000</code> — создать конверт\n"
        "<code>🥕 Продукты 15000</code> — с иконкой\n"
        "<code>500 кафе</code> — добавить трату",
        parse_mode=ParseMode.HTML,
        reply_markup=main_kb
    )

# ==================== ЗАПУСК ====================
async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
