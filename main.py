import json
import uuid
import threading
from utils import escape_markdown, get_irst_time, get_user_profile_photo, answer_inline_query, answer_callback_query, edit_message_text, format_block_code
from database import load_history, save_history, history
from cache import get_cached_inline_query, set_cached_inline_query
from logger import logger

whispers = {}
BOT_USERNAME = "@Bgnabot"

def process_update(update):
    """پردازش آپدیت‌های دریافتی از تلگرام"""
    if "inline_query" in update:
        inline_query = update["inline_query"]
        query_id = inline_query["id"]
        raw_query = inline_query.get("query", "").strip()
        query_text = raw_query.replace(BOT_USERNAME, "", 1).strip()
        sender = inline_query["from"]
        sender_id = str(sender["id"])

        # چک کردن کش
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
            "description": "همیشه فعال!"
        }

        results = [base_result]
        # نمایش تاریخچه برای کوئری خالی یا کوئری‌های تک‌کلمه‌ای
        if sender_id in history:
            for receiver in sorted(history[sender_id], key=lambda x: x["display_name"]):
                result = {
                    "type": "article",
                    "id": f"history_{receiver['receiver_id']}",
                    "title": f"نجوا به {receiver['display_name']} ✨",
                    "input_message_content": {
                        "message_text": f"📩 پیام خود را برای {receiver['display_name']} وارد کنید"
                    },
                    "description": f"ارسال نجوا به {receiver['first_name']}",
                    "thumb_url": receiver.get("profile_photo_url", "")
                }
                results.append(result)
        
        if not query_text:
            set_cached_inline_query(sender_id, query_text, results)
            answer_inline_query(query_id, results)
            return

        try:
            parts = query_text.split(" ", 1)
            # اگر فقط متن وارد شده باشد، نجوا برای گیرنده از تاریخچه ارسال می‌شود
            if len(parts) == 1 and sender_id in history:
                secret_message = parts[0].strip()
                results = [base_result]
                for receiver in sorted(history[sender_id], key=lambda x: x["display_name"]):
                    unique_id = uuid.uuid4().hex
                    receiver_id = receiver['receiver_id']
                    receiver_username = receiver_id.lstrip('@').lower() if receiver_id.startswith('@') else None
                    receiver_user_id = int(receiver_id) if receiver_id.isdigit() else None
                    receiver_display_name = receiver['display_name']

                    profile_photo = get_user_profile_photo(receiver_user_id) if receiver_user_id else None
                    profile_photo_url = f"https://api.telegram.org/file/bot7889701836:AAECLBRjjDadhpgJreOctpo5Jc72ekDKNjc/{profile_photo}" if profile_photo else ""

                    sender_username = sender.get("username", "").lstrip('@').lower() if sender.get("username") else None
                    sender_display_name = f"{sender.get('first_name', '')} {sender.get('last_name', '')}".strip() if sender.get('last_name') else sender.get('first_name', '')

                    # به‌روزرسانی profile_photo_url در تاریخچه
                    receiver["profile_photo_url"] = profile_photo_url
                    save_history(sender_id, receiver)

                    whispers[unique_id] = {
                        "sender_id": sender_id,
                        "sender_username": sender_username,
                        "sender_display_name": sender_display_name,
                        "receiver_username": receiver_username,
                        "receiver_user_id": receiver_user_id,
                        "receiver_display_name": receiver_display_name,
                        "secret_message": secret_message,
                        "curious_users": set(),
                        "receiver_views": []
                    }

                    receiver_id_display = escape_markdown(receiver_display_name)
                    code_content = format_block_code(whispers[unique_id])
                    public_text = f"{receiver_id_display}\n\n```{code_content}```"
                    reply_target = f"@{sender_username}" if sender_username else str(sender_id)
                    reply_text = f"{reply_target} "
                    keyboard = {
                        "inline_keyboard": [[
                            {"text": "👁️ show", "callback_data": f"show|{unique_id}"},
                            {"text": "🗨️ reply", "switch_inline_query_current_chat": reply_text}
                        ]]
                    }

                    results.append({
                        "type": "article",
                        "id": unique_id,
                        "title": f"🔒 نجوا به {receiver_display_name} 🎉",
                        "input_message_content": {
                            "message_text": public_text,
                            "parse_mode": "MarkdownV2"
                        },
                        "reply_markup": keyboard,
                        "description": f"پیام: {secret_message[:15]}...",
                        "thumb_url": receiver.get("profile_photo_url", "")
                    })
                set_cached_inline_query(sender_id, query_text, results)
                answer_inline_query(query_id, results)
                return

            # اگر گیرنده و متن وارد شده باشد
            if len(parts) < 2:
                set_cached_inline_query(sender_id, query_text, results)
                answer_inline_query(query_id, results)
                return

            receiver_id = parts[0]
            secret_message = parts[1].strip()

            receiver_username = None
            receiver_user_id = None

            if receiver_id.startswith('@'):
                receiver_username = receiver_id.lstrip('@').lower()
            elif receiver_id.isdigit():
                receiver_user_id = int(receiver_id)
            else:
                raise ValueError("شناسه گیرنده نامعتبر")

            unique_id = uuid.uuid4().hex
            sender_username = sender.get("username", "").lstrip('@').lower() if sender.get("username") else None
            sender_display_name = f"{sender.get('first_name', '')} {sender.get('last_name', '')}".strip() if sender.get('last_name') else sender.get('first_name', '')
            receiver_display_name = f"@{receiver_username}" if receiver_username else str(receiver_user_id)

            profile_photo = get_user_profile_photo(receiver_user_id) if receiver_user_id else None
            profile_photo_url = f"https://api.telegram.org/file/bot7889701836:AAECLBRjjDadhpgJreOctpo5Jc72ekDKNjc/{profile_photo}" if profile_photo else ""
            existing_receiver = next((r for r in history.get(sender_id, []) if r["receiver_id"] == (receiver_username or str(receiver_user_id))), None)
            if not existing_receiver:
                if sender_id not in history:
                    history[sender_id] = []
                receiver_data = {
                    "receiver_id": receiver_username or str(receiver_user_id),
                    "display_name": receiver_display_name,
                    "first_name": sender.get("first_name", ""),
                    "profile_photo_url": profile_photo_url,
                    "curious_users": set()
                }
                history[sender_id].append(receiver_data)
                history[sender_id] = history[sender_id][-10:]
                save_history(sender_id, receiver_data)

            whispers[unique_id] = {
                "sender_id": sender_id,
                "sender_username": sender_username,
                "sender_display_name": sender_display_name,
                "receiver_username": receiver_username,
                "receiver_user_id": receiver_user_id,
                "receiver_display_name": receiver_display_name,
                "secret_message": secret_message,
                "curious_users": set(),
                "receiver_views": []
            }

            receiver_id_display = escape_markdown(receiver_display_name)
            code_content = format_block_code(whispers[unique_id])
            public_text = f"{receiver_id_display}\n\n```{code_content}```"
            reply_target = f"@{sender_username}" if sender_username else str(sender_id)
            reply_text = f"{reply_target} "
            keyboard = {
                "inline_keyboard": [[
                    {"text": "👁️ show", "callback_data": f"show|{unique_id}"},
                    {"text": "🗨️ reply", "switch_inline_query_current_chat": reply_text}
                ]]
            }

            results = [
                {
                    "type": "article",
                    "id": unique_id,
                    "title": f"🔒 نجوا به {receiver_display_name} 🎉",
                    "input_message_content": {
                        "message_text": public_text,
                        "parse_mode": "MarkdownV2"
                    },
                    "reply_markup": keyboard,
                    "description": f"پیام: {secret_message[:15]}...",
                    "thumb_url": profile_photo_url
                },
                base_result
            ]
            set_cached_inline_query(sender_id, query_text, results)
            answer_inline_query(query_id, results)

        except Exception as e:
            logger.error("Inline query error: %s", str(e))
            answer_inline_query(query_id, [base_result])

    elif "callback_query" in update:
        callback = update["callback_query"]
        callback_id = callback["id"]
        data = callback["data"]
        message = callback.get("message")
        inline_message_id = callback.get("inline_message_id")

        if data.startswith("show|"):
            _, unique_id = data.split("|", 1)
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
                (whisper_data["receiver_username"] and username and username.lower() == whisper_data["receiver_username"].lower()) or
                (whisper_data["receiver_user_id"] and user_id == str(whisper_data["receiver_user_id"]))
            )

            if is_allowed and user_id != whisper_data["sender_id"]:
                whisper_data["receiver_views"].append(time.time())
                whisper_data["receiver_display_name"] = f"@{username}" if username else str(user_id)

            if not is_allowed:
                whisper_data["curious_users"].add(user_display_name)

            receiver_id_display = escape_markdown(whisper_data["receiver_display_name"])
            code_content = format_block_code(whisper_data)
            new_text = f"{receiver_id_display}\n\n```{code_content}```"

            reply_target = f"@{whisper_data['sender_username']}" if whisper_data['sender_username'] else str(whisper_data['sender_id'])
            reply_text = f"{reply_target} "
            keyboard = {
                "inline_keyboard": [[
                    {"text": "👁️ show", "callback_data": f"show|{unique_id}"},
                    {"text": "🗨️ reply", "switch_inline_query_current_chat": reply_text}
                ]]
            }

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