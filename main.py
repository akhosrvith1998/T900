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

# File for persistent whispers storage
WHISPERS_FILE = "whispers.json"

# Load whispers from file
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

# Save whispers to file
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
    """Convert username/ID to numeric ID"""
    if receiver_id.startswith('@'):
        username = receiver_id.lstrip('@')
        try:
            resp = requests.get(f"{URL}getChat", params={"chat_id": f"@{username}"}, timeout=5).json()
            if resp.get('ok'):
                user_id = str(resp['result']['id'])
                logger.info("Resolved username @%s to ID %s", username, user_id)
                return user_id
            else:
                logger.error("Failed to resolve username @%s: %s", username, resp.get('description', 'Unknown error'))
                return None
        except Exception as e:
            logger.error("Error resolving username @%s: %s", username, str(e))
            return None
    elif receiver_id.isdigit():
        logger.info("Using numeric ID: %s", receiver_id)
        return receiver_id
    logger.error("Invalid receiver ID format: %s", receiver_id)
    return None

def process_update(update):
    """Process updates received from Telegram"""
    global whispers

    if "inline_query" in update:
        inline_query = update["inline_query"]
        query = inline_query.get("query", "").strip()
        sender_id = str(inline_query['from']['id'])

        # Remove bot username if present
        if query.startswith(BOT_USERNAME):
            query = query[len(BOT_USERNAME):].strip()
        
        logger.info("Processing inline query from %s: '%s'", sender_id, query)

        # Process queries
        if query:
            # Split query into target and message
            parts = query.split(maxsplit=1)
            if len(parts) >= 1:  # At least target is provided
                target = parts[0]
                secret_message = parts[1] if len(parts) > 1 else ""
                
                receiver_id = resolve_user_id(target)
                
                if not receiver_id:
                    logger.warning("Invalid user ID or username: %s", target)
                    answer_inline_query(inline_query["id"], [{
                        "type": "article",
                        "id": "error",
                        "title": "❌ User not found!",
                        "input_message_content": {"message_text": "Error: Invalid user ID or username!"}
                    }])
                    return
                
                # Get user info
                try:
                    user_info = requests.get(f"{URL}getChat", params={"chat_id": receiver_id}, timeout=5).json()
                    if not user_info.get('ok'):
                        logger.error("Failed to get user info for %s: %s", receiver_id, user_info.get('description', 'Unknown error'))
                        answer_inline_query(inline_query["id"], [{
                            "type": "article",
                            "id": "error",
                            "title": "❌ User not found!",
                            "input_message_content": {"message_text": "Error: Unable to fetch user info!"}
                        }])
                        return
                    user_info = user_info['result']
                    first_name = user_info.get('first_name', 'Unknown')
                    username = user_info.get('username', '')
                    display_name = f"{user_info.get('first_name', 'Unknown')} {user_info.get('last_name', '')}".strip()
                    logger.info("User info for %s: display_name=%s, username=%s", receiver_id, display_name, username)
                except Exception as e:
                    logger.error("Error getting user info for %s: %s", receiver_id, str(e))
                    answer_inline_query(inline_query["id"], [{
                        "type": "article",
                        "id": "error",
                        "title": "❌ User not found!",
                        "input_message_content": {"message_text": "Error: Unable to fetch user info!"}
                    }])
                    return

                # Create message content (profile name with link)
                message_text = f"[{escape_markdown(display_name)}](tg://user?id={receiver_id})"
                code_content = f"{display_name} 0 | Not yet\n__________\nNothing"
                public_text = f"{message_text}\n```\n{code_content}\n```"

                # Create interactive buttons
                unique_id = uuid.uuid4().hex
                markup = {
                    "inline_keyboard": [
                        [
                            {"text": "Show", "callback_data": f"show_{unique_id}"},
                            {"text": "Reply", "switch_inline_query_current_chat": f"{inline_query['from']['id']}"}
                        ],
                        [
                            {"text": "Secret Room", "callback_data": f"secret_{unique_id}"}
                        ]
                    ]
                }

                # Store whisper data if there's a message
                if secret_message:
                    whispers[unique_id] = {
                        "sender_id": str(inline_query["from"]["id"]),
                        "sender_username": inline_query["from"].get("username", "").lstrip('@'),
                        "receiver_id": receiver_id,
                        "receiver_username": username.lstrip('@') if username else None,
                        "receiver_user_id": receiver_id,
                        "first_name": first_name,
                        "display_name": display_name,
                        "secret_message": secret_message,
                        "receiver_views": [],
                        "curious_users": []
                    }
                    save_whispers(whispers)

                    # Get and store profile photo
                    _, photo_url = get_user_profile_photo(int(receiver_id))
                    history_entry = {
                        "receiver_id": receiver_id,
                        "display_name": display_name,
                        "first_name": first_name,
                        "profile_photo_url": photo_url,
                        "time": time.time()
                    }
                    try:
                        save_history(inline_query['from']['id'], history_entry)
                        logger.info("Saved history for sender %s, receiver %s", sender_id, receiver_id)
                    except Exception as e:
                        logger.error("Error saving history: %s", str(e))

                    # Send result
                    answer_inline_query(inline_query["id"], [{
                        "type": "article",
                        "id": receiver_id,
                        "title": f"Send whisper to {display_name}",
                        "description": f"Message: {secret_message[:20]}...",
                        "thumb_url": photo_url,
                        "input_message_content": {
                            "message_text": public_text,
                            "parse_mode": "MarkdownV2"
                        },
                        "reply_markup": markup
                    }])
                    return

        # Show history and help
        results = [{
            "type": "article",
            "id": "help",
            "title": "Help",
            "input_message_content": {
                "message_text": "To send a whisper:\n@Bgnabot [ID/username] [message]"
            },
            "thumb_url": "https://via.placeholder.com/150"
        }]
        
        # Load and display history
        try:
            logger.info("Loading history for sender %s: %s", sender_id, history.get(sender_id, []))
            if sender_id in history:
                for item in history[sender_id]:
                    # Get updated profile photo
                    _, photo = get_user_profile_photo(int(item['receiver_id']))
                    results.append({
                        "type": "article",
                        "id": f"hist_{item['receiver_id']}",
                        "title": f"Send whisper to {item['display_name']}",
                        "description": f"Last sent: {get_irst_time(item['time'])}",
                        "thumb_url": photo,
                        "input_message_content": {
                            "message_text": f"[{escape_markdown(item['display_name'])}](tg://user?id={item['receiver_id']})\nTo send again: @Bgnabot {item['receiver_id']} [message]"
                        }
                    })
            else:
                logger.info("No history found for sender %s", sender_id)
        except Exception as e:
            logger.error("Error loading history: %s", str(e))

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
                answer_callback_query(callback_id, "⌛ Whisper expired! 🕒", True)
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
                # Check if user is already in curious_users
                if not any(user['id'] == user_id for user in whisper_data["curious_users"]):
                    whisper_data["curious_users"].append({"id": user_id, "name": user_display_name})
                    save_whispers(whispers)

            # Show profile name with link
            receiver_display_name = whisper_data["display_name"]
            receiver_id = whisper_data.get("receiver_id", "0")
            message_text = f"[{escape_markdown(receiver_display_name)}](tg://user?id={receiver_id})"
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
                        {"text": "Secret Room", "callback_data": f"secret_{unique_id}"}
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

                response_text = f"🔐 Whisper message:\n{whisper_data['secret_message']} 🎁" if is_allowed else "⚠️ This whisper isn't for you! 😕"
                answer_callback_query(callback_id, response_text, True)
            except Exception as e:
                logger.error("Error editing message: %s", str(e))
                answer_callback_query(callback_id, "An error occurred. Try again!", True)

        elif data.startswith("secret_"):
            unique_id = data.split("_")[1]
            whisper_data = whispers.get(unique_id)

            if not whisper_data:
                answer_callback_query(callback_id, "⌛ Whisper expired!", True)
                return

            user = callback["from"]
            user_id = str(user["id"])
            response_text = f"🔐 Secret Room:\n{whisper_data['secret_message']}\nOnly the sender can see this!" if user_id == whisper_data["sender_id"] else "⚠️ Only the sender can access the Secret Room! 😈"
            answer_callback_query(callback_id, response_text, True)