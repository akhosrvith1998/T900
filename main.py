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
            return json.load(f)
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

def resolve_user_id(receiver_id, sender_id=None, chat_id=None):
    """Improved user resolution with better group handling"""
    if receiver_id.startswith('@'):
        username = receiver_id[1:].lower()
        try:
            # Try direct resolution first
            resp = requests.get(f"{URL}getChat", params={"chat_id": receiver_id}, timeout=10).json()
            if resp.get('ok'):
                return str(resp['result']['id'])
            
            # Fallback to chat member check if in group
            if chat_id:
                resp = requests.get(f"{URL}getChatMember", 
                                  params={"chat_id": chat_id, "user_id": receiver_id}, 
                                  timeout=10).json()
                if resp.get('ok'):
                    return str(resp['result']['user']['id'])
            
            logger.error("User resolution failed for %s: %s", receiver_id, resp.get('description'))
            return None
            
        except Exception as e:
            logger.error("Resolution error for %s: %s", receiver_id, str(e))
            return None
    
    return receiver_id if receiver_id.isdigit() else None

def process_update(update):
    global whispers

    if "inline_query" in update:
        inline_query = update["inline_query"]
        query = inline_query.get("query", "").strip()
        sender_id = str(inline_query['from']['id'])
        chat_type = inline_query.get("chat_type")
        chat_id = inline_query.get("chat", {}).get("id")

        if query.startswith(BOT_USERNAME):
            query = query[len(BOT_USERNAME):].strip()
        
        logger.info("Processing inline query: '%s'", query)

        if not query:
            # Show history
            results = [{
                "type": "article",
                "id": "help",
                "title": "کمک",
                "input_message_content": {
                    "message_text": "برای ارسال نجوا:\n@Bgnabot [آیدی/یوزرنیم] [پیام]\nیا در گروه به پیام کاربر ریپلای کن و بنویس @Bgnabot [پیام]"
                },
                "thumb_url": "https://via.placeholder.com/150"
            }]
            
            if sender_id in history:
                for item in history[sender_id][-5:]:  # Show last 5
                    _, photo = get_user_profile_photo(int(item['receiver_id']))
                    results.append({
                        "type": "article",
                        "id": f"hist_{item['receiver_id']}",
                        "title": f"ارسال مجدد به {item['display_name']}",
                        "description": f"آخرین ارسال: {get_irst_time(item['time'])}",
                        "thumb_url": photo,
                        "input_message_content": {
                            "message_text": f"@{BOT_USERNAME[1:]} {item['receiver_id']} [پیام]"
                        }
                    })
            return answer_inline_query(inline_query["id"], results)

        parts = query.split(maxsplit=1)
        if len(parts) < 2:
            return answer_inline_query(inline_query["id"], [{
                "type": "article",
                "id": "help",
                "title": "فرمت نادرست!",
                "input_message_content": {
                    "message_text": "فرمت صحیح:\n@Bgnabot [آیدی/یوزرنیم] [پیام]"
                }
            }])

        target, secret_message = parts
        receiver_id = resolve_user_id(target, sender_id, chat_id)

        if not receiver_id:
            return answer_inline_query(inline_query["id"], [{
                "type": "article",
                "id": "error",
                "title": "❗ کاربر یافت نشد!",
                "input_message_content": {
                    "message_text": "خطا: کاربر مورد نظر یافت نشد یا ربات دسترسی ندارد!"
                }
            }])

        try:
            user_info = requests.get(f"{URL}getChat", params={"chat_id": receiver_id}, timeout=10).json()
            if not user_info.get('ok'):
                raise Exception(user_info.get('description'))
            
            user = user_info['result']
            display_name = user.get('first_name', '') + " " + user.get('last_name', '')
            display_name = display_name.strip() or user.get('username', 'Unknown')
            _, photo_url = get_user_profile_photo(int(receiver_id))

        except Exception as e:
            logger.error("User info error: %s", str(e))
            return answer_inline_query(inline_query["id"], [{
                "type": "article",
                "id": "error",
                "title": "❗ خطا در دریافت اطلاعات",
                "input_message_content": {
                    "message_text": "خطا در دریافت اطلاعات کاربر!"
                }
            }])

        # Create whisper
        unique_id = uuid.uuid4().hex
        markup = {
            "inline_keyboard": [
                [
                    {"text": "نمایش پیام", "callback_data": f"show_{unique_id}"},
                    {"text": "پاسخ", "switch_inline_query_current_chat": f"{sender_id} "}
                ]
            ]
        }

        whispers[unique_id] = {
            "sender_id": sender_id,
            "receiver_id": receiver_id,
            "display_name": display_name,
            "secret_message": secret_message,
            "receiver_views": [],
            "curious_users": []
        }
        save_whispers(whispers)

        # Save to history
        history_entry = {
            "receiver_id": receiver_id,
            "display_name": display_name,
            "time": time.time()
        }
        save_history(sender_id, history_entry)

        # Prepare result
        message_text = f"🔒 یک پیام محرمانه برای [{escape_markdown(display_name)}](tg://user?id={receiver_id})"
        return answer_inline_query(inline_query["id"], [{
            "type": "article",
            "id": unique_id,
            "title": f"ارسال نجوا به {display_name}",
            "description": f"پیام: {secret_message[:30]}...",
            "thumb_url": photo_url,
            "input_message_content": {
                "message_text": message_text,
                "parse_mode": "MarkdownV2"
            },
            "reply_markup": markup
        }])

    elif "message" in update and "reply_to_message" in update["message"]:
        msg = update["message"]
        if msg["chat"]["type"] not in ["group", "supergroup"]:
            return

        replied_user = msg["reply_to_message"]["from"]
        receiver_id = str(replied_user["id"])
        secret_message = msg.get("text", "").replace(BOT_USERNAME, "", 1).strip()

        if not secret_message:
            return

        sender_id = str(msg["from"]["id"])
        display_name = replied_user.get("first_name", "") + " " + replied_user.get("last_name", "")
        display_name = display_name.strip() or replied_user.get("username", "Unknown")
        
        # Create whisper
        unique_id = uuid.uuid4().hex
        markup = {
            "inline_keyboard": [
                [
                    {"text": "نمایش پیام", "callback_data": f"show_{unique_id}"},
                    {"text": "پاسخ", "switch_inline_query_current_chat": f"{sender_id} "}
                ]
            ]
        }

        whispers[unique_id] = {
            "sender_id": sender_id,
            "receiver_id": receiver_id,
            "display_name": display_name,
            "secret_message": secret_message,
            "receiver_views": [],
            "curious_users": []
        }
        save_whispers(whispers)

        # Send message to group
        message_text = f"🔒 یک پیام محرمانه برای [{escape_markdown(display_name)}](tg://user?id={receiver_id})"
        requests.post(f"{URL}sendMessage", json={
            "chat_id": msg["chat"]["id"],
            "text": message_text,
            "parse_mode": "MarkdownV2",
            "reply_markup": markup
        })

    elif "callback_query" in update:
        callback = update["callback_query"]
        data = callback["data"]
        
        if data.startswith("show_"):
            unique_id = data.split("_")[1]
            whisper = whispers.get(unique_id)
            
            if not whisper:
                return answer_callback_query(callback["id"], "⌛ پیام منقضی شده!", True)

            user_id = str(callback["from"]["id"])
            is_receiver = user_id == whisper["receiver_id"]
            is_sender = user_id == whisper["sender_id"]

            if is_receiver:
                whisper["receiver_views"].append(time.time())
                save_whispers(whispers)
            
            response_text = whisper["secret_message"] if is_receiver or is_sender else "🔐 این پیام برای شما نیست!"
            
            # Update message
            views_count = len(whisper["receiver_views"])
            display_text = f"🔐 پیام محرمانه ({views_count} بار مشاهده شده)\n{response_text if (is_receiver or is_sender) else '〽️ شما مجوز مشاهده ندارید!'}"
            
            try:
                edit_message_text(
                    inline_message_id=callback["inline_message_id"],
                    text=display_text,
                    reply_markup=callback["message"].get("reply_markup")
                )
            except:
                pass
            
            return answer_callback_query(callback["id"], response_text[:200], show_alert=True)

    return {"ok": True}