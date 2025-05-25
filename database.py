import sqlite3
import json
import time
from logger import logger

DATABASE = "history.db"
history = {}

def init_database():
    """ایجاد جدول تاریخچه در صورت عدم وجود"""
    conn = sqlite3.connect(DATABASE, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS history (
            sender_id TEXT,
            receiver_id TEXT,
            display_name TEXT,
            first_name TEXT,
            profile_photo_url TEXT,
            PRIMARY KEY (sender_id, receiver_id)
        )
    """)
    conn.commit()
    conn.close()

def load_history():
    """بارگذاری تاریخچه از پایگاه داده به حافظه"""
    global history
    history = {}
    try:
        conn = sqlite3.connect(DATABASE, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("SELECT sender_id, receiver_id, display_name, first_name, profile_photo_url FROM history")
        rows = cursor.fetchall()
        for row in rows:
            sender_id, receiver_id, display_name, first_name, profile_photo_url = row
            if sender_id not in history:
                history[sender_id] = []
            history[sender_id].append({
                "receiver_id": receiver_id,
                "display_name": display_name,
                "first_name": first_name,
                "profile_photo_url": profile_photo_url,
                "time": time.time()  # برای سازگاری
            })
        conn.close()
        logger.info("Loaded history: %s", history)
    except Exception as e:
        logger.error("Error loading history: %s", str(e))
    return history

def save_history(sender_id, receiver):
    """ذخیره یا به‌روزرسانی تاریخچه در پایگاه داده و حافظه"""
    try:
        conn = sqlite3.connect(DATABASE, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO history (sender_id, receiver_id, display_name, first_name, profile_photo_url)
            VALUES (?, ?, ?, ?, ?)
        """, (sender_id, receiver["receiver_id"], receiver["display_name"], receiver["first_name"], receiver["profile_photo_url"]))
        conn.commit()
        conn.close()
        logger.info("Saved history to database: sender=%s, receiver=%s, display_name=%s", sender_id, receiver["receiver_id"], receiver["display_name"])
        # به‌روزرسانی حافظه
        if sender_id not in history:
            history[sender_id] = []
        existing = next((r for r in history[sender_id] if r["receiver_id"] == receiver["receiver_id"]), None)
        if existing:
            existing.update(receiver)
        else:
            history[sender_id].append(receiver)
            history[sender_id] = history[sender_id][-10:]  # محدود به 10 گیرنده
        logger.info("Updated in-memory history for sender %s: %s", sender_id, history[sender_id])
    except Exception as e:
        logger.error("Error saving history: %s", str(e))

# Initialize database
init_database()
load_history()