import requests
from datetime import datetime, timezone, timedelta
import json
from functools import lru_cache
import os

TOKEN = os.getenv("BOT_TOKEN", "7889701836:AAECLBRjjDadhpgJreOctpo5Jc72ekDKNjc")
URL = f"https://api.telegram.org/bot{TOKEN}/"
IRST_OFFSET = timedelta(hours=3, minutes=30)

@lru_cache(maxsize=1000)
def get_user_profile_photo(user_id):
    """دریافت عکس پروفایل کاربر با کش"""
    url = URL + "getUserProfilePhotos"
    params = {"user_id": user_id, "limit": 1}
    try:
        resp = requests.get(url, params=params).json()
        if resp.get("ok") and resp["result"]["total_count"] > 0:
            # 🟢 اولویت استفاده از عکس اصلی پروفایل
            file_id = resp["result"]["photos"][0][-1]["file_id"]  # آخرین سایز عکس
            file_path_url = URL + "getFile"
            file_params = {"file_id": file_id}
            file_resp = requests.get(file_path_url, params=file_params).json()
            if file_resp.get("ok"):
                file_path = file_resp["result"]["file_path"]
                file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"
                print(f"Profile photo URL for user_id {user_id}: {file_url}")
                return file_id, file_url
        print(f"No profile photo found for user_id {user_id}")
        return None, "https://via.placeholder.com/150"  # تصویر پیش‌فرض
    except Exception as e:
        print(f"Error fetching profile photo for user_id {user_id}: {e}")
        return None, "https://via.placeholder.com/150"

def escape_markdown(text):
    """فرمت کردن متن برای MarkdownV2 با مدیریت کاراکترهای خاص"""
    if not text or not text.strip():
        return "Unknown"
    escape_chars = '_*[]()~`>#+-=|{}.!'
    escaped_text = ''.join(['\\' + char if char in escape_chars else char for char in str(text)])
    return escaped_text if escaped_text.strip() else "Unknown"

def get_irst_time(timestamp):
    """تبدیل زمان به وقت ایران"""
    utc_time = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    irst_time = utc_time + IRST_OFFSET
    return irst_time.strftime("%H:%M")

def answer_inline_query(inline_query_id, results):
    """پاسخ به inline query"""
    url = URL + "answerInlineQuery"
    data = {
        "inline_query_id": inline_query_id,
        "results": json.dumps(results),
        "cache_time": 0,
        "is_personal": True
    }
    requests.post(url, data=data)

def answer_callback_query(callback_query_id, text, show_alert=False):
    """پاسخ به callback query"""
    url = URL + "answerCallbackQuery"
    data = {
        "callback_query_id": callback_query_id,
        "text": text,
        "show_alert": show_alert
    }
    requests.post(url, data=data)

def edit_message_text(chat_id=None, message_id=None, inline_message_id=None, text=None, reply_markup=None):
    """ویرایش پیام"""
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
    """فرمت کردن اطلاعات نجوا برای نمایش در بلاک کد"""
    receiver_first_name = whisper_data.get('first_name', 'Unknown')
    view_times = whisper_data.get("receiver_views", [])
    view_count = len(view_times)
    view_time_str = get_irst_time(view_times[-1]) if view_times else "Don't see."
    code_content = f"{escape_markdown(receiver_first_name)} {view_count} | {view_time_str}\n___________"
    curious_users = whisper_data.get("curious_users", [])
    if curious_users:
        code_content += "\nCurious\n" + "\n".join([escape_markdown(user.get("name", "Unknown")) for user in sorted(curious_users, key=lambda x: x.get("name", ""))])
    else:
        code_content += "\nNothing"
    return code_content