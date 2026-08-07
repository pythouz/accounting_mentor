import logging
import time
from telegram import Update
from telegram.ext import Application
from config import BOT_TOKEN
from database.models import init_db
from handlers.admin import get_admin_handlers
from handlers.user import get_user_conv_handler
from handlers.content import get_content_handlers
from handlers.admin_content import get_admin_content_handlers
from handlers.admin_quiz import get_admin_quiz_handlers  # <-- أضف هذا الاستيراد
from handlers.quiz import get_quiz_handlers              # <-- أضف هذا الاستيراد

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

def run_bot():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is missing! تأكد من ملف .env")
        return
    logger.info("جاري تهيئة قاعدة البيانات...")
    init_db()
    application = Application.builder().token(BOT_TOKEN).build()
    
    for admin_handler in get_admin_handlers():
        application.add_handler(admin_handler)

    for admin_content_handler in get_admin_content_handlers():
        application.add_handler(admin_content_handler)

    for admin_quiz_handler in get_admin_quiz_handlers():      # <-- تسجيل أدمن الأسئلة
        application.add_handler(admin_quiz_handler)

    for content_handler in get_content_handlers():
        application.add_handler(content_handler)

    for quiz_handler in get_quiz_handlers():                  # <-- تسجيل هاندلر اختبارات المستخدمين
        application.add_handler(quiz_handler)

    application.add_handler(get_user_conv_handler())
    logger.info("البوت يعمل الآن ومستعد لاستقبال الرسائل...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

def main():
    """
    غلاف خارجي: لو run_bot() وقعت لأي سبب (قطع نت، Conflict من تليجرام،
    استثناء غير متوقع...) بيعيد تشغيلها تاني تلقائيًا بدل ما البوت يفضل واقف.
    """
    backoff = 5  # ثواني الانتظار قبل أول محاولة إعادة تشغيل
    max_backoff = 60
    while True:
        try:
            run_bot()
            # لو run_polling رجعت عادي (يعني حد وقفها بإشارة إيقاف)، بلاش لوب لا نهائي
            logger.info("البوت توقف بشكل طبيعي. جاري الخروج.")
            break
        except Exception:
            logger.exception(f"البوت وقع بخطأ غير متوقع. هيعيد المحاولة بعد {backoff} ثانية...")
            time.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)  # زيادة وقت الانتظار تدريجيًا لحد سقف معين
            continue

if __name__ == "__main__":
    main()
