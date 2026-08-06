from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from database.models import SessionLocal, AccessCode, User
from config import ADMIN_IDS

async def add_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    if not context.args:
        await update.message.reply_text("الرجاء كتابة الكلمة بعد الأمر.\nمثال: `/addcode RABIE_2026`")
        return

    new_code_text = context.args[0]
    db = SessionLocal()
    try:
        existing_code = db.query(AccessCode).filter(AccessCode.code == new_code_text).first()
        if existing_code:
            await update.message.reply_text("❌ هذه الكلمة موجودة بالفعل.")
            return
        new_access_code = AccessCode(code=new_code_text, is_used=False)
        db.add(new_access_code)
        db.commit()
        await update.message.reply_text(f"✅ تم حفظ الكلمة بنجاح: `{new_code_text}`\nيمكنك الآن إعطاؤها للمحاسب ليدخل بها مرة واحدة.")
    finally:
        db.close()

async def show_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    db = SessionLocal()
    try:
        total_users = db.query(User).count()
        active_users = db.query(User).filter(User.is_banned == False).count()
        banned_users = db.query(User).filter(User.is_banned == True).count()
        msg = (f"📊 إحصائيات المشتركين:\n\n"
               f"👥 إجمالي المحاسبين: {total_users}\n"
               f"✅ النشطين: {active_users}\n"
               f"🚫 المحظورين: {banned_users}\n")
        await update.message.reply_text(msg)
    finally:
        db.close()

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("مثال: `/ban 123456789`\n(الرقم هو الـ Telegram ID بتاع المستخدم)", parse_mode="Markdown")
        return

    target_id = int(context.args[0])
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == target_id).first()
        if not user:
            await update.message.reply_text("❌ مفيش مستخدم مسجل بالـ ID دا.")
            return
        user.is_banned = True
        db.commit()
        await update.message.reply_text(
            f"🚫 تم حظر المستخدم `{target_id}`.\n"
            "مش هيقدر يستخدم البوت تاني إلا لو ديته كود تفعيل جديد بأمر /addcode، "
            "وهو يكتبه في البوت عشان يفك الحظر عن نفسه.",
            parse_mode="Markdown"
        )
    finally:
        db.close()

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # فك حظر فوري بدون كود جديد - للحالات الاستثنائية فقط (زي حظر بالغلط)
    if update.effective_user.id not in ADMIN_IDS:
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("مثال: `/unban 123456789`", parse_mode="Markdown")
        return

    target_id = int(context.args[0])
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == target_id).first()
        if not user:
            await update.message.reply_text("❌ مفيش مستخدم مسجل بالـ ID دا.")
            return
        user.is_banned = False
        db.commit()
        await update.message.reply_text(f"✅ تم فك الحظر فورًا عن `{target_id}` بدون طلب كود جديد.", parse_mode="Markdown")
    finally:
        db.close()

def get_admin_handlers():
    return [
        CommandHandler('addcode', add_code),
        CommandHandler('users', show_users),
        CommandHandler('ban', ban_user),
        CommandHandler('unban', unban_user),
    ]
