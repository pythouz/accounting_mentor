from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from database.models import SessionLocal, Level, Lesson, Question
from config import ADMIN_IDS

Q_LEVEL, Q_TYPE, Q_LESSON_SELECT, Q_TEXT, Q_OPT_A, Q_OPT_B, Q_OPT_C, Q_OPT_D, Q_CORRECT, Q_EXPLANATION = range(10)

async def start_addquestion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_user.id not in ADMIN_IDS:
        return ConversationHandler.END
    await update.message.reply_text("أدخل رقم المستوى الذي ينتمي له السؤال (مثلاً 1):")
    return Q_LEVEL

async def q_receive_level(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not text.isdigit():
        await update.message.reply_text("الرجاء إدخال رقم صحيح للمستوى:")
        return Q_LEVEL
    
    level_num = int(text)
    db = SessionLocal()
    try:
        level = db.query(Level).filter(Level.level_number == level_num).first()
        if not level:
            await update.message.reply_text(f"❌ المستوى {level_num} غير موجود.")
            return ConversationHandler.END
        context.user_data['q_level_id'] = level.id
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📝 كويز سريع لدرس معني", callback_data="qtype:lesson")],
            [InlineKeyboardButton("🏆 امتحان نهائي للمستوى", callback_data="qtype:final")]
        ])
        await update.message.reply_text("حدد نوع السؤال:", reply_markup=keyboard)
        return Q_TYPE
    finally:
        db.close()

async def q_receive_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    qtype = query.data.split(":")[1]
    
    if qtype == "final":
        context.user_data['is_final_exam'] = True
        context.user_data['lesson_id'] = None
        await query.message.reply_text("تمام (سؤال امتحان مستوى نهائي).\nاكتب نص السؤال:")
        return Q_TEXT
    else:
        context.user_data['is_final_exam'] = False
        level_id = context.user_data['q_level_id']
        db = SessionLocal()
        try:
            lessons = db.query(Lesson).filter(Lesson.level_id == level_id).order_by(Lesson.order).all()
            if not lessons:
                await query.message.reply_text("❌ لا يوجد دروس في هذا المستوى بعد. أضف درساً أولاً.")
                return ConversationHandler.END
            
            keyboard = []
            for l in lessons:
                keyboard.append([InlineKeyboardButton(f"درس {l.order + 1}: {l.title}", callback_data=f"select_lesson:{l.id}")])
            
            await query.message.reply_text("اختر الدرس المطلوب إرفاق السؤال له:", reply_markup=InlineKeyboardMarkup(keyboard))
            return Q_LESSON_SELECT
        finally:
            db.close()

async def q_receive_lesson_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    lesson_id = int(query.data.split(":")[1])
    context.user_data['lesson_id'] = lesson_id
    await query.message.reply_text("تمام (سؤال كويز درس).\nاكتب نص السؤال:")
    return Q_TEXT

async def q_receive_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['q_text'] = update.message.text.strip()
    await update.message.reply_text("اكتب الخيار الأول (A):")
    return Q_OPT_A

async def q_receive_opt_a(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['q_opt_a'] = update.message.text.strip()
    await update.message.reply_text("اكتب الخيار الثاني (B):")
    return Q_OPT_B

async def q_receive_opt_b(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['q_opt_b'] = update.message.text.strip()
    await update.message.reply_text("اكتب الخيار الثالث (C):")
    return Q_OPT_C

async def q_receive_opt_c(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['q_opt_c'] = update.message.text.strip()
    await update.message.reply_text("اكتب الخيار الرابع (D):")
    return Q_OPT_D

async def q_receive_opt_d(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['q_opt_d'] = update.message.text.strip()
    await update.message.reply_text("ما هو الخيار الصحيح؟ اكتب الحرف فقط (A أو B أو C أو D):")
    return Q_CORRECT

async def q_receive_correct(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    correct = update.message.text.strip().upper()
    if correct not in ['A', 'B', 'C', 'D']:
        await update.message.reply_text("❌ الحرف يجب أن يكون A أو B أو C أو D فقط:")
        return Q_CORRECT
    context.user_data['q_correct'] = correct
    await update.message.reply_text("اكتب شرح الإجابة (أو أرسل 'لا يوجد'):")
    return Q_EXPLANATION

async def q_receive_explanation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    exp = update.message.text.strip()
    explanation = None if exp.lower() in ['لا يوجد', 'none', '-'] else exp

    db = SessionLocal()
    try:
        new_q = Question(
            level_id=context.user_data['q_level_id'],
            lesson_id=context.user_data.get('lesson_id'),
            is_final_exam=context.user_data['is_final_exam'],
            question_text=context.user_data['q_text'],
            option_a=context.user_data['q_opt_a'],
            option_b=context.user_data['q_opt_b'],
            option_c=context.user_data['q_opt_c'],
            option_d=context.user_data['q_opt_d'],
            correct_answer=context.user_data['q_correct'],
            explanation=explanation
        )
        db.add(new_q)
        db.commit()
        await update.message.reply_text("✅ تم حفظ السؤال بنجاح!")
    finally:
        db.close()

    context.user_data.clear()
    return ConversationHandler.END

async def cancel_addquestion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("تم إلغاء إضافة السؤال.")
    return ConversationHandler.END

def get_admin_quiz_handlers():
    return [
        ConversationHandler(
            entry_points=[CommandHandler("addquestion", start_addquestion)],
            states={
                Q_LEVEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, q_receive_level)],
                Q_TYPE: [CallbackQueryHandler(q_receive_type, pattern="^qtype:")],
                Q_LESSON_SELECT: [CallbackQueryHandler(q_receive_lesson_select, pattern="^select_lesson:")],
                Q_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, q_receive_text)],
                Q_OPT_A: [MessageHandler(filters.TEXT & ~filters.COMMAND, q_receive_opt_a)],
                Q_OPT_B: [MessageHandler(filters.TEXT & ~filters.COMMAND, q_receive_opt_b)],
                Q_OPT_C: [MessageHandler(filters.TEXT & ~filters.COMMAND, q_receive_opt_c)],
                Q_OPT_D: [MessageHandler(filters.TEXT & ~filters.COMMAND, q_receive_opt_d)],
                Q_CORRECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, q_receive_correct)],
                Q_EXPLANATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, q_receive_explanation)],
            },
            fallbacks=[CommandHandler("cancel", cancel_addquestion)]
        )
    ]
