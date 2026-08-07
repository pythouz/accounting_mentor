from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, MessageHandler, CallbackQueryHandler, filters
from database.models import SessionLocal, User, Level, Lesson, Question


# ============================================================
#                    المسار الحي (التقدم الفعلي)
# ============================================================

def _build_action_buttons(level_id: int, lesson, step_index: int, is_last_step: bool, has_quiz: bool):
    """
    الأزرار اللي بتظهر في آخر مرحلة من الدرس (بعد النص والفيديو):
    - لو الدرس ليه كويز سريع -> زرار الكويز *بس* (لازم يخلصه الأول، مينفعش يتخطاه)
    - لو مفيش كويز ومش آخر درس -> زرار الدرس التالي
    - لو مفيش كويز وآخر درس -> زرار امتحان المستوى النهائي
    """
    if has_quiz:
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
    """
    level_id هنا دايمًا هو Level.id الحقيقي (مش رقم المستوى level_number).
    """
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

        has_quiz = db.query(Question).filter(Question.lesson_id == lesson.id, Question.is_final_exam == False).count() > 0

        caption_text = f"📘 *الدرس ({step_index + 1}): {lesson.title}*\n\n{lesson.intro_text}"
        has_video = bool(lesson.video_file_id)

        if stage == "text":
            if has_video:
                keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(
                    "▶️ عرض الفيديو التوضيحي",
                    callback_data=f"lesson_step:{level_id}:{step_index}:video"
                )]])
            else:
                keyboard = InlineKeyboardMarkup(_build_action_buttons(level_id, lesson, step_index, is_last_step, has_quiz))

            await context.bot.send_message(
                chat_id,
                text=caption_text,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            return

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
        level = db.query(Level).filter(Level.level_number == user.current_level).first()
        if not level:
            await update.message.reply_text("❌ لم يتم العثور على تفاصيل مستواك الحالي.")
            return
        step_index = user.current_lesson_step or 0
        level_id = level.id
    finally:
        db.close()

    await send_lesson_step(update.effective_chat.id, level_id, step_index, context, stage="text")


async def lesson_step_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
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
        level = db.query(Level).filter(Level.id == level_id).first()
        # لازم يتأكد إن ده فعلاً مستواه الحالي (مقارنة برقم المستوى، مش المعرف الداخلي)
        if not user or user.is_banned or not level or level.level_number != user.current_level:
            return
        user.current_lesson_step = step_index
        db.commit()
    finally:
        db.close()

    await send_lesson_step(query.message.chat_id, level_id, step_index, context, stage=stage)


# ============================================================
#         شاشة "تقدمي": عرض كل المستويات + المراجعة بدون تأثير على التقدم
# ============================================================

async def _build_progress_view(telegram_id: int):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        if not user or user.is_banned:
            return None, None

        levels = db.query(Level).order_by(Level.level_number).all()
        current_level_obj = next((lv for lv in levels if lv.level_number == user.current_level), None)

        buttons = []
        for level in levels:
            if level.level_number < user.current_level:
                label = f"✅ مستوى {level.level_number}: {level.title} (مراجعة)"
                callback = f"review_level:{level.id}"
            elif level.level_number == user.current_level:
                label = f"📍 مستوى {level.level_number}: {level.title} (مستواك الحالي)"
                callback = f"lesson_step:{level.id}:{user.current_lesson_step or 0}:text"
            else:
                label = f"🔒 مستوى {level.level_number}: {level.title}"
                callback = f"locked_level:{user.current_level}"
            buttons.append([InlineKeyboardButton(label, callback_data=callback)])

        current_title = current_level_obj.title if current_level_obj else "غير معروف"
        text = (
            f"📊 *تقدمك الحالي*\n\n"
            f"مستواك الحالي: *المستوى {user.current_level} - {current_title}*\n\n"
            f"✅ = مستوى خلصته، تقدر تراجعه براحتك من غير ما يتغير مستواك\n"
            f"📍 = مستواك الحالي\n"
            f"🔒 = لسه مقفول، لازم تنجح في امتحان المستوى الحالي الأول\n\n"
            f"اختار أي مستوى من تحت:"
        )
        return text, InlineKeyboardMarkup(buttons)
    finally:
        db.close()


async def show_progress_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text, markup = await _build_progress_view(update.effective_user.id)
    if text is None:
        return
    await update.message.reply_text(text, reply_markup=markup, parse_mode="Markdown")


async def show_progress_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text, markup = await _build_progress_view(update.effective_user.id)
    if text is None:
        return
    try:
        await query.edit_message_text(text, reply_markup=markup, parse_mode="Markdown")
    except Exception:
        await context.bot.send_message(query.message.chat_id, text, reply_markup=markup, parse_mode="Markdown")


async def locked_level_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("🔒 المستوى ده لسه مقفول", show_alert=True)
    parts = query.data.split(":")
    current_level_num = parts[1] if len(parts) > 1 else "؟"
    await context.bot.send_message(
        query.message.chat_id,
        f"🔒 المستوى ده لسه مقفول قدامك.\n"
        f"مستواك الحالي هو *المستوى {current_level_num}*، ولازم تنجح في امتحان المستوى ده الأول "
        f"(اضغط '📝 ابدأ اختبار المستوى' من القائمة) عشان يتفتح المستوى اللي بعده.",
        parse_mode="Markdown"
    )


# -------------------- مراجعة مستوى أقل (بدون أي تأثير على قاعدة البيانات) --------------------

async def send_review_step(chat_id: int, level_id: int, step_index: int, context: ContextTypes.DEFAULT_TYPE, stage: str = "text"):
    db = SessionLocal()
    try:
        lessons = db.query(Lesson).filter(Lesson.level_id == level_id).order_by(Lesson.order).all()
        back_button = InlineKeyboardButton("🔙 رجوع لقائمة المستويات", callback_data="show_progress")

        if step_index >= len(lessons):
            keyboard = InlineKeyboardMarkup([[back_button]])
            await context.bot.send_message(
                chat_id,
                "✅ خلصت مراجعة كل دروس المستوى ده.",
                reply_markup=keyboard
            )
            return

        lesson = lessons[step_index]
        caption_text = f"📘 *(مراجعة) الدرس ({step_index + 1}): {lesson.title}*\n\n{lesson.intro_text}"
        has_video = bool(lesson.video_file_id)

        if stage == "text":
            if has_video:
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("▶️ عرض الفيديو التوضيحي", callback_data=f"review_step:{level_id}:{step_index}:video")],
                    [back_button],
                ])
            else:
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("الدرس التالي ➡️", callback_data=f"review_step:{level_id}:{step_index + 1}:text")],
                    [back_button],
                ])
            await context.bot.send_message(chat_id, caption_text, reply_markup=keyboard, parse_mode="Markdown")
            return

        if stage == "video" and has_video:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("الدرس التالي ➡️", callback_data=f"review_step:{level_id}:{step_index + 1}:text")],
                [back_button],
            ])
            await context.bot.send_video(
                chat_id,
                video=lesson.video_file_id,
                caption=f"🎬 (مراجعة) فيديو الدرس ({step_index + 1}): {lesson.title}",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            return

        await send_review_step(chat_id, level_id, step_index, context, stage="text")
    finally:
        db.close()


async def review_level_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    level_id = int(query.data.split(":")[1])

    telegram_id = update.effective_user.id
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        level = db.query(Level).filter(Level.id == level_id).first()
        # تأكيد أمان: يمنع التلاعب اليدوي بالـ callback عشان يدخل مستوى مش مسموحله بمراجعته
        if not user or not level or level.level_number >= user.current_level:
            await query.answer("🔒 المستوى ده مش متاح للمراجعة.", show_alert=True)
            return
    finally:
        db.close()

    await send_review_step(query.message.chat_id, level_id, 0, context, stage="text")


async def review_step_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, level_id_str, step_index_str, stage = query.data.split(":")
    level_id, step_index = int(level_id_str), int(step_index_str)

    telegram_id = update.effective_user.id
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        level = db.query(Level).filter(Level.id == level_id).first()
        if not user or not level or level.level_number >= user.current_level:
            await query.answer("🔒 المستوى ده مش متاح للمراجعة.", show_alert=True)
            return
    finally:
        db.close()

    await send_review_step(query.message.chat_id, level_id, step_index, context, stage=stage)


def get_content_handlers():
    return [
        MessageHandler(filters.Regex("^📚 المادة العلمية للمستوى الحالي$"), show_material_entry),
        MessageHandler(filters.Regex(r"^📊 تقدمي \(مستواي الحالي\)$"), show_progress_entry),
        CallbackQueryHandler(lesson_step_callback, pattern="^lesson_step:"),
        CallbackQueryHandler(show_progress_callback, pattern="^show_progress$"),
        CallbackQueryHandler(review_level_callback, pattern="^review_level:"),
        CallbackQueryHandler(review_step_callback, pattern="^review_step:"),
        CallbackQueryHandler(locked_level_callback, pattern="^locked_level:"),
    ]
