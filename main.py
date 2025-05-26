import json
import uuid
import time
import requests
import os
from utils import escape_markdown, get_irst_time, answer_inline_query, answer_callback_query, edit_message_text, format_block_code
from cache import get_cached_inline_query, set_cached_inline_query
from logger import logger

WHISPERS_FILE = "whispers.json"
HISTORY_FILE = "history.json"  # فقط برای سازگاری نگه داشته شده

USER_INFO_CACHE = {}

TEHRAN_OFFSET = 3.5 * 3600

def load_history():
    try:
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.error("Error loading history from file: %s", str(e))
        return {}

history = load_history()

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

def resolve_user_id(receiver_id, sender_id=None, sender_username=None, chat_id=None, reply_to_message=None):
    try:
        if receiver_id.startswith('@'):
            username = receiver_id.lstrip('@').lower()
            if not username:  # اگه یوزرنیم خالی باشه، null برگردون
                return None
            if reply_to_message and 'from' in reply_to_message:
                return str(reply_to_message['from']['id'])
            logger.info("Using username directly: @%s", username)
            return f"@{username}"  # یوزرنیم خام رو نگه دار
        elif receiver_id.isdigit():
            logger.info("Using numeric ID: %s", receiver_id)
            return receiver_id
        logger.error("Invalid receiver ID format: %s", receiver_id)
        return None
    except Exception as e:
        logger.error("Error resolving user ID: %s", str(e))
        return None

def get_user_profile_photo(user_id):
    try:
        response = requests.get(f"{URL}getUserProfilePhotos", params={"user_id": user_id, "limit": 1}, timeout=10).json()
        if not response.get('ok'):
            logger.error("Failed to get profile photos for user %s: %s (Error code: %s)", 
                         user_id, response.get('description', 'Unknown error'), response.get('error_code', 'N/A'))
            return None, "https://via.placeholder.com/150"
        photos = response['result']['photos']
        if not photos:
            logger.info("No profile photos found for user %s", user_id)
            return None, "https://via.placeholder.com/150"
        photo = photos[0][-1]
        file_id = photo['file_id']
        file_response = requests.get(f"{URL}getFile", params={"file_id": file_id}, timeout=10).json()
        if not file_response.get('ok'):
            logger.error("Failed to get file path for file_id %s: %s", file_id, file_response.get('description', 'Unknown error'))
            return None, "https://via.placeholder.com/150"
        file_path = file_response['result']['file_path']
        photo_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"
        logger.info("Successfully retrieved photo URL for user %s: %s", user_id, photo_url)
        return file_id, photo_url
    except Exception as e:
        logger.error("Error getting profile photo for user %s: %s", user_id, str(e))
        return None, "https://via.placeholder.com/150"

def fetch_user_info(receiver_id):
    try:
        if receiver_id in USER_INFO_CACHE:
            cached_info = USER_INFO_CACHE[receiver_id]
            logger.info("Using cached user info for %s: %s", receiver_id, cached_info)
            return cached_info['username'], receiver_id, cached_info['display_name'], cached_info['photo_url']

        if receiver_id.isdigit():
            user_info = requests.get(f"{URL}getChat", params={"chat_id": receiver_id}, timeout=10).json()
        else:  # اگه یوزرنیم باشه
            resolved_id, user_info = resolve_username_to_id(receiver_id.lstrip('@'))
            if resolved_id:
                receiver_id = resolved_id
                user_info = requests.get(f"{URL}getChat", params={"chat_id": resolved_id}, timeout=10).json()
            else:
                return None, receiver_id, receiver_id.lstrip('@'), "https://via.placeholder.com/150"

        if not user_info.get('ok'):
            logger.error("Failed to get user info for %s: %s (Error code: %s)", 
                         receiver_id, user_info.get('description', 'Unknown error'), user_info.get('error_code', 'N/A'))
            return None, receiver_id, str(receiver_id), None
        user_info = user_info['result']
        first_name = user_info.get('first_name', 'Unknown')
        username = user_info.get('username', '').lstrip('@') if user_info.get('username') else None
        display_name = f"{first_name} {user_info.get('last_name', '')}".strip() if not username else f"@{username}"
        _, photo_url = get_user_profile_photo(int(receiver_id))

        USER_INFO_CACHE[receiver_id] = {
            "username": username,
            "display_name": display_name,
            "photo_url": photo_url
        }
        logger.info("Cached user info for %s: %s", receiver_id, USER_INFO_CACHE[receiver_id])
        return username, receiver_id, display_name, photo_url
    except Exception as e:
        logger.error("Error getting user info for %s: %s", receiver_id, str(e))
        return None, receiver_id, str(receiver_id), None

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
    curious_users = whisper_data.get("curious_users", [])
    
    view_count = len(receiver_views)
    last_seen_time = receiver_views[-1] if receiver_views else None
    
    if last_seen_time:
        tehran_time = last_seen_time + TEHRAN_OFFSET
        seen_text = f"گیرنده [{view_count}] خونده | {time.strftime('%H:%M', time.localtime(tehran_time))}"
    else:
        seen_text = "هنوز نخونده"
    
    block_lines = [f"- {seen_text}"]
    
    return "\n".join(block_lines)

def process_update(update):
    logger.info("Bot processing update: %s", update)
    global whispers

    if "inline_query" in update:
        inline_query = update["inline_query"]
        query = inline_query.get("query", "").strip()
        sender_id = str(inline_query['from']['id'])
        sender_username = inline_query['from'].get('username', '')
        chat_type = inline_query.get("chat_type", "unknown")
        chat_id = inline_query.get("chat", {}).get("id")
        reply_to_message = None

        if query.startswith(BOT_USERNAME):
            query = query[len(BOT_USERNAME):].strip()
        
        logger.info("Processing inline query from %s in chat_type %s: '%s'", sender_id, chat_type, query)

        parts = query.split(maxsplit=1)
        target = parts[0] if parts else ''
        secret_message = parts[1] if len(parts) > 1 else ''

        receiver_id = resolve_user_id(target, sender_id, sender_username, chat_id, reply_to_message) if target else None

        display_name = None
        first_name = None
        username = None
        photo_url = "https://via.placeholder.com/150"

        # Case 1: Valid receiver ID/username + secret message
        if receiver_id and secret_message:
            try:
                username, receiver_id, display_name, photo_url = fetch_user_info(receiver_id)
                display_name = f"@{username}" if username else display_name
                message_text = f"گیرنده ({display_name})"
                code_content = format_diff_block_code({"display_name": display_name, "receiver_views": [], "curious_users": []})
                public_text = f"{message_text}\n```diff\n{code_content}\n```"

                unique_id = uuid.uuid4().hex
                markup = {
                    "inline_keyboard": [
                        [
                            {"text": "ببینم", "callback_data": f"show_{unique_id}"},
                            {"text": "پاسخ", "switch_inline_query_current_chat": f"{sender_id}"}
                        ],
                        [
                            {"text": "حذف نجوا 💣", "callback_data": f"delete_{unique_id}"},
                            {"text": f"فضول‌ها [{len(whispers.get(unique_id, {}).get('curious_users', []))}]", "callback_data": f"curious_{unique_id}"}
                        ]
                    ]
                }

                whispers[unique_id] = {
                    "sender_id": sender_id,
                    "sender_username": sender_username.lstrip('@') if sender_username else None,
                    "receiver_id": receiver_id,
                    "receiver_username": username,
                    "receiver_user_id": receiver_id if receiver_id.isdigit() else None,
                    "first_name": first_name,
                    "display_name": display_name,
                    "secret_message": secret_message,
                    "receiver_views": [],
                    "curious_users": [],
                    "deleted": False
                }
                save_whispers(whispers)
                logger.info("Sending inline query response for whisper %s", unique_id)
                answer_inline_query(inline_query["id"], [{
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
                }])
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

        # Case 2: Only receiver ID/username provided, no secret message yet
        elif receiver_id and not secret_message:
            try:
                username, receiver_id, display_name, photo_url = fetch_user_info(receiver_id)
                display_name = f"@{username}" if username else display_name
                results = [
                    {
                        "type": "article",
                        "id": f"target_{receiver_id}",
                        "title": "حالا متن نجوا رو بنویس",
                        "description": "پیام خودت رو وارد کن...",
                        "thumb_url": photo_url,
                        "input_message_content": {
                            "message_text": f"ارسال نجوا به گیرنده ({display_name})\nلطفاً پیام خود را وارد کنید.",
                            "parse_mode": "MarkdownV2"
                        },
                        "reply_markup": {
                            "inline_keyboard": [[
                                {"text": f"ارسال نجوا (به {display_name})", "switch_inline_query_current_chat": f"{BOT_USERNAME} {receiver_id} "}
                            ]]
                        }
                    }
                ]
                logger.info("Sending receiver selection response for %s", receiver_id)
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
                results = [
                    {
                        "type": "article",
                        "id": "guide",
                        "title": "( آیدی رو تایپ کن یا از ریپلای استفاده کن )",
                        "input_message_content": {
                            "message_text": "یه چیزی تایپ کن تا بتونم نجوا رو آماده کنم!\nمثال: @Bgnabot @username پیامت\nیا روی پیام کسی ریپلای کن و @Bgnabot پیامت رو بنویس."
                        },
                        "thumb_url": "https://via.placeholder.com/150"
                    }
                ]
                logger.info("Sending guide response")
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
                replied_user = message["reply_to_message"]["from"]
                receiver_id = str(replied_user["id"])
                first_name = replied_user.get("first_name", "Unknown")
                username = replied_user.get("username", "").lstrip('@') if replied_user.get("username") else None
                display_name = f"@{username}" if username else first_name
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
                                {"text": "پاسخ", "switch_inline_query_current_chat": f"{sender_id}"}
                            ],
                            [
                                {"text": "حذف نجوا 💣", "callback_data": f"delete_{unique_id}"},
                                {"text": f"فضول‌ها [{len(whispers.get(unique_id, {}).get('curious_users', []))}]", "callback_data": f"curious_{unique_id}"}
                            ]
                        ]
                    }

                    whispers[unique_id] = {
                        "sender_id": sender_id,
                        "sender_username": sender_username.lstrip('@') if sender_username else None,
                        "receiver_id": receiver_id,
                        "receiver_username": username,
                        "receiver_user_id": receiver_id,
                        "first_name": first_name,
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
                        logger.info("Whisper sent successfully for %s", unique_id)
                    else:
                        logger.error("Failed to send whisper: %s", response.text)
        except Exception as e:
            logger.error("Error processing group message: %s", str(e))

    elif "callback_query" in update:
        try:
            callback = update["callback_query"]
            callback_id = callback["id"]
            data = callback["data"]
            message = callback.get("message")
            inline_message_id = callback.get("inline_message_id")

            user = callback["from"]
            user_id = str(user["id"])
            username = user.get("username", "").lstrip('@').lower() if user.get("username") else None
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
                    if (user_id == whisper_data["sender_id"] or
                        (whisper_data["receiver_user_id"] and user_id == whisper_data["receiver_user_id"])):
                        answer_callback_query(callback_id, "نجوا توسط فرستنده پاک شده🤌🏼", True)
                    else:
                        answer_callback_query(callback_id, "خجالت بکش😐👊🏼", True)
                    return

                is_allowed = (
                    user_id == whisper_data["sender_id"] or
                    (whisper_data["receiver_user_id"] and user_id == whisper_data["receiver_user_id"])
                )

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
                reply_text = f"{reply_target} "
                keyboard = {
                    "inline_keyboard": [
                        [
                            {"text": "ببینم", "callback_data": f"show_{unique_id}"},
                            {"text": "پاسخ", "switch_inline_query_current_chat": reply_text}
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

                is_allowed = (
                    user_id == whisper_data["sender_id"] or
                    (whisper_data["receiver_user_id"] and user_id == whisper_data["receiver_user_id"])
                )

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
                                {"text": "پاسخ", "switch_inline_query_current_chat": f"@{whisper_data['sender_username']}" if whisper_data["sender_username"] else str(whisper_data["sender_id"])}
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

                elif is_allowed and user_id != whisper_data["sender_id"]:
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
                                {"text": "پاسخ", "switch_inline_query_current_chat": f"@{whisper_data['sender_username']}" if whisper_data["sender_username"] else str(whisper_data["sender_id"])}
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

                is_allowed = (
                    user_id == whisper_data["sender_id"] or
                    (whisper_data["receiver_user_id"] and user_id == whisper_data["receiver_user_id"])
                )

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