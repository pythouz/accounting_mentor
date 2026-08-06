from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, MessageHandler, CallbackQueryHandler, filters
from database.models import SessionLocal, User, Lesson


async def send_lesson_step(chat_id: int, level_id: int, step_index: int, context: ContextTypes.DEFAULT_TYPE):
    """
    بيبعت درس واحد بس (الخطوة رقم step_index) من مستوى level_id،
    مع زرار 'التالي' أو 'ابدأ الاختبار' لو ده آخر درس.
    """
    db = SessionLocal()
    try:
        lessons = (
            db.query(Lesson)
            .filter(Lesson.level_id == level_id)
            .order_by(Lesson.order)
            .all()
        )

        # لو خلصت كل الدروس (أو مفيش دروس أصلاً) → زرار ابدأ الاختبار مباشرة
        if step_index >= len(lessons):
            keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton("📝 ابدأ الاختبار", callback_data=f"start_quiz:{level_id}")]]
            )
            await context.bot.send_message(
                chat_id,
                "🎉 خلصت المادة العلمية بتاعت المستوى ده!\nجاهز تبدأ الاختبار؟",
                reply_markup=keyboard,
            )
            return

        lesson = lessons[step_index]
        is_last_step = (step_index == len(lessons) - 1)

        if is_last_step:
            button_text = "📝 ابدأ الاختبار"
            next_callback = f"start_quiz:{level_id}"
        else:
            button_text = "التالي ➡️"
            next_callback = f"lesson_step:{level_id}:{step_index + 1}"

        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(button_text, callback_data=next_callback)]])

        if lesson.content_type == "video":
            await context.bot.send_video(
                chat_id,
                video=lesson.content,  # ده الـ file_id المحفوظ، مش الفيديو نفسه
                caption=lesson.title or "",
                reply_markup=keyboard,
            )
        else:
            text = f"*{lesson.title}*\n\n{lesson.content}" if lesson.title else lesson.content
            await context.bot.send_message(chat_id, text, reply_markup=keyboard, parse_mode="Markdown")
    finally:
        db.close()


async def show_material_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """يتفعّل لما المستخدم يدوس زرار '📚 المادة العلمية للمستوى الحالي'."""
    telegram_id = update.effective_user.id
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        if not user or user.is_banned:
            return
        user.current_lesson_step = 0  # يبدأ من أول درس كل مرة يدوس الزرار
        db.commit()
        level_id = user.current_level
    finally:
        db.close()

    await send_lesson_step(update.effective_chat.id, level_id, 0, context)


async def lesson_step_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """يتفعّل لما المستخدم يدوس زرار 'التالي' جوه رسالة الدرس."""
    query = update.callback_query
    await query.answer()  # لازم دايمًا نرد على الـ callback عشان الزرار ميفضلش "بيلف"

    _, level_id_str, step_index_str = query.data.split(":")
    level_id, step_index = int(level_id_str), int(step_index_str)

    telegram_id = update.effective_user.id
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        if not user or user.is_banned or user.current_level != level_id:
            # المستخدم عدّى مستوى أو اتحظر في الوقت ده - نتجاهل الضغطة القديمة
            return
        user.current_lesson_step = step_index
        db.commit()
    finally:
        db.close()

    await send_lesson_step(query.message.chat_id, level_id, step_index, context)


def get_content_handlers():
    return [
        MessageHandler(filters.Regex("^📚 المادة العلمية للمستوى الحالي$"), show_material_entry),
        CallbackQueryHandler(lesson_step_callback, pattern="^lesson_step:"),
        CallbackQueryHandler(quiz_coming_soon, pattern="^start_quiz:"),
    ]


async def quiz_coming_soon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # مؤقت لحد ما نبني منطق الاختبار الكامل في الخطوة الجاية
    query = update.callback_query
    await query.answer()
    await context.bot.send_message(query.message.chat_id, "⏳ قسم الاختبار جاري بناؤه دلوقتي، هيبقى شغال قريب جدًا.")
