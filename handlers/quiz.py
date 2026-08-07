from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, MessageHandler, filters
from database.models import SessionLocal, User, Level, Lesson, Question

# تشغيل امتحان المستوى من زر القائمة
async def trigger_final_exam_from_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        level_id = level.id
    finally:
        db.close()

    await start_quiz_engine(update.effective_chat.id, context, level_id=level_id, is_final=True)

# تشغيل كويز درس أو امتحان مستوى من أزرار Callback
async def trigger_quiz_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split(":")
    mode = data[0]

    if mode == "start_mini_quiz":
        lesson_id = int(data[1])
        step_index = int(data[2])
        await start_quiz_engine(query.message.chat_id, context, lesson_id=lesson_id, is_final=False, step_index=step_index, query=query)
    elif mode == "start_final_exam":
        level_id = int(data[1])
        await start_quiz_engine(query.message.chat_id, context, level_id=level_id, is_final=True, query=query)

async def start_quiz_engine(chat_id: int, context: ContextTypes.DEFAULT_TYPE, level_id: int = None, lesson_id: int = None, is_final: bool = False, step_index: int = 0, query=None):
    db = SessionLocal()
    try:
        if is_final:
            level = db.query(Level).filter(Level.id == level_id).first()
            questions = db.query(Question).filter(Question.level_id == level_id, Question.is_final_exam == True).all()
            passing_score = level.passing_score if level else 80
            level_num = level.level_number if level else 1
        else:
            questions = db.query(Question).filter(Question.lesson_id == lesson_id, Question.is_final_exam == False).all()
            lesson = db.query(Lesson).filter(Lesson.id == lesson_id).first()
            level_id = lesson.level_id
            level_num = lesson.level.level_number
            passing_score = 0

        if not questions:
            msg = "⏳ لا يوجد أسئلة متوفرة لهذا الاختبار حالياً."
            if query:
                await query.edit_message_text(msg)
            else:
                await context.bot.send_message(chat_id, msg)
            return

        q_list = [{
            'id': q.id,
            'text': q.question_text,
            'options': {'A': q.option_a, 'B': q.option_b, 'C': q.option_c, 'D': q.option_d},
            'correct': q.correct_answer,
            'explanation': q.explanation
        } for q in questions]

        context.user_data['quiz'] = {
            'is_final': is_final,
            'level_id': level_id,
            'level_number': level_num,
            'step_index': step_index,
            'passing_score': passing_score,
            'questions': q_list,
            'index': 0,
            'score': 0
        }
    finally:
        db.close()

    await render_question(chat_id, context, edit_query=query)

async def render_question(chat_id: int, context: ContextTypes.DEFAULT_TYPE, edit_query=None):
    quiz = context.user_data.get('quiz')
    if not quiz:
        return

    idx = quiz['index']
    q = quiz['questions'][idx]
    total = len(quiz['questions'])
    tag = "🏆 اختبار المستوى النهائي" if quiz['is_final'] else "📝 كويز الدرس"

    keyboard = [
        [InlineKeyboardButton(f"A) {q['options']['A']}", callback_data=f"qans:{q['id']}:A")],
        [InlineKeyboardButton(f"B) {q['options']['B']}", callback_data=f"qans:{q['id']}:B")],
        [InlineKeyboardButton(f"C) {q['options']['C']}", callback_data=f"qans:{q['id']}:C")],
        [InlineKeyboardButton(f"D) {q['options']['D']}", callback_data=f"qans:{q['id']}:D")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = f"{tag} (سؤال {idx + 1} من {total}):\n\n*{q['text']}*"

    if edit_query:
        try:
            await edit_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
        except Exception:
            await context.bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await context.bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode="Markdown")

async def process_quiz_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, q_id_str, chosen = query.data.split(":")
    q_id = int(q_id_str)

    quiz = context.user_data.get('quiz')
    if not quiz:
        await query.edit_message_text("❌ انتهت جلسة الاختبار. أعد الفتح من القائمة.")
        return

    idx = quiz['index']
    q = quiz['questions'][idx]

    if q['id'] != q_id:
        return

    if chosen == q['correct']:
        quiz['score'] += 1
        msg = "✅ إجابة صحيحة!"
    else:
        msg = f"❌ إجابة خاطئة.\nالإجابة الصحيحة هي: *{q['correct']}) {q['options'][q['correct']]}*"

    if q['explanation']:
        msg += f"\n\n💡 *التوضيح:* {q['explanation']}"

    quiz['index'] += 1
    is_last = (quiz['index'] >= len(quiz['questions']))

    if is_last:
        keyboard = [[InlineKeyboardButton("🏁 إنهاء وعرض النتيجة", callback_data="q_finish")]]
    else:
        keyboard = [[InlineKeyboardButton("السؤال التالي ➡️", callback_data="q_next")]]

    await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def quiz_next_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await render_question(query.message.chat_id, context, edit_query=query)

async def quiz_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    quiz = context.user_data.pop('quiz', None)
    if not quiz:
        await query.edit_message_text("❌ انتهت الجلسة.")
        return

    score = quiz['score']
    total = len(quiz['questions'])
    is_final = quiz['is_final']
    telegram_id = update.effective_user.id

    if not is_final:
        # نهاية كويز الدرس السريع
        level_id = quiz['level_id']
        next_step = quiz['step_index'] + 1

        db = SessionLocal()
        try:
            total_lessons = db.query(Lesson).filter(Lesson.level_id == level_id).count()
        finally:
            db.close()

        if next_step >= total_lessons:
            # ده كان آخر درس -> يوجّه مباشرة لامتحان المستوى النهائي
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(
                "🏆 ابدأ امتحان المستوى النهائي", callback_data=f"start_final_exam:{level_id}"
            )]])
            text = (
                f"👏 أحسنت! أنهيت كويز الدرس بنجاح.\n📊 درجتك: {score}/{total}\n\n"
                f"🎉 كده خلصت كل دروس المستوى! جاهز للامتحان النهائي؟"
            )
        else:
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(
                "متابعة للدرس التالي ➡️", callback_data=f"lesson_step:{level_id}:{next_step}:text"
            )]])
            text = f"👏 أحسنت! أنهيت كويز الدرس بنجاح.\n📊 درجتك: {score}/{total}\n\nاضغط أدناه لمتابعة المذاكرة:"

        await query.edit_message_text(text, reply_markup=keyboard)
        return

    # نهاية اختبار المستوى النهائي
    percentage = int((score / total) * 100)
    passed = (percentage >= quiz['passing_score'])
    level_num = quiz['level_number']

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        if not user:
            return

        if passed:
            next_level_num = level_num + 1
            next_level = db.query(Level).filter(Level.level_number == next_level_num).first()
            if next_level:
                user.current_level = next_level_num
                user.current_lesson_step = 0
                db.commit()
                out_msg = (
                    f"🎉 مبروك! اجتزت اختبار المستوى {level_num} بنجاح!\n"
                    f"📊 درجتك: {score}/{total} ({percentage}%)\n\n"
                    f"🚀 تم ترقيتك تلقائياً للبدء في: *{next_level.title}*"
                )
            else:
                out_msg = (
                    f"🏆 مبروك التخرج النهائي!\n"
                    f"اجتزت جميع المستويات والاختبارات بنجاح باهر.\n"
                    f"📊 درجتك الأخيرة: {score}/{total} ({percentage}%)\n\n"
                    f"نتمنى لك كل التوفيق والتميز في مسيرتك المهنية المحاسبية!"
                )
        else:
            out_msg = (
                f"😔 لم تجتز اختبار المستوى {level_num}.\n"
                f"📊 درجتك: {score}/{total} ({percentage}%)\n"
                f"🎯 المطلوب للنجاح: {quiz['passing_score']}%\n\n"
                f"راجع الدروس مجدداً وأعد الاختبار عند الاستعداد."
            )
    finally:
        db.close()

    await query.edit_message_text(out_msg, parse_mode="Markdown")

def get_quiz_handlers():
    return [
        MessageHandler(filters.Regex("^📝 ابدأ اختبار المستوى$"), trigger_final_exam_from_menu),
        CallbackQueryHandler(trigger_quiz_callback, pattern="^(start_mini_quiz|start_final_exam):"),
        CallbackQueryHandler(process_quiz_answer, pattern="^qans:"),
        CallbackQueryHandler(quiz_next_question, pattern="^q_next$"),
        CallbackQueryHandler(quiz_finish, pattern="^q_finish$"),
    ]
