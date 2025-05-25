import json
import uuid
import threading
import time
import requests
import os
from utils import escape_markdown, get_irst_time, get_user_profile_photo, answer_inline_query, answer_callback_query, edit_message_text, format_block_code
from database import load_history, save_history, history
from cache import get_cached_inline_query, set_cached_inline_query
from logger import logger

# فایل برای ذخیره دائمی whispers
WHISPERS_FILE = "whispers.json"

# بارگذاری whispers از فایل
def load_whispers():
    try:
        with open(WHISPERS_FILE, "r") as f:
            data = json.load(f)
            for key, value in data.items():
                if "curious_users" in value:
                    value["curious_users"] = [user for user in value["curious_users"]]
            return data
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.error("Error loading whispers: %s", str(e))
        return {}

# ذخیره whispers در فایل
def save_whispers(whispers_data):
    try:
        with open(WHISPERS_FILE, "w") as f:
            json.dump(whispers_data, f, indent=4)
    except Exception as e:
        logger.error("Error saving whispers: %s", str(e))

whispers = load_whispers()
BOT_USERNAME = "@Bgnabot"
TOKEN = os.getenv("BOT_TOKEN", "7889701836:AAECLBRjjDadhpgJreOctpo5Jc72ekDKNjc")
URL = f"https://api.telegram.org/bot{TOKEN}/"

def resolve_user_id(receiver_id):
    """تبدیل یوزرنیم/آیدی به آیدی عددی"""
    if receiver_id.startswith('@'):
        username = receiver_id.lstrip('@')
        try:
            resp = requests.get(f"{URL}getChat", params={"chat_id": f"@{username}"}).json()
            return str(resp['result']['id']) if resp.get('ok') else None
        except:
            return None
    elif receiver_id.isdigit():
        return receiver_id
    return None

def process_update(update):
    """پردازش آپدیت‌های دریافتی از تلگرام"""
    global whispers

    if "inline_query" in update:
        inline_query = update["inline_query"]
        query = inline_query.get("query", "").replace(BOT_USERNAME, "").strip()
        
        # پردازش کوئری‌های معتبر
        if query:
            parts = query.split(maxsplit=1)
            if len(parts) == 2:
                target, secret_message = parts
                receiver_id = resolve_user_id(target)
                
                if not receiver_id:
                    answer_inline_query(inline_query["id"], [{
                        "type": "article",
                        "id": "error",
                        "title": "❌ کاربر یافت نشد!",
                        "input_message_content": {"message_text": "خطا: شناسه کاربر نامعتبر است!"}
                    }])
                    return
                
                # دریافت اطلاعات کاربر
                try:
                    user_info = requests.get(f"{URL}getChat", params={"chat_id": receiver_id}).json()['result']
                    first_name = user_info.get('first_name', 'ناشناس')
                    username = user_info.get('username', '')
                except:
                    first_name = "ناشناس"
                    username = ""

                # ساخت محتوای پیام
                message_link = f"[{escape_markdown(first_name)}](tg://user?id={receiver_id})"
                code_content = f"{first_name} 0 | ۰۰:۰۰\n__________\nبدون بازدید"
                public_text = f"{message_link}\n```\n{code_content}\n```"

                # ساخت دکمه‌های تعاملی
                markup = {
                    "inline_keyboard": [
                        [
                            {"text": "👁️ نمایش", "callback_data": f"show_{uuid.uuid4().hex}"},
                            {"text": "🗨️ پاسخ", "switch_inline_query_current_chat": f"{inline_query['from']['id']}"}
                        ]
                    ]
                }

                # دریافت و ذخیره عکس پروفایل
                _, photo_url = get_user_profile_photo(int(receiver_id))
                history_entry = {
                    "receiver_id": receiver_id,
                    "name": first_name,
                    "photo": photo_url,
                    "time": time.time()
                }
                save_history(inline_query['from']['id'], history_entry)

                # ارسال نتیجه
                answer_inline_query(inline_query["id"], [{
                    "type": "article",
                    "id": receiver_id,
                    "title": f"🔐 ارسال نجوا به {first_name}",
                    "description": f"پیام: {secret_message[:20]}...",
                    "thumb_url": photo_url,
                    "input_message_content": {
                        "message_text": public_text,
                        "parse_mode": "MarkdownV2"
                    },
                    "reply_markup": markup
                }])
                return

        # نمایش تاریخچه
        sender_id = str(inline_query['from']['id'])
        results = [{
            "type": "article",
            "id": "help",
            "title": "💡 راهنمای استفاده",
            "input_message_content": {
                "message_text": "برای ارسال نجوا:\n@Bgnabot [آدی/یوزرنیم] [متن پیام]"
            },
            "thumb_url": "https://via.placeholder.com/150"
        }]
        
        if sender_id in history:
            for item in history[sender_id]:
                # دریافت عکس به روز شده
                _, photo = get_user_profile_photo(int(item['receiver_id']))
                results.append({
                    "type": "article",
                    "id": f"hist_{item['receiver_id']}",
                    "title": f"✉️ تاریخچه نجوا به {item['name']}",
                    "description": f"آخرین ارسال: {get_irst_time(item['time'])}",
                    "thumb_url": photo,
                    "input_message_content": {
                        "message_text": f"ارسال مجدد پیام به {item['name']}"
                    }
                })
        
        answer_inline_query(inline_query["id"], results)

    elif "callback_query" in update:
        callback = update["callback_query"]
        callback_id = callback["id"]
        data = callback["data"]
        message = callback.get("message")
        inline_message_id = callback.get("inline_message_id")

        if data.startswith("show_"):
            unique_id = data.split("_")[1]
            whisper_data = whispers.get(unique_id)

            if not whisper_data:
                answer_callback_query(callback_id, "⌛️ نجوا منقضی شده! 🕒", True)
                return

            user = callback["from"]
            user_id = str(user["id"])
            username = user.get("username", "").lstrip('@').lower() if user.get("username") else None
            first_name = user.get("first_name", "")
            last_name = user.get("last_name", "")
            user_display_name = f"{first_name} {last_name}".strip() if last_name else first_name

            is_allowed = (
                user_id == whisper_data["sender_id"] or
                (whisper_data["receiver_username"] and username and username == whisper_data["receiver_username"]) or
                (whisper_data["receiver_user_id"] and user_id == str(whisper_data["receiver_user_id"]))
            )

            if is_allowed and user_id != whisper_data["sender_id"]:
                whisper_data["receiver_views"].append(time.time())
                save_whispers(whispers)
            elif not is_allowed:
                whisper_data["curious_users"].append({"id": user_id, "name": user_display_name})
                save_whispers(whispers)

            receiver_first_name = whisper_data["first_name"]
            receiver_id = whisper_data.get("receiver_id", "0")
            receiver_username = whisper_data["receiver_username"]
            receiver_first_name_escaped = escape_markdown(receiver_first_name)
            receiver_link = f"[{receiver_first_name_escaped}](https://t.me/{receiver_username})" if receiver_username else f"[{receiver_first_name_escaped}](tg://user?id={receiver_id})"
            code_content = format_block_code(whisper_data)
            new_text = f"{receiver_link}\n```\n{code_content}\n```"

            reply_target = f"@{whisper_data['sender_username']}" if whisper_data["sender_username"] else str(whisper_data["sender_id"])
            reply_text = f"{reply_target} "
            keyboard = {
                "inline_keyboard": [
                    [
                        {"text": "👁️ Show", "callback_data": f"show_{unique_id}"},
                        {"text": "🗨️ Reply", "switch_inline_query_current_chat": reply_text}
                    ],
                    [
                        {"text": "Secret Room 😈", "callback_data": f"secret_{unique_id}"}
                    ]
                ]
            }

            try:
                if message:
                    edit_message_text(
                        chat_id=message["chat"]["id"],
                        message_id=message["message_id"],
                        text=new_text,
                        reply_markup=keyboard
                    )
                elif inline_message_id:
                    edit_message_text(
                        inline_message_id=inline_message_id,
                        text=new_text,
                        reply_markup=keyboard
                    )

                response_text = f"🔐 پیام نجوا:\n{whisper_data['secret_message']} 🎁" if is_allowed else "⚠️ این نجوا برای تو نیست! 😕"
                answer_callback_query(callback_id, response_text, show_alert=True)
            except Exception as e:
                logger.error("Error editing message: %s", str(e))
                answer_callback_query(callback_id, "خطایی رخ داد. دوباره امتحان کنید!", True)

        elif data.startswith("secret_"):
            unique_id = data.split("_")[1]
            whisper_data = whispers.get(unique_id)

            if not whisper_data:
                answer_callback_query(callback_id, "⌛️ نجوا منقضی شده! 🕒", True)
                return

            user = callback["from"]
            user_id = str(user["id"])
            is_allowed = user_id == whisper_data["sender_id"]

            if is_allowed:
                response_text = f"🔐 Secret Room:\n{whisper_data['secret_message']} 🎁\nاینجا فقط فرستنده می‌تونه پیام رو ببینه!"
            else:
                response_text = "⚠️ فقط فرستنده می‌تونه به Secret Room دسترسی داشته باشه! 😈"
            answer_callback_query(callback_id, response_text, show_alert=True)