from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, MessageHandler, CallbackQueryHandler, filters
from database.models import SessionLocal, User, Lesson, Question


def _build_action_buttons(level_id: int, lesson, step_index: int, is_last_step: bool, has_quiz: bool):
    """
    الأزرار اللي بتظهر في آخر مرحلة من الدرس (بعد النص والفيديو):
    - لو الدرس ليه كويز سريع -> زرار الكويز *بس* (لازم يخلصه الأول، مينفعش يتخطاه)
    - لو مفيش كويز ومش آخر درس -> زرار الدرس التالي
    - لو مفيش كويز وآخر درس -> زرار امتحان المستوى النهائي
    """
    if has_quiz:
        # زرار الكويز لوحده -> الانتقال للخطوة اللي بعده بيحصل من داخل quiz_finish
        # بعد ما المستخدم يخلص الكويز فعليًا، مش من هنا
        return [[InlineKeyboardButton(
            "📝 كويز الدرس السريع",
            callback_data=f"start_mini_quiz:{lesson.id}:{step_index}"
        )]]

    if is_last_step:
        return [[InlineKeyboardButton(
            "🏆 امتحان المستوى النهائي",
            callback_data=f"start_final_exam:{level_id}"
        )]]

    return [[InlineKeyboardButton(
        "الدرس التالي ➡️",
        callback_data=f"lesson_step:{level_id}:{step_index + 1}:text"
    )]]


async def send_lesson_step(chat_id: int, level_id: int, step_index: int, context: ContextTypes.DEFAULT_TYPE, stage: str = "text"):
    db = SessionLocal()
    try:
        lessons = db.query(Lesson).filter(Lesson.level_id == level_id).order_by(Lesson.order).all()

        if step_index >= len(lessons):
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("📝 ابدأ امتحان المستوى النهائي", callback_data=f"start_final_exam:{level_id}")]])
            await context.bot.send_message(
                chat_id,
                "🎉 أتممت المادة العلمية لجميع دروس هذا المستوى!\nجاهز لخوض الاختبار النهائي للترقية؟",
                reply_markup=keyboard,
            )
            return

        lesson = lessons[step_index]
        is_last_step = (step_index == len(lessons) - 1)

        # التحقق من وجود أسئلة كويز لهذا الدرس
        has_quiz = db.query(Question).filter(Question.lesson_id == lesson.id, Question.is_final_exam == False).count() > 0

        caption_text = f"📘 *الدرس ({step_index + 1}): {lesson.title}*\n\n{lesson.intro_text}"
        has_video = bool(lesson.video_file_id)

        # ---------- المرحلة الأولى: النص الملخص ----------
        if stage == "text":
            if has_video:
                # فيه فيديو بعد كده -> زرار واحد بس يودي لمرحلة الفيديو
                keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(
                    "▶️ عرض الفيديو التوضيحي",
                    callback_data=f"lesson_step:{level_id}:{step_index}:video"
                )]])
            else:
                # مفيش فيديو -> اعرض أزرار الإجراء (كويز/الدرس التالي/الامتحان) على طول
                keyboard = InlineKeyboardMarkup(_build_action_buttons(level_id, lesson, step_index, is_last_step, has_quiz))

            await context.bot.send_message(
                chat_id,
                text=caption_text,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            return

        # ---------- المرحلة الثانية: الفيديو (لو موجود) ----------
        if stage == "video" and has_video:
            keyboard = InlineKeyboardMarkup(_build_action_buttons(level_id, lesson, step_index, is_last_step, has_quiz))
            await context.bot.send_video(
                chat_id,
                video=lesson.video_file_id,
                caption=f"🎬 فيديو الدرس ({step_index + 1}): {lesson.title}",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            return

        # حالة احتياطية (مفيش فيديو لكن اتبعتلنا stage=video غلط) -> ارجع للنص
        await send_lesson_step(chat_id, level_id, step_index, context, stage="text")
    finally:
        db.close()


async def show_material_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        if not user or user.is_banned:
            return
        # يكمل من نفس الدرس اللي كان واقف عنده (مش بيرجّعه للدرس الأول من الأول)
        step_index = user.current_lesson_step or 0
        level_id = user.current_level
    finally:
        db.close()

    await send_lesson_step(update.effective_chat.id, level_id, step_index, context, stage="text")


async def lesson_step_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    # يدعم الصيغة القديمة (بدون stage) والصيغة الجديدة (بيها stage) لضمان التوافق
    if len(parts) == 4:
        _, level_id_str, step_index_str, stage = parts
    else:
        _, level_id_str, step_index_str = parts
        stage = "text"

    level_id, step_index = int(level_id_str), int(step_index_str)

    telegram_id = update.effective_user.id
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        if not user or user.is_banned or user.current_level != level_id:
            return
        user.current_lesson_step = step_index
        db.commit()
    finally:
        db.close()

    await send_lesson_step(query.message.chat_id, level_id, step_index, context, stage=stage)


def get_content_handlers():
    return [
        MessageHandler(filters.Regex("^📚 المادة العلمية للمستوى الحالي$"), show_material_entry),
        CallbackQueryHandler(lesson_step_callback, pattern="^lesson_step:"),
    ]
