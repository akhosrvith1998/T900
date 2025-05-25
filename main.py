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

def get_user_first_name(user_id):
    """دریافت نام کاربر از API تلگرام"""
    url = URL + "getChat"
    params = {"chat_id": user_id}
    try:
        resp = requests.get(url, params=params).json()
        if resp.get("ok"):
            return resp["result"].get("first_name", "Unknown")
        return "Unknown"
    except Exception as e:
        logger.error("Error fetching first name for user_id %s: %s", user_id, str(e))
        return "Unknown"

def resolve_user_id(receiver_id, receiver_username=None):
    """تبدیل یوزرنیم به آیدی عددی یا تأیید آیدی عددی"""
    if receiver_id.isdigit():
        return receiver_id
    if receiver_username:
        url = URL + "getChat"
        params = {"chat_id": f"@{receiver_username}"}
        try:
            resp = requests.get(url, params=params).json()
            if resp.get("ok"):
                user_id = str(resp["result"]["id"])
                print(f"Resolved user_id for @{receiver_username}: {user_id}")
                return user_id
        except Exception as e:
            logger.error("Error resolving user_id for username @%s: %s", receiver_username, str(e))
    logger.error("Could not resolve user_id for receiver_id %s", receiver_id)
    return None

def process_update(update):
    """پردازش آپدیت‌های دریافتی از تلگرام"""
    global whispers

    if "inline_query" in update:
        inline_query = update["inline_query"]
        query_id = inline_query["id"]
        raw_query = inline_query.get("query", "").strip()
        query_text = raw_query.replace(BOT_USERNAME, "", 1).strip()
        sender = inline_query["from"]
        sender_id = str(sender["id"])

        cached_results = get_cached_inline_query(sender_id, query_text)
        if cached_results:
            logger.info("Serving cached inline query for %s: %s", sender_id, query_text)
            answer_inline_query(query_id, cached_results)
            return

        base_result = {
            "type": "article",
            "id": "base",
            "title": "💡 راهنمای نجوا",
            "input_message_content": {
                "message_text": (
                    "راهنمای نجوا:\n\n"
                    "روش اول با یوزرنیم گیرنده:\n"
                    "@Bgnabot @username متن نجوا\n\n"
                    "روش دوم با آیدی عددی گیرنده:\n"
                    "@Bgnabot 1234567890 متن نجوا\n\n"
                    "یا فقط متن نجوا را وارد کنید و از تاریخچه گیرنده انتخاب کنید!"
                )
            },
            "description": "همیشه فعال!",
            "thumb_url": "https://via.placeholder.com/150"
        }

        results = [base_result]
        # نمایش تاریخچه با به‌روزرسانی عکس پروفایل
        if sender_id in history:
            for receiver in sorted(history[sender_id], key=lambda x: x.get("display_name", "")):
                receiver_id = receiver.get("receiver_id", "")
                if not receiver_id:
                    continue
                receiver_user_id = receiver_id if receiver_id.isdigit() else None
                receiver_first_name = receiver.get("first_name", "Unknown")
                profile_photo, profile_photo_url = get_user_profile_photo(int(receiver_user_id)) if receiver_user_id else (None, None)
                if profile_photo_url:
                    receiver["profile_photo_url"] = profile_photo_url
                    save_history(sender_id, receiver)
                result = {
                    "type": "article",
                    "id": f"history_{receiver_id}",
                    "title": f"نجوا به {receiver.get('display_name', 'Unknown')} ✨",
                    "input_message_content": {
                        "message_text": f"📩 پیام خود را برای {receiver.get('display_name', 'Unknown')} وارد کنید"
                    },
                    "description": f"ارسال نجوا به {receiver_first_name}",
                    "thumb_url": receiver.get("profile_photo_url", "https://via.placeholder.com/150")
                }
                results.append(result)

        # پردازش نجوا یا نمایش تاریخچه
        if query_text:
            parts = query_text.split(" ", 1)
            receiver_id = parts[0].strip()
            secret_message = parts[1].strip() if len(parts) > 1 else ""

            receiver_username = None
            receiver_user_id = None
            if receiver_id.startswith('@'):
                receiver_username = receiver_id.lstrip('@').lower()
            elif receiver_id.isdigit():
                receiver_user_id = receiver_id
            else:
                # اگر نه یوزرنیمه نه آیدی عددی، فرض می‌کنیم کاربر می‌خواد از تاریخچه استفاده کنه
                secret_message = query_text
                results = [base_result]
                for receiver in sorted(history.get(sender_id, []), key=lambda x: x.get("display_name", "")):
                    receiver_id = receiver.get("receiver_id", "")
                    if not receiver_id:
                        continue
                    receiver_username = receiver_id.lstrip('@').lower() if receiver_id.startswith('@') else None
                    receiver_user_id = receiver_id if receiver_id.isdigit() else None
                    receiver_first_name = receiver.get("first_name", "Unknown")

                    profile_photo, profile_photo_url = get_user_profile_photo(int(receiver_user_id)) if receiver_user_id else (None, None)

                    unique_id = uuid.uuid4().hex
                    whispers[unique_id] = {
                        "sender_id": sender_id,
                        "receiver_username": receiver_username,
                        "receiver_user_id": receiver_user_id,
                        "first_name": receiver_first_name,
                        "secret_message": secret_message,
                        "curious_users": [],
                        "receiver_views": [],
                        "created_at": time.time()
                    }
                    save_whispers(whispers)

                    receiver_first_name_escaped = escape_markdown(receiver_first_name)
                    receiver_link = f"[{receiver_first_name_escaped}](https://t.me/{receiver_username})" if receiver_username else f"[{receiver_first_name_escaped}](tg://user?id={receiver_user_id})"
                    code_content = format_block_code(whispers[unique_id])
                    public_text = f"{receiver_link}\n```\n{code_content}\n```"

                    reply_target = f"@{sender.get('username', '').lstrip('@')}" if sender.get("username") else str(sender_id)
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

                    results.append({
                        "type": "article",
                        "id": unique_id,
                        "title": f"🔒 نجوا به {receiver_first_name} 🎉",
                        "input_message_content": {
                            "message_text": public_text,
                            "parse_mode": "MarkdownV2"
                        },
                        "reply_markup": keyboard,
                        "description": f"پیام: {secret_message[:15]}...",
                        "thumb_url": profile_photo_url if profile_photo_url else "https://via.placeholder.com/150"
                    })
                set_cached_inline_query(sender_id, query_text, results)
                answer_inline_query(query_id, results)
                return

            if receiver_username or receiver_user_id:
                actual_receiver_id = resolve_user_id(receiver_id, receiver_username)
                if not actual_receiver_id:
                    raise ValueError("نمی‌توان آیدی عددی گیرنده را پیدا کرد")

                receiver_first_name = get_user_first_name(actual_receiver_id)
                receiver_display_name = f"@{receiver_username}" if receiver_username else str(actual_receiver_id)

                profile_photo, profile_photo_url = get_user_profile_photo(int(actual_receiver_id))

                existing_receiver = next((r for r in history.get(sender_id, []) if r.get("receiver_id") == (f"@{receiver_username}" if receiver_username else str(actual_receiver_id))), None)
                if not existing_receiver:
                    if sender_id not in history:
                        history[sender_id] = []
                    receiver_data = {
                        "receiver_id": f"@{receiver_username}" if receiver_username else str(actual_receiver_id),
                        "display_name": receiver_display_name,
                        "first_name": receiver_first_name,
                        "profile_photo_url": profile_photo_url if profile_photo_url else "",
                        "curious_users": []
                    }
                    history[sender_id].append(receiver_data)
                    history[sender_id] = history[sender_id][-10:]
                    save_history(sender_id, receiver_data)

                unique_id = uuid.uuid4().hex
                sender_username = sender.get("username", "").lstrip('@').lower() if sender.get("username") else None
                sender_display_name = f"{sender.get('first_name', '')} {sender.get('last_name', '')}".strip() if sender.get('last_name') else sender.get('first_name', '')

                whispers[unique_id] = {
                    "sender_id": sender_id,
                    "sender_username": sender_username,
                    "sender_display_name": sender_display_name,
                    "receiver_username": receiver_username,
                    "receiver_user_id": actual_receiver_id,
                    "receiver_id": actual_receiver_id,
                    "receiver_display_name": receiver_display_name,
                    "first_name": receiver_first_name,
                    "secret_message": secret_message,
                    "curious_users": [],
                    "receiver_views": [],
                    "created_at": time.time()
                }
                save_whispers(whispers)

                receiver_first_name_escaped = escape_markdown(receiver_first_name)
                receiver_link = f"[{receiver_first_name_escaped}](https://t.me/{receiver_username})" if receiver_username else f"[{receiver_first_name_escaped}](tg://user?id={actual_receiver_id})"
                code_content = format_block_code(whispers[unique_id])
                public_text = f"{receiver_link}\n```\n{code_content}\n```"

                reply_target = f"@{sender_username}" if sender_username else str(sender_id)
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

                results = [
                    {
                        "type": "article",
                        "id": unique_id,
                        "title": f"🔒 نجوا به {receiver_first_name} 🎉",
                        "input_message_content": {
                            "message_text": public_text,
                            "parse_mode": "MarkdownV2"
                        },
                        "reply_markup": keyboard,
                        "description": f"پیام: {secret_message[:15]}...",
                        "thumb_url": profile_photo_url if profile_photo_url else "https://via.placeholder.com/150"
                    },
                    base_result
                ]
                set_cached_inline_query(sender_id, query_text, results)
                answer_inline_query(query_id, results)

        else:
            set_cached_inline_query(sender_id, query_text, results)
            answer_inline_query(query_id, results)

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
            receiver_id = whisper_data["receiver_id"]
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