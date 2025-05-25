from functools import lru_cache

# زمان انقضای کش به صورت پیش‌فرض توسط Telegram مدیریت می‌شود، اما maxsize محدود شده است
@lru_cache(maxsize=1000)
def get_cached_inline_query(sender_id, query):
    """
    دریافت نتایج کش‌شده برای یک sender_id و query مشخص.
    این تابع به صورت خودکار توسط lru_cache مدیریت می‌شود.
    """
    pass  # این تابع فقط برای کش کردن استفاده می‌شود و نیازی به پیاده‌سازی دستی ندارد

def set_cached_inline_query(sender_id, query, results):
    """
    تنظیم نتایج کش برای یک sender_id و query مشخص.
    با استفاده از lru_cache نیازی به پیاده‌سازی دستی نیست.
    """
    pass  # lru_cache به طور خودکار کش را مدیریت می‌کند
