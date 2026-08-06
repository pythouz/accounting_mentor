import logging
from telegram import Update
from telegram.ext import Application
from config import BOT_TOKEN
from database.models import init_db
from handlers.admin import get_admin_handlers
from handlers.user import get_user_conv_handler
from handlers.content import get_content_handlers
from handlers.admin_content import get_admin_content_handlers

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is missing! تأكد من ملف .env")
        return
    logger.info("جاري تهيئة قاعدة البيانات...")
    init_db()
    application = Application.builder().token(BOT_TOKEN).build()
    
    for admin_handler in get_admin_handlers():
        application.add_handler(admin_handler)

    for content_handler in get_content_handlers():
        application.add_handler(content_handler)

    for admin_content_handler in get_admin_content_handlers():
        application.add_handler(admin_content_handler)

    application.add_handler(get_user_conv_handler())
    logger.info("البوت يعمل الآن ومستعد لاستقبال الرسائل...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
