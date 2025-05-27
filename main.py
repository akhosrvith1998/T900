import json
import uuid
import time
import requests
import os
import re  # برای regex

from utils import escape_markdown, get_irst_time, answer_inline_query, answer_callback_query, edit_message_text, format_block_code
from cache import get_cached_inline_query, set_cached_inline_query
from logger import logger

WHISPERS_FILE = "whispers.json"
TEHRAN_OFFSET = 3.5 * 3600  # آفست زمان تهران

USER_INFO_CACHE = {}

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

def resolve_user_id(receiver_id, reply_to_message=None):
    """تشخیص یوزرنیم، آیدی عددی یا ریپلای"""
    try:
        if reply_to_message and 'from' in reply_to_message:
            logger.info("Extracting user ID from reply: %s", reply_to_message['from']['id'])
            return str(reply_to_message['from']['id']), None  # برگرداندن آیدی عددی برای ریپلای
        elif receiver_id.startswith('@'):
            username = receiver_id.lstrip('@').lower()
            if not username:
                logger.warning("Empty username provided")
                return None, None
            return None, username  # برگرداندن یوزرنیم بدون تبدیل به آیدی
        elif receiver_id.isdigit():
            logger.info("Using numeric ID: %s", receiver_id)
            return receiver_id, None  # برگرداندن آیدی عددی
        logger.error("Invalid receiver ID format: %s", receiver_id)
        return None, None
    except Exception as e:
        logger.error("Error resolving user ID: %s", str(e))
        return None, None

def get_user_profile_photo(user_id):
    try:
        response = requests.get(f"{URL}getUserProfilePhotos", params={"user_id": user_id, "limit": 1}, timeout=10).json()
        if not response.get('ok'):
            logger.error("Failed to get profile photos for user %s: %s (Error code: %s)", 
                         user_id, response.get('description', 'Unknown error'), response.get('error_code', 'N/A'))
            return "https://via.placeholder.com/150"
        photos = response['result']['photos']
        if not photos:
            logger.info("No profile photos found for user %s", user_id)
            return "https://via.placeholder.com/150"
        photo = photos[0][-1]
        file_id = photo['file_id']
        file_response = requests.get(f"{URL}getFile", params={"file_id": file_id}, timeout=10).json()
        if not file_response.get('ok'):
            logger.error("Failed to get file path for file_id %s: %s", file_id, file_response.get('description', 'Unknown error'))
            return "https://via.placeholder.com/150"
        file_path = file_response['result']['file_path']
        photo_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"
        logger.info("Successfully retrieved photo URL for user %s: %s", user_id, photo_url)
        return photo_url
    except Exception as e:
        logger.error("Error getting profile photo for user %s: %s", user_id, str(e))
        return "https://via.placeholder.com/150"

def fetch_user_info(receiver_id, receiver_username=None):
    """دریافت اطلاعات کاربر بر اساس آیدی یا یوزرنیم"""
    try:
        if receiver_id and receiver_id in USER_INFO_CACHE:
            cached_info = USER_INFO_CACHE[receiver_id]
            logger.info("Using cached user info for %s: %s", receiver_id, cached_info)
            return cached_info['username'], receiver_id, cached_info['display_name'], cached_info['photo_url']

        if receiver_username:
            resolved_id, user_info = resolve_username_to_id(receiver_username)
            if not resolved_id:
                return receiver_username, None, f"@{receiver_username}", "https://via.placeholder.com/150"
        else:
            resolved_id = receiver_id

        user_info = requests.get(f"{URL}getChat", params={"chat_id": resolved_id}, timeout=10).json()
        if not user_info.get('ok'):
            logger.error("Failed to get user info for %s: %s (Error code: %s)", 
                         resolved_id, user_info.get('description', 'Unknown error'), user_info.get('error_code', 'N/A'))
            return receiver_username, resolved_id, receiver_username or str(resolved_id), "https://via.placeholder.com/150"
        
        user_info = user_info['result']
        first_name = user_info.get('first_name', 'Unknown')
        username = user_info.get('username', '').lstrip('@') if user_info.get('username') else None
        display_name = f"@{username}" if username else f"{first_name} {user_info.get('last_name', '')}".strip()
        photo_url = get_user_profile_photo(resolved_id)

        USER_INFO_CACHE[resolved_id] = {
            "username": username,
            "display_name": display_name,
            "photo_url": photo_url
        }
        logger.info("Cached user info for %s: %s", resolved_id, USER_INFO_CACHE[resolved_id])
        return username, resolved_id, display_name, photo_url
    except Exception as e:
        logger.error("Error getting user info for %s: %s", receiver_id, str(e))
        return receiver_username, receiver_id, receiver_username or str(receiver_id), "https://via.placeholder.com/150"

def resolve_username_to_id(username):
    try:
        if not username or not username.strip():
            logger.warning("Empty or invalid username provided: %s", username)
            return None, None
        response = requests.get(f"{URL}getChat", params={"chat_id": f"@{username}"}, timeout=10).json()
        if response.get('ok'):
            user_info = response['result']
            return str(user_info['id']), user_info
        else:
            logger.error("Failed to resolve username @%s: %s (Error code: %s)", 
                         username, response.get('description', 'Unknown error'), response.get('error_code', 'N/A'))
            return None, None
    except Exception as e:
        logger.error("Error resolving username @%s: %s", username, str(e))
        return None, None

def format_diff_block_code(whisper_data):
    display_name = whisper_data["display_name"]
    receiver_views = whisper_data.get("receiver_views", [])
    view_count = len(receiver_views)
    last_seen_time = receiver_views[-1] if receiver_views else None
    
    if last_seen_time:
        tehran_time = last_seen_time + TEHRAN_OFFSET
        seen_text = f"گیرنده [{view_count}] خونده | {time.strftime('%H:%M', time.localtime(tehran_time))}"
    else:
        seen_text = "هنوز نخونده"
    
    return f"- {seen_text}"

def extract_receiver_and_message(query):
    """جدا کردن گیرنده و پیام با regex"""
    username_match = re.search(r'@[\w\d]+', query)
    numeric_match = re.search(r'\b\d{8,}\b', query)
    
    if username_match:
        receiver = username_match.group(0)
        message = query.replace(receiver, '').strip()
        return receiver, message
    elif numeric_match:
        receiver = numeric_match.group(0)
        message = query.replace(receiver, '').strip()
        return receiver, message
    else:
        return None, query.strip()

def process_update(update):
    logger.info("Bot processing update: %s", update)
    global whispers

    if "inline_query" in update:
        inline_query = update["inline_query"]
        query = inline_query.get("query", "").strip()
        sender_id = str(inline_query['from']['id'])
        sender_username = inline_query['from'].get('username', '')
        chat_type = inline_query.get("chat_type", "unknown")

        if query.startswith(BOT_USERNAME):
            query = query[len(BOT_USERNAME):].strip()

        logger.info("Processing inline query from %s in chat_type %s: '%s'", sender_id, chat_type, query)

        # جدا کردن گیرنده و پیام
        target, secret_message = extract_receiver_and_message(query)
        receiver_id, receiver_username = resolve_user_id(target) if target else (None, None)

        # Case 1: Valid receiver (username or ID) + secret message
        if (receiver_id or receiver_username) and secret_message:
            try:
                username, resolved_id, display_name, photo_url = fetch_user_info(receiver_id, receiver_username)
                
                message_text = f"گیرنده ({display_name})"
                code_content = format_diff_block_code({"display_name": display_name, "receiver_views": [], "curious_users": []})
                public_text = f"{message_text}\n```diff\n{code_content}\n```"

                unique_id = uuid.uuid4().hex
                markup = {
                    "inline_keyboard": [
                        [
                            {"text": "ببینم", "callback_data": f"show_{unique_id}"},
                            {"text": "پاسخ", "switch_inline_query_current_chat": f"{BOT_USERNAME} {sender_id} "}
                        ],
                        [
                            {"text": "حذف نجوا 💣", "callback_data": f"delete_{unique_id}"},
                            {"text": f"فضول‌ها [0]", "callback_data": f"curious_{unique_id}"}
                        ]
                    ]
                }

                whispers[unique_id] = {
                    "sender_id": sender_id,
                    "sender_username": sender_username.lstrip('@') if sender_username else None,
                    "receiver_id": resolved_id if receiver_id else None,
                    "receiver_username": receiver_username if receiver_username else username,
                    "display_name": display_name,
                    "secret_message": secret_message,
                    "receiver_views": [],
                    "curious_users": [],
                    "deleted": False
                }
                save_whispers(whispers)

                response = [{
                    "type": "article",
                    "id": unique_id,
                    "title": f"ارسال نجوا به {display_name}",
                    "description": f"پیام: {secret_message[:20]}...",
                    "thumb_url": photo_url,
                    "input_message_content": {
                        "message_text": public_text,
                        "parse_mode": "MarkdownV2"
                    },
                    "reply_markup": markup
                }]
                logger.info("Sending inline query response for whisper %s: %s", unique_id, response)
                answer_inline_query(inline_query["id"], response)
            except Exception as e:
                logger.error("Error processing whisper: %s", str(e))
                answer_inline_query(inline_query["id"], [{
                    "type": "article",
                    "id": "error",
                    "title": "خطا!",
                    "input_message_content": {
                        "message_text": "مشکلی پیش اومد. لطفاً دوباره امتحان کن."
                    },
                    "thumb_url": "https://via.placeholder.com/150"
                }])

        # Case 2: Only receiver provided, no secret message
        elif receiver_id or receiver_username:
            try:
                username, resolved_id, display_name, photo_url = fetch_user_info(receiver_id, receiver_username)

                results = [{
                    "type": "article",
                    "id": f"target_{resolved_id or receiver_username}",
                    "title": f"ارسال نجوا (به {display_name})",
                    "description": "پیام خودت رو وارد کن...",
                    "thumb_url": photo_url,
                    "input_message_content": {
                        "message_text": f"ارسال نجوا به گیرنده ({display_name})\nلطفاً پیام خود را وارد کنید.",
                        "parse_mode": "MarkdownV2"
                    },
                    "reply_markup": {
                        "inline_keyboard": [[
                            {"text": f"ارسال نجوا (به {display_name})", "switch_inline_query_current_chat": f"{BOT_USERNAME} {target} "}
                        ]]
                    }
                }]
                logger.info("Sending receiver selection response for %s: %s", resolved_id or receiver_username, results)
                answer_inline_query(inline_query["id"], results)
            except Exception as e:
                logger.error("Error processing receiver selection: %s", str(e))
                answer_inline_query(inline_query["id"], [{
                    "type": "article",
                    "id": "error",
                    "title": "خطا!",
                    "input_message_content": {
                        "message_text": "مشکلی پیش اومد. لطفاً دوباره امتحان کن."
                    },
                    "thumb_url": "https://via.placeholder.com/150"
                }])

        # Case 3: Nothing provided, show guide
        else:
            try:
                results = [{
                    "type": "article",
                    "id": "guide",
                    "title": "( آیدی رو تایپ کن یا از ریپلای استفاده کن )",
                    "input_message_content": {
                        "message_text": "یه چیزی تایپ کن تا بتونم نجوا رو آماده کنم!\nمثال: @Bgnabot @username پیامت\nیا @Bgnabot 1234567890 پیامت\nیا روی پیام کسی ریپلای کن و @Bgnabot پیامت رو بنویس."
                    },
                    "thumb_url": "https://via.placeholder.com/150"
                }]
                logger.info("Sending guide response: %s", results)
                answer_inline_query(inline_query["id"], results)
            except Exception as e:
                logger.error("Error processing guide: %s", str(e))
                answer_inline_query(inline_query["id"], [{
                    "type": "article",
                    "id": "error",
                    "title": "خطا!",
                    "input_message_content": {
                        "message_text": "مشکلی پیش اومد. لطفاً دوباره امتحان کن."
                    },
                    "thumb_url": "https://via.placeholder.com/150"
                }])

    elif "message" in update and "reply_to_message" in update["message"] and update["message"]["chat"]["type"] in ["group", "supergroup"]:
        try:
            message = update["message"]
            chat_id = message["chat"]["id"]
            sender_id = str(message["from"]["id"])
            sender_username = message["from"].get("username", "")
            text = message.get("text", "").strip()

            if text.startswith(BOT_USERNAME):
                text = text[len(BOT_USERNAME):].strip()
                secret_message = text
                receiver_id, _ = resolve_user_id(None, message["reply_to_message"])
                username, _, display_name, photo_url = fetch_user_info(receiver_id)
                logger.info("Detected reply to user %s (%s) in group chat %s with message: %s", display_name, receiver_id, chat_id, secret_message)

                if secret_message:
                    message_text = f"گیرنده ({display_name})"
                    code_content = format_diff_block_code({"display_name": display_name, "receiver_views": [], "curious_users": []})
                    public_text = f"{message_text}\n```diff\n{code_content}\n```"

                    unique_id = uuid.uuid4().hex
                    markup = {
                        "inline_keyboard": [
                            [
                                {"text": "ببینم", "callback_data": f"show_{unique_id}"},
                                {"text": "پاسخ", "switch_inline_query_current_chat": f"{BOT_USERNAME} {sender_id} "}
                            ],
                            [
                                {"text": "حذف نجوا 💣", "callback_data": f"delete_{unique_id}"},
                                {"text": f"فضول‌ها [0]", "callback_data": f"curious_{unique_id}"}
                            ]
                        ]
                    }

                    whispers[unique_id] = {
                        "sender_id": sender_id,
                        "sender_username": sender_username.lstrip('@') if sender_username else None,
                        "receiver_id": receiver_id,
                        "receiver_username": username,
                        "display_name": display_name,
                        "secret_message": secret_message,
                        "receiver_views": [],
                        "curious_users": [],
                        "deleted": False
                    }
                    save_whispers(whispers)

                    response = requests.post(f"{URL}sendMessage", json={
                        "chat_id": chat_id,
                        "text": public_text,
                        "parse_mode": "MarkdownV2",
                        "reply_markup": markup
                    })
                    if response.status_code == 200:
                        logger.info("Whisper sent successfully in group for %s", unique_id)
                    else:
                        logger.error("Failed to send whisper in group: %s", response.text)
        except Exception as e:
            logger.error("Error processing group message: %s", str(e))

    elif "callback_query" in update:
        try:
            callback = update["callback_query"]
            callback_id = callback["id"]
            data = callback["data"]
            messageoti = callback.get("message")
            inline_message_id = callback.get("inline_message_id")

            user = callback["from"]
            user_id = str(user["id"])
            user_username = user.get("username", "").lstrip('@')
            first_name = user.get("first_name", "")
            last_name = user.get("last_name", "")
            user_display_name = f"{first_name} {last_name}".strip() if last_name else first_name

            if data.startswith("show_"):
                unique_id = data.split("_")[1]
                whisper_data = whispers.get(unique_id)

                if not whisper_data:
                    answer_callback_query(callback_id, "⌛ نجوا منقضی شده! 🕒", True)
                    return

                if whisper_data.get("deleted", False):
                    if user_id == whisper_data["sender_id"] or (whisper_data["receiver_id"] and user_id == whisper_data["receiver_id"]) or (whisper_data["receiver_username"] and user_username == whisper_data["receiver_username"]):
                        answer_callback_query(callback_id, "نجوا توسط فرستنده پاک شده🤌🏼", True)
                    else:
                        answer_callback_query(callback_id, "خجالت بکش😐👊🏼", True)
                    return

                # چک کردن دسترسی بر اساس یوزرنیم یا آیدی
                is_allowed = user_id == whisper_data["sender_id"] or \
                            (whisper_data["receiver_id"] and user_id == whisper_data["receiver_id"]) or \
                            (whisper_data["receiver_username"] and user_username == whisper_data["receiver_username"])
                
                if is_allowed and user_id != whisper_data["sender_id"]:
                    whisper_data["receiver_views"].append(time.time())
                    save_whispers(whispers)
                elif not is_allowed:
                    if not any(user['id'] == user_id for user in whisper_data["curious_users"]):
                        whisper_data["curious_users"].append({"id": user_id, "name": user_display_name})
                        save_whispers(whispers)

                display_name = whisper_data["display_name"]
                message_text = f"گیرنده ({display_name})"
                code_content = format_diff_block_code(whisper_data)
                new_text = f"{message_text}\n```diff\n{code_content}\n```"

                reply_target = f"@{whisper_data['sender_username']}" if whisper_data["sender_username"] else str(whisper_data["sender_id"])
                keyboard = {
                    "inline_keyboard": [
                        [
                            {"text": "ببینم", "callback_data": f"show_{unique_id}"},
                            {"text": "پاسخ", "switch_inline_query_current_chat": f"{BOT_USERNAME} {reply_target} "}
                        ],
                        [
                            {"text": "حذف نجوا 💣", "callback_data": f"delete_{unique_id}"},
                            {"text": f"فضول‌ها [{len(whisper_data.get('curious_users', []))}]", "callback_data": f"curious_{unique_id}"}
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
                    response_text = f"پیام نجوا 💜\n{whisper_data['secret_message']}" if is_allowed else "خجالت بکش😐👊🏼"
                    answer_callback_query(callback_id, response_text, True)
                except Exception as e:
                    logger.error("Error editing message for whisper %s: %s", unique_id, str(e))
                    answer_callback_query(callback_id, "خطا رخ داد! لطفاً دوباره امتحان کنید.", True)

            elif data.startswith("delete_"):
                unique_id = data.split("_")[1]
                whisper_data = whispers.get(unique_id)

                if not whisper_data:
                    answer_callback_query(callback_id, "⌛ نجوا منقضی شده! 🕒", True)
                    return

                if user_id == whisper_data["sender_id"]:
                    whisper_data["deleted"] = True
                    save_whispers(whispers)
                    answer_callback_query(callback_id, "نجوا با موفقیت پاک شد! 💣", True)

                    display_name = whisper_data["display_name"]
                    message_text = f"گیرنده ({display_name})"
                    code_content = f"- {display_name} │ نجوا توسط فرستنده پاک شده🤌🏼"
                    new_text = f"{message_text}\n```diff\n{code_content}\n```"
                    keyboard = {
                        "inline_keyboard": [
                            [
                                {"text": "ببینم", "callback_data": f"show_{unique_id}"},
                                {"text": "پاسخ", "switch_inline_query_current_chat": f"{BOT_USERNAME} {reply_target} "}
                            ]
                        ]
                    }
                    try:
                        if inline_message_id:
                            edit_message_text(inline_message_id=inline_message_id, text=new_text, reply_markup=keyboard)
                        elif message:
                            edit_message_text(
                                chat_id=message["chat"]["id"],
                                message_id=message["message_id"],
                                text=new_text,
                                reply_markup=keyboard
                            )
                    except Exception as e:
                        logger.error("Error updating message for whisper %s: %s", unique_id, str(e))

                elif (whisper_data["receiver_id"] and user_id == whisper_data["receiver_id"]) or (whisper_data["receiver_username"] and user_username == whisper_data["receiver_username"]):
                    answer_callback_query(callback_id, "فقط فرستنده میتونه نجواشو پاک کنه🥱", True)
                else:
                    if not any(user['id'] == user_id for user in whisper_data["curious_users"]):
                        whisper_data["curious_users"].append({"id": user_id, "name": user_display_name})
                        save_whispers(whispers)

                    display_name = whisper_data["display_name"]
                    message_text = f"گیرنده ({display_name})"
                    code_content = format_diff_block_code(whisper_data)
                    new_text = f"{message_text}\n```diff\n{code_content}\n```"
                    keyboard = {
                        "inline_keyboard": [
                            [
                                {"text": "ببینم", "callback_data": f"show_{unique_id}"},
                                {"text": "پاسخ", "switch_inline_query_current_chat": f"{BOT_USERNAME} {reply_target} "}
                            ],
                            [
                                {"text": "حذف نجوا 💣", "callback_data": f"delete_{unique_id}"},
                                {"text": f"فضول‌ها [{len(whisper_data.get('curious_users', []))}]", "callback_data": f"curious_{unique_id}"}
                            ]
                        ]
                    }
                    try:
                        if inline_message_id:
                            edit_message_text(inline_message_id=inline_message_id, text=new_text, reply_markup=keyboard)
                        elif message:
                            edit_message_text(
                                chat_id=message["chat"]["id"],
                                message_id=message["message_id"],
                                text=new_text,
                                reply_markup=keyboard
                            )
                    except Exception as e:
                        logger.error("Error updating message for whisper %s: %s", unique_id, str(e))

                    answer_callback_query(callback_id, "خجالت بکش😐👊🏼", True)

            elif data.startswith("curious_"):
                unique_id = data.split("_")[1]
                whisper_data = whispers.get(unique_id)

                if not whisper_data:
                    answer_callback_query(callback_id, "⌛ نجوا منقضی شده! 🕒", True)
                    return

                is_allowed = user_id == whisper_data["sender_id"] or \
                            (whisper_data["receiver_id"] and user_id == whisper_data["receiver_id"]) or \
                            (whisper_data["receiver_username"] and user_username == whisper_data["receiver_username"])
                if is_allowed:
                    curious_users = whisper_data.get("curious_users", [])
                    if curious_users:
                        names = "\n".join([user["name"] for user in curious_users])
                        answer_callback_query(callback_id, f"فضول‌ها:\n{names}", True)
                    else:
                        answer_callback_query(callback_id, "هیچ فضولی نیست! 🌚", True)
                else:
                    answer_callback_query(callback_id, "خجالت بکش😐👊🏼", True)
        except Exception as e:
            logger.error("Error processing callback query: %s", str(e))