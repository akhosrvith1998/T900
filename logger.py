import logging
import os

def setup_logger():
    """تنظیم لاگر با خروجی در فایل و کنسول"""
    logger = logging.getLogger('bot_logger')
    logger.setLevel(logging.INFO)
    # Handler برای فایل
    file_handler = logging.FileHandler('bot.log')
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    # Handler برای کنسول
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger

logger = setup_logger()
