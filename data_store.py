import json
import os
import time
from pathlib import Path

from config import INITIAL_ADMINS, MANDATORY_CHANNELS, SELL_CHANNEL, BUY_CHANNEL

DATA_FILE = "bot_data.json"

data = {
    "users": {},         
    "admins": INITIAL_ADMINS.copy(),  
    "mandatory_channels": MANDATORY_CHANNELS.copy(),
    "sell_channel": SELL_CHANNEL,
    "buy_channel": BUY_CHANNEL,
    "events": []           
}


_used_unique_ids = set()

def load_data():
    """Load data from JSON file if it exists, else use defaults."""
    global data, _used_unique_ids
    if Path(DATA_FILE).exists():
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                stored = json.load(f)

            for key in data:
                if key in stored:
                    data[key] = stored[key]
            data["admins"] = [int(x) for x in data.get("admins", [])]
        except Exception as e:
            print(f"Failed to load data file: {e}")
    _used_unique_ids.clear()
    for u in data["users"].values():
        uid = u.get("unique_id")
        if uid:
            _used_unique_ids.add(uid)

def save_data():
    """Save current data to JSON file."""
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving data: {e}")

def generate_unique_id():
    """Generate a unique 12-digit ID not used before."""
    import random
    while True:
        code = str(random.randint(10**11, 10**12 - 1))
        if code not in _used_unique_ids:
            _used_unique_ids.add(code)
            return code

def add_user(user_id: int, first_name: str, username: str = None, referrer_id: int = None):
    """Add a new user to data and return the user record dict."""
    user_id_str = str(user_id)
    if user_id_str in data["users"]:
        return data["users"][user_id_str]
    unique_code = generate_unique_id()
    now = int(time.time())
    user_data = {
        "id": user_id,
        "unique_id": unique_code,
        "first_name": first_name,
        "username": username,
        "joined_at": now,
        "captcha_passed": False,
        "channels_verified": False,
        "subscription": {
            "tier": None,
            "expires": None
        },
        "pins_used": 0,
        "pins_cycle_start": None,
        "posts_count": 0,
        "posts": [],    
        "referrer_id": referrer_id,
        "referrals": [],
        "banned": False,
    }
    data["users"][user_id_str] = user_data
    save_data()
    return user_data

def get_user(user_id: int):
    """Get user data dict by id. Returns None if not exists."""
    return data["users"].get(str(user_id))

def update_username(user_id: int, username: str):
    """Update stored username for a user."""
    u = get_user(user_id)
    if not u:
        return
    u["username"] = username

def record_event(event_type: str, **kwargs):
    """Record an event (for analytics)."""
    evt = {"type": event_type, "time": int(time.time())}
    evt.update(kwargs)
    data["events"].append(evt)
    save_data()
