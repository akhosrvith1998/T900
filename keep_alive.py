from flask import Flask
from threading import Thread
import requests
import time

app = Flask('')

@app.route('/')
def home():
    return "I'm alive"

def run():
    """اجرای سرور Flask"""
    app.run(host='0.0.0.0', port=8080)

def ping():
    """پینگ دوره‌ای برای فعال نگه داشتن سرور"""
    while True:
        try:
            requests.get("https://your-render-app.onrender.com")  # آدرس سرور خود را جایگزین کنید
        except Exception:
            pass
        time.sleep(600)  # هر 10 دقیقه

def keep_alive():
    """راه‌اندازی سرور و پینگ در تردهای جداگانه"""
    t1 = Thread(target=run)
    t2 = Thread(target=ping)
    t1.start()
    t2.start()
