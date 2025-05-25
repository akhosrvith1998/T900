from flask import Flask, request, Response
import requests
import os
from main import process_update
from logger import logger
import threading

app = Flask(__name__)
TOKEN = "7889701836:AAECLBRjjDadhpgJreOctpo5Jc72ekDKNjc"
URL = f"https://api.telegram.org/bot{TOKEN}/"

@app.route("/webhook", methods=["POST"])
def webhook():
    """دریافت و پردازش وب‌هوک"""
    try:
        update = request.get_json()
        logger.info("Received update: %s", update)
        threading.Thread(target=process_update, args=(update,)).start()
        return Response(status=200)
    except Exception as e:
        logger.error("Webhook error: %s", str(e))
        return Response(status=500)

if __name__ == "__main__":
    webhook_url = os.getenv("WEBHOOK_URL", "https://t900.onrender.com/webhook")
    response = requests.get(f"{URL}setWebhook?url={webhook_url}")
    logger.info("Webhook set: %s", response.text)
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
