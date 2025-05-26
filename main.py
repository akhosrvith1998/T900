import json
import uuid
import time
import requests
import os
from utils import escape_markdown, get_irst_time, get_user_profile_photo, answer_inline_query, answer_callback_query, edit_message_text, format_block_code
from database import load_history, save_history, history
from cache import get_cached_inline_query, set_cached_inline_query
from logger import logger

WHISPERS_FILE = "whispers.json"

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
    """Resolve username/ID to numeric ID or keep as username"""
    if receiver_id.startswith('@'):
        username = receiver_id.lstrip('@').lower()
        if reply_to_message and 'from' in reply_to_message:
            return str(reply_to_message['from']['id'])
        logger.info("Using username directly: @%s", username)
        return receiver_id
    elif receiver_id.isdigit():
        logger.info("Using numeric ID: %s", receiver_id)
        return receiver_id
    logger.error("Invalid receiver ID format: %s", receiver_id)
    return None

def get_user_profile_photo(user_id):
    """Fetch the user's profile photo URL"""
    try:
        response = requests.get(f"{URL}getUserProfilePhotos", params={"user_id": user_id, "limit": 1}, timeout=10).json()
        if not response.get('ok'):
            logger.error("Failed to get profile photos for user %s: %s", user_id, response.get('description', 'Unknown error'))
            return None, "https://via.placeholder.com/150"
        photos = response['result']['photos']
        if not photos:
            logger.info("No profile photos found for user %s (possibly no photo set)", user_id)
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
    """Fetch user info (ID, username, display name, photo)"""
    if receiver_id.startswith('@'):
        return None, None, receiver_id, "https://via.placeholder.com/150"
    try:
        user_info = requests.get(f"{URL}getChat", params={"chat_id": receiver_id}, timeout=10).json()
        if not user_info.get('ok'):
            logger.error("Failed to get user info for %s: %s (Error code: %s)", 
                         receiver_id, user_info.get('description', 'Unknown error'), user_info.get('error_code', 'N/A'))
            return None, None, "Unknown", "https://via.placeholder.com/150"
        user_info = user_info['result']
        first_name = user_info.get('first_name', 'Unknown')
        username = user_info.get('username', '').lstrip('@') if user_info.get('username') else None
        display_name = f"{first_name} {user_info.get('last_name', '')}".strip()
        _, photo_url = get_user_profile_photo(int(receiver_id))
        return username, receiver_id, display_name, photo_url
    except Exception as e:
        logger.error("Error getting user info for %s: %s", receiver_id, str(e))
        return None, None, "Unknown", "https://via.placeholder.com/150"

def resolve_username_to_id(username):
    """Try to resolve a username to a numeric ID"""
    try:
        response = requests.get(f"{URL}getChat", params={"chat_id": f"@{username}"}, timeout=10).json()
        if response.get('ok'):
            user_info = response['result']
            return str(user_info['id']), user_info
        else:
            logger.error("Failed to resolve username @%s: %s", username, response.get('description', 'Unknown error'))
            return None, None
    except Exception as e:
        logger.error("Error resolving username @%s: %s", username, str(e))
        return None, None

def process_update(update):
    """Process updates received from Telegram"""
    global whispers

    if "inline_query" in update:
        inline_query = update["inline_query"]
        query = inline_query.get("query", "").strip()
        sender_id = str(inline_query['from']['id'])
        sender_username = inline_query['from'].get('username', '')
        chat_type = inline_query.get("chat_type")
        chat_id = inline_query.get("chat", {}).get("id")
        reply_to_message = None

        if query.startswith(BOT_USERNAME):
            query = query[len(BOT_USERNAME):].strip()
        
        logger.info("Processing inline query from %s in chat_type %s: '%s'", sender_id, chat_type, query)

        # Check if query starts with a valid username or ID
        parts = query.split(maxsplit=1)
        target = parts[0] if parts else ''
        secret_message = parts[1] if len(parts) > 1 else ""
        receiver_id = resolve_user_id(target, sender_id, sender_username, chat_id, reply_to_message) if target and (target.startswith('@') or target.isdigit()) else None

        display_name = None
        first_name = None
        username = None
        photo_url = "https://via.placeholder.com/150"

        if receiver_id and secret_message:
            if receiver_id.startswith('@'):
                display_name = receiver_id
                first_name = receiver_id.lstrip('@')
                username = receiver_id.lstrip('@')
            else:
                username, _, display_name, photo_url = fetch_user_info(receiver_id)
                first_name = display_name.split()[0] if display_name else "Unknown"

            message_text = f"[{escape_markdown(display_name)}](tg://user?id={receiver_id})" if not receiver_id.startswith('@') else escape_markdown(display_name)
            code_content = f"{display_name} 0 | Not yet\n__________\nNothing"
            public_text = f"{message_text}\n```\n{code_content}\n```"

            unique_id = uuid.uuid4().hex
            markup = {
                "inline_keyboard": [
                    [
                        {"text": "Show", "callback_data": f"show_{unique_id}"},
                        {"text": "Reply", "switch_inline_query_current_chat": f"{sender_id}"}
                    ],
                    [
                        {"text": "Secret Room 😈", "callback_data": f"secret_{unique_id}"}
                    ]
                ]
            }

            whispers[unique_id] = {
                "sender_id": sender_id,
                "sender_username": sender_username.lstrip('@') if sender_username else None,
                "receiver_id": receiver_id,
                "receiver_username": username,
                "receiver_user_id": receiver_id if not receiver_id.startswith('@') else None,
                "first_name": first_name,
                "display_name": display_name,
                "secret_message": secret_message,
                "receiver_views": [],
                "curious_users": []
            }
            save_whispers(whispers)

            history_entry = {
                "receiver_id": receiver_id,
                "display_name": display_name,
                "first_name": first_name,
                "profile_photo_url": photo_url,
                "time": time.time()
            }
            try:
                save_history(sender_id, history_entry)
                load_history()
                logger.info("Saved history for sender %s, receiver %s", sender_id, receiver_id)
            except Exception as e:
                logger.error("Error saving history: %s", str(e))

            answer_inline_query(inline_query["id"], [{
                "type": "article",
                "id": receiver_id,
                "title": f"Secret to💭 {display_name}",
                "description": f"Message: {secret_message[:20]}...",
                "thumb_url": photo_url,
                "input_message_content": {
                    "message_text": public_text,
                    "parse_mode": "MarkdownV2"
                },
                "reply_markup": markup
            }])
        else:
            # Show history even if text is typed, unless a valid target is specified
            results = [{
                "type": "article",
                "id": "help",
                "title": "Help",
                "input_message_content": {
                    "message_text": "To send a secret:\n@Bgnabot [ID/username] [message]\nOr reply to a message in a group with @Bgnabot [message]"
                },
                "thumb_url": "https://via.placeholder.com/150"
            }]
            
            try:
                logger.info("Loading history for sender %s from memory: %s", sender_id, history.get(sender_id, []))
                if sender_id in history and history[sender_id]:
                    for item in history[sender_id]:
                        photo = item.get("profile_photo_url", "https://via.placeholder.com/150")
                        receiver_id_numeric = item["receiver_id"] if item["receiver_id"].isdigit() else None
                        if receiver_id_numeric:
                            _, updated_photo = get_user_profile_photo(int(receiver_id_numeric))
                        else:
                            resolved_id, user_info = resolve_username_to_id(item["receiver_id"].lstrip('@')) if item["receiver_id"].startswith('@') else (None, None)
                            if resolved_id and user_info:
                                _, updated_photo = get_user_profile_photo(int(resolved_id))
                                item["display_name"] = f"{user_info.get('first_name', 'Unknown')} {user_info.get('last_name', '')}".strip()
                                item["first_name"] = user_info.get('first_name', 'Unknown')
                            else:
                                updated_photo = "https://via.placeholder.com/150"
                        if updated_photo != "https://via.placeholder.com/150" and updated_photo.startswith("https://api.telegram.org"):
                            item["profile_photo_url"] = updated_photo
                            save_history(sender_id, item)
                            load_history()
                            logger.info("Updated photo URL for receiver %s: %s", item["receiver_id"], updated_photo)
                        results.append({
                            "type": "article",
                            "id": f"hist_{item['receiver_id']}",
                            "title": f"Secret to💭 {item['display_name']}",
                            "description": f"Last sent: {get_irst_time(item['time'])}",
                            "thumb_url": item["profile_photo_url"],
                            "input_message_content": {
                                "message_text": f"[{escape_markdown(item['display_name'])}](tg://user?id={item['receiver_id'] if item['receiver_id'].isdigit() else '0'})"  
                                               f"\nTo send again: @Bgnabot {item['receiver_id']} [message]"
                            }
                        })
                else:
                    logger.warning("No valid history found for sender %s in memory: %s", sender_id, history.get(sender_id, []))
            except Exception as e:
                logger.error("Error loading history: %s", str(e))

            answer_inline_query(inline_query["id"], results)

    elif "message" in update and "reply_to_message" in update["message"] and update["message"]["chat"]["type"] in ["group", "supergroup"]:
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
            display_name = f"{first_name} {replied_user.get('last_name', '')}".strip()
            _, photo_url = get_user_profile_photo(int(receiver_id))
            logger.info("Detected reply to user %s (%s) in group chat %s with message: %s", display_name, receiver_id, chat_id, secret_message)

            if secret_message:
                message_text = f"[{escape_markdown(display_name)}](tg://user?id={receiver_id})"
                code_content = f"{display_name} 0 | Not yet\n__________\nNothing"
                public_text = f"{message_text}\n```\n{code_content}\n```"

                unique_id = uuid.uuid4().hex
                markup = {
                    "inline_keyboard": [
                        [
                            {"text": "Show", "callback_data": f"show_{unique_id}"},
                            {"text": "Reply", "switch_inline_query_current_chat": f"{sender_id}"}
                        ],
                        [
                            {"text": "Secret Room 😈", "callback_data": f"secret_{unique_id}"}
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
                    "curious_users": []
                }
                save_whispers(whispers)

                history_entry = {
                    "receiver_id": receiver_id,
                    "display_name": display_name,
                    "first_name": first_name,
                    "profile_photo_url": photo_url,
                    "time": time.time()
                }
                try:
                    save_history(sender_id, history_entry)
                    load_history()
                    logger.info("Saved history for sender %s, receiver %s", sender_id, receiver_id)
                except Exception as e:
                    logger.error("Error saving history: %s", str(e))

                requests.post(f"{URL}sendMessage", json={
                    "chat_id": chat_id,
                    "text": public_text,
                    "parse_mode": "MarkdownV2",
                    "reply_markup": markup
                })

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
                answer_callback_query(callback_id, "⌛ Whisper expired! 🕒", True)
                return

            user = callback["from"]
            user_id = str(user["id"])
            username = user.get("username", "").lstrip('@').lower() if user.get("username") else None
            first_name = user.get("first_name", "")
            last_name = user.get("last_name", "")
            user_display_name = f"{first_name} {last_name}".strip() if last_name else first_name

            receiver_id = whisper_data["receiver_id"]
            is_allowed = (
                user_id == whisper_data["sender_id"] or
                (whisper_data["receiver_user_id"] and user_id == whisper_data["receiver_user_id"]) or
                (whisper_data["receiver_username"] and username and username.lower() == whisper_data["receiver_username"].lower())
            )

            photo_url = "https://via.placeholder.com/150"
            if receiver_id.startswith('@') and is_allowed:
                resolved_id, user_info = resolve_username_to_id(receiver_id.lstrip('@'))
                if resolved_id:
                    new_receiver_id = resolved_id
                    first_name = user_info.get('first_name', 'Unknown')
                    username = user_info.get('username', '').lstrip('@') if user_info.get('username') else None
                    display_name = f"{first_name} {user_info.get('last_name', '')}".strip()
                    _, photo_url = get_user_profile_photo(int(new_receiver_id))
                    whisper_data["receiver_id"] = new_receiver_id
                    whisper_data["receiver_user_id"] = new_receiver_id
                    whisper_data["receiver_username"] = username
                    whisper_data["display_name"] = display_name
                    whisper_data["first_name"] = first_name
                    save_whispers(whispers)
                    history_entry = {
                        "receiver_id": new_receiver_id,
                        "display_name": display_name,
                        "first_name": first_name,
                        "profile_photo_url": photo_url,
                        "time": time.time()
                    }
                    save_history(whisper_data["sender_id"], history_entry)
                    load_history()
                    logger.info("Updated history with resolved user info for %s", new_receiver_id)
                else:
                    logger.warning("Could not resolve username %s to ID", receiver_id)

            is_allowed = (
                user_id == whisper_data["sender_id"] or
                (whisper_data["receiver_user_id"] and user_id == whisper_data["receiver_user_id"]) or
                (whisper_data["receiver_username"] and username and username.lower() == whisper_data["receiver_username"].lower())
            )

            if is_allowed and user_id != whisper_data["sender_id"]:
                whisper_data["receiver_views"].append(time.time())
                save_whispers(whispers)
            elif not is_allowed:
                if not any(user['id'] == user_id for user in whisper_data["curious_users"]):
                    whisper_data["curious_users"].append({"id": user_id, "name": user_display_name})
                    save_whispers(whispers)
                    logger.info("Added curious user %s (%s) to whisper %s", user_display_name, user_id, unique_id)

            receiver_display_name = whisper_data["display_name"]
            receiver_id = whisper_data.get("receiver_id", "0")
            message_text = f"[{escape_markdown(receiver_display_name)}](tg://user?id={receiver_id})" if not receiver_id.startswith('@') else escape_markdown(receiver_display_name)
            code_content = format_block_code(whisper_data)
            new_text = f"{message_text}\n```\n{code_content}\n```"

            reply_target = f"@{whisper_data['sender_username']}" if whisper_data["sender_username"] else str(whisper_data["sender_id"])
            reply_text = f"{reply_target} "
            keyboard = {
                "inline_keyboard": [
                    [
                        {"text": "Show", "callback_data": f"show_{unique_id}"},
                        {"text": "Reply", "switch_inline_query_current_chat": reply_text}
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
                logger.info("Successfully updated message for whisper %s", unique_id)
                response_text = f"Secret message 💜\n{whisper_data['secret_message']}" if is_allowed else "⚠️ این پیام برای شما نیست!"
                answer_callback_query(callback_id, response_text, True)
            except Exception as e:
                logger.error("Error editing message for whisper %s: %s", unique_id, str(e))
                answer_callback_query(callback_id, "خطا رخ داد! لطفاً دوباره امتحان کنید.", True)

        elif data.startswith("secret_"):
            unique_id = data.split("_")[1]
            whisper_data = whispers.get(unique_id)

            if not whisper_data:
                answer_callback_query(callback_id, "⌛ پیام منقضی شده!", True)
                return

            user = callback["from"]
            user_id = str(user["id"])
            username = user.get("username", "").lstrip('@').lower() if user.get("username") else None
            first_name = user.get("first_name", "")
            last_name = user.get("last_name", "")
            user_display_name = f"{first_name} {last_name}".strip() if last_name else first_name

            is_allowed = (
                user_id == whisper_data["sender_id"] or
                (whisper_data["receiver_user_id"] and user_id == whisper_data["receiver_user_id"]) or
                (whisper_data["receiver_username"] and username and username.lower() == whisper_data["receiver_username"].lower())
            )

            if is_allowed:
                response_text = "به زودی"
            else:
                response_text = "⚠️ فقط فرستنده و گیرنده می‌توانند دسترسی داشته باشند!"
                if not any(user['id'] == user_id for user in whisper_data["curious_users"]):
                    whisper_data["curious_users"].append({"id": user_id, "name": user_display_name})
                    save_whispers(whispers)
                    logger.info("Added curious user %s (%s) to whisper %s", user_display_name, user_id, unique_id)

                    # Update the message to reflect the new curious_users
                    receiver_display_name = whisper_data["display_name"]
                    receiver_id = whisper_data.get("receiver_id", "0")
                    message_text = f"[{escape_markdown(receiver_display_name)}](tg://user?id={receiver_id})" if not receiver_id.startswith('@') else escape_markdown(receiver_display_name)
                    code_content = format_block_code(whisper_data)
                    new_text = f"{message_text}\n```\n{code_content}\n```"
                    keyboard = {
                        "inline_keyboard": [
                            [
                                {"text": "Show", "callback_data": f"show_{unique_id}"},
                                {"text": "Reply", "switch_inline_query_current_chat": f"@{whisper_data['sender_username']}" if whisper_data["sender_username"] else str(whisper_data["sender_id"])}
                            ],
                            [
                                {"text": "Secret Room 😈", "callback_data": f"secret_{unique_id}"}
                            ]
                        ]
                    }
                    try:
                        if inline_message_id:
                            edit_message_text(inline_message_id=inline_message_id, text=new_text, reply_markup=keyboard)
                            logger.info("Updated message for whisper %s after adding curious user", unique_id)
                    except Exception as e:
                        logger.error("Error updating message for whisper %s: %s", unique_id, str(e))

            answer_callback_query(callback_id, response_text, True)