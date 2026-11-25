import asyncio
import hashlib
import hmac
import json
import os
import time
from contextlib import asynccontextmanager
from urllib.parse import parse_qsl

import aiosqlite
import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse

load_dotenv()

# === НАСТРОЙКИ ===
BOT_TOKEN = os.getenv("BOT_TOKEN", "9118390399:AAEF-AqbDxsl0sRTNZB2yzkHXmW3ksWMAtY")
ADMIN_ID = int(os.getenv("ADMIN_ID", "9130081170"))  # Твой Telegram ID для логов
WEBAPP_URL = os.getenv("WEBAPP_URL", "")
PORT = int(os.getenv("PORT", "8000"))
DB_PATH = "tapper.db"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# === БАЗА ДАННЫХ ===
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                coins INTEGER DEFAULT 0,
                energy INTEGER DEFAULT 1000,
                max_energy INTEGER DEFAULT 1000,
                multitap INTEGER DEFAULT 1,
                profit_per_hour INTEGER DEFAULT 0,
                last_update INTEGER DEFAULT 0
            )
        """)
        await db.commit()


async def get_or_create_user(user_id: int, username: str = "", first_name: str = "Игрок"):
    now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()

        if not row:
            await db.execute(
                """INSERT INTO users (user_id, username, first_name, coins, energy, max_energy, multitap, profit_per_hour, last_update)
                   VALUES (?, ?, ?, 0, 1000, 1000, 1, 0, ?)""",
                (user_id, username, first_name, now),
            )
            await db.commit()
            cur = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = await cur.fetchone()
            return dict(row), True

        user = dict(row)
        elapsed = max(0, now - user["last_update"])

        # Восстановление энергии (2 ед/сек) и пассивный доход в час
        regen_energy = min(user["max_energy"], user["energy"] + elapsed * 2)
        passive_coins = int((user["profit_per_hour"] / 3600) * min(elapsed, 10800))  # макс 3 часа оффлайн

        if regen_energy != user["energy"] or passive_coins > 0 or username != user["username"]:
            new_coins = user["coins"] + passive_coins
            await db.execute(
                """UPDATE users SET coins = ?, energy = ?, username = ?, first_name = ?, last_update = ?
                   WHERE user_id = ?""",
                (new_coins, regen_energy, username or user["username"], first_name or user["first_name"], now, user_id),
            )
            await db.commit()
            user["coins"] = new_coins
            user["energy"] = regen_energy
            user["last_update"] = now

        return user, False


# === ПРОВЕРКА ПОДПИСИ TELEGRAM MINI APP ===
def verify_telegram_init_data(init_data: str) -> dict:
    if not init_data:
        raise HTTPException(status_code=401, detail="No initData")

    parsed = dict(parse_qsl(init_data, strict_parsing=True))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise HTTPException(status_code=401, detail="No hash")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(calculated_hash, received_hash):
        raise HTTPException(status_code=403, detail="Invalid initData signature")

    user_json = json.loads(parsed.get("user", "{}"))
    return user_json


# === ЛОГИКА TELEGRAM БОТА ===
async def send_admin_log(text: str):
    if not ADMIN_ID:
        return
    try:
        await bot.send_message(chat_id=ADMIN_ID, text=text, parse_mode="HTML")
    except Exception as e:
        print(f"Ошибка отправки лога: {e}")


@dp.message(CommandStart())
async def cmd_start(message: Message):
    u = message.from_user
    _, is_new = await get_or_create_user(u.id, u.username or "", u.first_name or "Игрок")

    if is_new:
        await send_admin_log(
            f"🆕 <b>Новый игрок зашёл в бота</b>\n"
            f"Имя: {u.full_name}\n"
            f"Юзернейм: @{u.username or 'нет'}\n"
            f"ID: <code>{u.id}</code>"
        )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Играть в Tap Combat", web_app=WebAppInfo(url=WEBAPP_URL))]
        ]
    )
    await message.answer(
        f"Привет, <b>{u.first_name}</b>!\n\n"
        "Тапай по монете, качай прибыль в час и обгоняй других в топе.\n"
        "Жми кнопку ниже, чтобы запустить игру 👇",
        reply_markup=kb,
        parse_mode="HTML",
    )


@dp.message(Command("top"))
async def cmd_top(message: Message):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT first_name, coins, profit_per_hour FROM users ORDER BY coins DESC LIMIT 10")
        rows = await cur.fetchall()

    if not rows:
        return await message.answer("Пока никого нет в рейтинге.")

    lines = ["🏆 <b>Топ-10 тапальщиков:</b>\n"]
    for idx, (name, coins, pph) in enumerate(rows, 1):
        lines.append(f"{idx}. <b>{name}</b> — {coins:,} 🪙 (+{pph:,}/ч)")
    await message.answer("\n".join(lines), parse_mode="HTML")


# === ЗАПУСК БОТА И FASTAPI В ОДНОМ ПРОЦЕССЕ ===
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    polling_task = asyncio.create_task(dp.start_polling(bot))
    await send_admin_log("🟢 <b>Сервер и Mini App успешно запущены на Bothost!</b>")
    yield
    polling_task.cancel()
    await bot.session.close()


app = FastAPI(lifespan=lifespan)


# === API ДЛЯ MINI APP ===
@app.get("/", response_class=HTMLResponse)
async def serve_index():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()


@app.post("/api/sync")
async def api_sync(request: Request, x_init_data: str = Header(default="")):
    tg_user = verify_telegram_init_data(x_init_data)
    user_id = int(tg_user["id"])
    username = tg_user.get("username", "")
    first_name = tg_user.get("first_name", "Игрок")

    user, is_new = await get_or_create_user(user_id, username, first_name)
    body = await request.json()
    taps = int(body.get("taps", 0))

    if is_new:
        await send_admin_log(
            f"📲 <b>Открыл Mini App (новый юзер)</b>\n"
            f"Игрок: {first_name} (@{username or 'нет'})\n"
            f"ID: <code>{user_id}</code>"
        )

    if taps > 0:
        # Защита от накрутки: максимум 35 тапов за один пакет
        safe_taps = min(taps, 35)
        energy_cost = safe_taps * user["multitap"]
        actual_energy = min(user["energy"], energy_cost)
        earned = actual_energy

        if earned > 0:
            user["coins"] += earned
            user["energy"] -= actual_energy
            now = int(time.time())
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "UPDATE users SET coins = ?, energy = ?, last_update = ? WHERE user_id = ?",
                    (user["coins"], user["energy"], now, user_id),
                )
                await db.commit()

    return {"ok": True, "user": user}


@app.post("/api/upgrade")
async def api_upgrade(request: Request, x_init_data: str = Header(default="")):
    tg_user = verify_telegram_init_data(x_init_data)
    user_id = int(tg_user["id"])
    user, _ = await get_or_create_user(user_id)

    body = await request.json()
    upgrade_type = body.get("type")

    if upgrade_type == "multitap":
        cost = user["multitap"] * 250
        if user["coins"] < cost:
            return {"ok": False, "error": "Не хватает монет"}
        user["coins"] -= cost
        user["multitap"] += 1
        log_msg = f"⚡ <b>Апгрейд Multitap</b> до ур. {user['multitap']}"

    elif upgrade_type == "energy":
        level = (user["max_energy"] - 1000) // 500 + 1
        cost = level * 300
        if user["coins"] < cost:
            return {"ok": False, "error": "Не хватает монет"}
        user["coins"] -= cost
        user["max_energy"] += 500
        user["energy"] = user["max_energy"]
        log_msg = f"🔋 <b>Апгрейд Энергии</b> до {user['max_energy']}"

    elif upgrade_type == "mining":
        level = user["profit_per_hour"] // 500 + 1
        cost = level * 400
        if user["coins"] < cost:
            return {"ok": False, "error": "Не хватает монет"}
        user["coins"] -= cost
        user["profit_per_hour"] += 500
        log_msg = f"⛏ <b>Апгрейд Майнинга</b> (+{user['profit_per_hour']}/ч)"

    else:
        return {"ok": False, "error": "Неизвестное улучшение"}

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE users SET coins = ?, energy = ?, max_energy = ?, multitap = ?, profit_per_hour = ?, last_update = ?
               WHERE user_id = ?""",
            (
                user["coins"],
                user["energy"],
                user["max_energy"],
                user["multitap"],
                user["profit_per_hour"],
                int(time.time()),
                user_id,
            ),
        )
        await db.commit()

    await send_admin_log(
        f"{log_msg}\n"
        f"Игрок: {user['first_name']} (<code>{user_id}</code>)\n"
        f"Баланс: {user['coins']:,} 🪙"
    )
    return {"ok": True, "user": user}


@app.get("/api/leaderboard")
async def api_leaderboard():
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT first_name, coins, profit_per_hour FROM users ORDER BY coins DESC LIMIT 15"
        )
        rows = await cur.fetchall()
    return {
        "leaders": [
            {"name": r[0], "coins": r[1], "profit_per_hour": r[2]} for r in rows
        ]
    }


@app.post("/api/client-log")
async def api_client_log(request: Request, x_init_data: str = Header(default="")):
    try:
        tg_user = verify_telegram_init_data(x_init_data)
        who = f"{tg_user.get('first_name')} (<code>{tg_user.get('id')}</code>)"
    except Exception:
        who = "Неавторизованный клиент"

    body = await request.json()
    msg = str(body.get("message", ""))[:1000]
    await send_admin_log(f"⚠️ <b>Лог/Ошибка из Mini App</b>\nОт: {who}\n<code>{msg}</code>")
    return {"ok": True}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
