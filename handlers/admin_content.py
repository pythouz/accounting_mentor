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

(
    ASKING_LEVEL,
    ASKING_NEW_LEVEL_TITLE,
    ASKING_LESSON_TITLE,
    ASKING_INTRO_TEXT,
    ASKING_HAS_VIDEO,
    ASKING_VIDEO,
) = range(6)


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
            await update.message.reply_text("اكتب عنوان الدرس:")
            return ASKING_LESSON_TITLE
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
        await update.message.reply_text("اكتب عنوان الدرس:")
        return ASKING_LESSON_TITLE
    finally:
        db.close()


async def receive_lesson_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    title = update.message.text.strip()
    if not title:
        await update.message.reply_text("محتاج عنوان فعلي للدرس، اكتبه تاني:")
        return ASKING_LESSON_TITLE
    context.user_data["lesson_title"] = title
    await update.message.reply_text("تمام، اكتب النص الملخص للدرس (اللي هيظهر للطالب الأول قبل أي حاجة):")
    return ASKING_INTRO_TEXT


async def receive_intro_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    intro_text = update.message.text.strip()
    if not intro_text:
        await update.message.reply_text("محتاج نص فعلي، اكتبه تاني:")
        return ASKING_INTRO_TEXT
    context.user_data["intro_text"] = intro_text

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🎥 آه، فيه فيديو", callback_data="has_video:yes"),
                InlineKeyboardButton("🚫 لا، مفيش فيديو", callback_data="has_video:no"),
            ]
        ]
    )
    await update.message.reply_text("فيه فيديو توضيحي للدرس ده؟", reply_markup=keyboard)
    return ASKING_HAS_VIDEO


async def receive_has_video_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    choice = query.data.split(":")[1]

    if choice == "yes":
        await query.message.reply_text("تمام، ابعتلي الفيديو دلوقتي (كملف فيديو مش رابط):")
        return ASKING_VIDEO

    return await save_lesson(update, context, video_file_id=None)


async def receive_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message.video:
        await update.message.reply_text("محتاج تبعت فيديو فعلي، حاول تاني:")
        return ASKING_VIDEO
    return await save_lesson(update, context, video_file_id=update.message.video.file_id)


async def save_lesson(update: Update, context: ContextTypes.DEFAULT_TYPE, video_file_id) -> int:
    level_id = context.user_data.get("level_id")
    db = SessionLocal()
    try:
        existing_count = db.query(Lesson).filter(Lesson.level_id == level_id).count()
        new_lesson = Lesson(
            level_id=level_id,
            order=existing_count,  # يتحط آخر الدروس بالترتيب
            title=context.user_data.get("lesson_title"),
            intro_text=context.user_data.get("intro_text"),
            video_file_id=video_file_id,
        )
        db.add(new_lesson)
        db.commit()
        target_message = update.callback_query.message if update.callback_query else update.message
        await target_message.reply_text(
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
                ASKING_LESSON_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_lesson_title)],
                ASKING_INTRO_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_intro_text)],
                ASKING_HAS_VIDEO: [CallbackQueryHandler(receive_has_video_choice, pattern="^has_video:")],
                ASKING_VIDEO: [MessageHandler(filters.VIDEO & ~filters.COMMAND, receive_video)],
            },
            fallbacks=[CommandHandler("cancel", cancel_addlesson)],
        )
    ]
