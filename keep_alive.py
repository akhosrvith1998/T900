from flask import Flask
from threading import Thread
import requests
import time
import os

app = Flask(__name__)

@app.route('/')
def home():
    """نمایش وضعیت سرور"""
    return "I'm alive"

def run():
    """اجرای سرور Flask"""
    port = int(os.getenv("PORT", 8080))  # استفاده از متغیر محیطی PORT
    app.run(host='0.0.0.0', port=port)

def ping():
    """پینگ دوره‌ای برای فعال نگه داشتن سرور"""
    server_url = os.getenv("SERVER_URL", "https://t900.onrender.com")  # آدرس اصلی سرور
    while True:
        try:
            response = requests.get(server_url)
            if response.status_code == 200:
                print(f"Ping successful to {server_url}")
            else:
                print(f"Ping failed to {server_url}, status code: {response.status_code}")
        except Exception as e:
            print(f"Ping error: {str(e)}")
        time.sleep(600)  # هر 10 دقیقه

def keep_alive():
    """راه‌اندازی سرور و پینگ در تردهای جداگانه"""
    t1 = Thread(target=run, daemon=True)  # تنظیم daemon برای ترد سرور
    t2 = Thread(target=ping, daemon=True)  # تنظیم daemon برای ترد پینگ
    t1.start()
    t2.start()

if __name__ == "__main__":
    keep_alive()