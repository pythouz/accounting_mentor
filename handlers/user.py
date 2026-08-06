from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters
from database.models import SessionLocal, User, AccessCode

WAITING_FOR_CODE = 1

def get_main_keyboard():
    keyboard = [['📚 المادة العلمية للمستوى الحالي', '📝 ابدأ اختبار المستوى'],
                ['📊 تقدمي (مستواي الحالي)', '📞 الدعم الفني']]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    telegram_id = update.effective_user.id
    first_name = update.effective_user.first_name
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        if user:
            if user.is_banned:
                await update.message.reply_text(
                    "🚫 حسابك محظور حالياً من استخدام البوت.\n\n"
                    "لو حصلت على كود تفعيل جديد من الأدمن، اكتبه هنا لإعادة تفعيل حسابك "
                    "(هتكمل من نفس مستواك زي ما كان بالظبط):"
                )
                return WAITING_FOR_CODE
            await update.message.reply_text(f"أهلاً بك مجدداً يا {first_name}! 👋\nحسابك مفعّل بالكامل.", reply_markup=get_main_keyboard())
            return ConversationHandler.END
        
        welcome_text = (f"أهلاً بك يا {first_name} في بوت إعداد المحاسبين. 🎯\n\n"
                        "يرجى كتابة كلمة التفعيل الخاصة بك للبدء:")
        await update.message.reply_text(welcome_text)
        return WAITING_FOR_CODE
    finally:
        db.close()

async def check_activation_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    telegram_id = update.effective_user.id
    username = update.effective_user.username
    entered_code = update.message.text.strip()
    db = SessionLocal()
    try:
        code_record = db.query(AccessCode).filter(AccessCode.code == entered_code).first()
        if not code_record or code_record.is_used:
            await update.message.reply_text("❌ الكلمة غير صحيحة، أو تم استخدامها بالفعل من قبل شخص آخر.\n\nيرجى إعادة كتابة كلمة تفعيل صحيحة:")
            return WAITING_FOR_CODE

        existing_user = db.query(User).filter(User.telegram_id == telegram_id).first()
        if existing_user:
            # المستخدم موجود بالفعل ومحظور، وبيعيد التفعيل بكود جديد
            existing_user.is_banned = False
            existing_user.username = username
            code_record.is_used = True
            code_record.used_by_id = existing_user.id
            db.commit()
            await update.message.reply_text(
                f"✅ تم إعادة تفعيل حسابك بنجاح!\nأنت لسه في المستوى {existing_user.current_level} وهتكمل منه عادي.",
                reply_markup=get_main_keyboard()
            )
            return ConversationHandler.END

        new_user = User(telegram_id=telegram_id, username=username, current_level=1, is_banned=False)
        db.add(new_user)
        db.flush()
        code_record.is_used = True
        code_record.used_by_id = new_user.id
        db.commit()
        await update.message.reply_text("✅ تم تفعيل حسابك بنجاح! تم فتح خصائص البوت والمستوى الأول.", reply_markup=get_main_keyboard())
        return ConversationHandler.END
    except Exception as e:
        db.rollback()
        # إظهار الخطأ التقني مباشرة في التيليجرام لمعرفة السبب بدقة
        await update.message.reply_text(f"❌ حدث خطأ تقني أثناء التفعيل:\n`{str(e)}`", parse_mode="Markdown")
        print(e)
        return ConversationHandler.END
    finally:
        db.close()

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("تم إلغاء عملية التسجيل.")
    return ConversationHandler.END

def get_user_conv_handler():
    return ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={WAITING_FOR_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_activation_code)]},
        fallbacks=[CommandHandler('cancel', cancel)]
    )
