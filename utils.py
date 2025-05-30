import requests
from datetime import datetime, timezone, timedelta
import json
from functools import lru_cache
import os

TOKEN = os.getenv("BOT_TOKEN", "7889701836:AAECLBRjjDadhpgJreOctpo5Jc72ekDKNjc")
URL = f"https://api.telegram.org/bot{TOKEN}/"
IRST_OFFSET = timedelta(hours=3, minutes=30)

@lru_cache(maxsize=500)
def get_user_profile_photo(user_id):
    """Get high-quality profile photo"""
    try:
        resp = requests.get(f"{URL}getUserProfilePhotos", params={
            "user_id": user_id,
            "limit": 1
        }, timeout=5).json()
        
        if resp.get("ok") and resp["result"]["total_count"] > 0:
            file_id = resp["result"]["photos"][0][-1]["file_id"]
            file_resp = requests.get(f"{URL}getFile", params={"file_id": file_id}).json()
            if file_resp.get("ok"):
                return (
                    file_id,
                    f"https://api.telegram.org/file/bot{TOKEN}/{file_resp['result']['file_path']}"
                )
        return None, "https://via.placeholder.com/150"
    except:
        return None, "https://via.placeholder.com/150"

def escape_markdown(text):
    """Format text for MarkdownV2, escaping special characters"""
    if not text or not text.strip():
        return "Unknown"
    escape_chars = '_*[]()~`>#+-=|{}.!'
    escaped_text = ''.join(['\\' + char if char in escape_chars else char for char in str(text)])
    return escaped_text if escaped_text.strip() else "Unknown"

def get_irst_time(timestamp):
    """Convert timestamp to Iran time"""
    utc_time = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    irst_time = utc_time + IRST_OFFSET
    return irst_time.strftime("%H:%M")

def answer_inline_query(inline_query_id, results):
    """Answer inline query"""
    url = URL + "answerInlineQuery"
    data = {
        "inline_query_id": inline_query_id,
        "results": json.dumps(results),
        "cache_time": 0,
        "is_personal": True
    }
    requests.post(url, data=data)

def answer_callback_query(callback_query_id, text, show_alert=False):
    """Answer callback query"""
    url = URL + "answerCallbackQuery"
    data = {
        "callback_query_id": callback_query_id,
        "text": text,
        "show_alert": show_alert
    }
    requests.post(url, data=data)

def edit_message_text(chat_id=None, message_id=None, inline_message_id=None, text=None, reply_markup=None):
    """Edit message text"""
    url = URL + "editMessageText"
    data = {
        "text": text,
        "parse_mode": "MarkdownV2",
        "reply_markup": json.dumps(reply_markup) if reply_markup else None
    }
    if chat_id and message_id:
        data["chat_id"] = chat_id
        data["message_id"] = message_id
    elif inline_message_id:
        data["inline_message_id"] = inline_message_id
    else:
        raise ValueError("Either (chat_id and message_id) or inline_message_id must be provided.")
    return requests.post(url, data=data)

def format_block_code(whisper_data):
    """Format whisper data for display in code block"""
    receiver_display_name = whisper_data.get('display_name', 'Unknown')
    view_times = whisper_data.get("receiver_views", [])
    view_count = len(view_times)
    view_time_str = get_irst_time(view_times[-1]) if view_times else "Not yet"
    code_content = f"{escape_markdown(receiver_display_name)} {view_count} | {view_time_str}\n__________"
    curious_users = whisper_data.get("curious_users", [])
    if curious_users:
        code_content += "\nCuriosity\n" + "\n".join([escape_markdown(user.get("name", "Unknown")) for user in sorted(curious_users, key=lambda x: x.get("name", ""))])
    else:
        code_content += "\nNothing"
    return code_content