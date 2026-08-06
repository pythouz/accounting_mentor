from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from database.models import SessionLocal, Level, Lesson
from config import ADMIN_IDS

ASKING_LEVEL, ASKING_NEW_LEVEL_TITLE, ASKING_CONTENT_TYPE, ASKING_CONTENT = range(4)


async def start_addlesson(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_user.id not in ADMIN_IDS:
        return ConversationHandler.END
    await update.message.reply_text(
        "هنضيف درس جديد. اكتب رقم المستوى اللي الدرس ده هيتضاف له (مثلاً 1):"
    )
    return ASKING_LEVEL


async def receive_level_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not text.isdigit():
        await update.message.reply_text("اكتب رقم صحيح بس، مثلاً 1 أو 2:")
        return ASKING_LEVEL

    level_number = int(text)
    db = SessionLocal()
    try:
        level = db.query(Level).filter(Level.level_number == level_number).first()
        if level:
            context.user_data["level_id"] = level.id
            context.user_data["level_number"] = level_number
            return await ask_content_type(update, context)
        else:
            context.user_data["level_number"] = level_number
            await update.message.reply_text(
                f"المستوى رقم {level_number} لسه مش موجود. اكتب عنوانه عشان ننشئه دلوقتي "
                "(مثلاً: أساسيات القيد المزدوج):"
            )
            return ASKING_NEW_LEVEL_TITLE
    finally:
        db.close()


async def receive_new_level_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    title = update.message.text.strip()
    level_number = context.user_data["level_number"]
    db = SessionLocal()
    try:
        new_level = Level(level_number=level_number, title=title, passing_score=80, is_final=False)
        db.add(new_level)
        db.commit()
        db.refresh(new_level)
        context.user_data["level_id"] = new_level.id
        await update.message.reply_text(f"✅ تم إنشاء المستوى {level_number} بعنوان: {title}")
        return await ask_content_type(update, context)
    finally:
        db.close()


async def ask_content_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📝 نص", callback_data="lesson_type:text"),
                InlineKeyboardButton("🎥 فيديو", callback_data="lesson_type:video"),
            ]
        ]
    )
    await update.message.reply_text("الدرس ده نوعه إيه؟", reply_markup=keyboard)
    return ASKING_CONTENT_TYPE


async def receive_content_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    content_type = query.data.split(":")[1]  # 'text' أو 'video'
    context.user_data["content_type"] = content_type

    if content_type == "video":
        await query.message.reply_text("تمام، ابعتلي الفيديو دلوقتي (كملف فيديو مش رابط):")
    else:
        await query.message.reply_text("تمام، اكتب نص الدرس دلوقتي:")
    return ASKING_CONTENT


async def receive_content(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    content_type = context.user_data.get("content_type")
    level_id = context.user_data.get("level_id")

    if content_type == "video":
        if not update.message.video:
            await update.message.reply_text("محتاج تبعت فيديو فعلي، حاول تاني:")
            return ASKING_CONTENT
        content_value = update.message.video.file_id
    else:
        if not update.message.text:
            await update.message.reply_text("محتاج تبعت نص فعلي، حاول تاني:")
            return ASKING_CONTENT
        content_value = update.message.text

    db = SessionLocal()
    try:
        existing_count = db.query(Lesson).filter(Lesson.level_id == level_id).count()
        new_lesson = Lesson(
            level_id=level_id,
            order=existing_count,  # يتحط آخر الدروس بالترتيب
            content_type=content_type,
            content=content_value,
        )
        db.add(new_lesson)
        db.commit()
        await update.message.reply_text(
            f"✅ تم إضافة الدرس بنجاح (ترتيبه رقم {existing_count + 1} في المستوى ده).\n"
            "عايز تضيف درس تاني؟ اكتب /addlesson تاني."
        )
    finally:
        db.close()

    context.user_data.clear()
    return ConversationHandler.END


async def cancel_addlesson(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("تم إلغاء إضافة الدرس.")
    return ConversationHandler.END


def get_admin_content_handlers():
    return [
        ConversationHandler(
            entry_points=[CommandHandler("addlesson", start_addlesson)],
            states={
                ASKING_LEVEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_level_number)],
                ASKING_NEW_LEVEL_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_new_level_title)],
                ASKING_CONTENT_TYPE: [CallbackQueryHandler(receive_content_type, pattern="^lesson_type:")],
                ASKING_CONTENT: [MessageHandler((filters.TEXT | filters.VIDEO) & ~filters.COMMAND, receive_content)],
            },
            fallbacks=[CommandHandler("cancel", cancel_addlesson)],
        )
    ]
