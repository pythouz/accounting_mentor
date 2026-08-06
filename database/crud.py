from sqlalchemy.orm import Session
from database.models import User, AccessCode

def activate_user_code(db: Session, telegram_id: int, username: str, entered_code: str) -> tuple[bool, str]:
    # البحث عن الكود في قاعدة البيانات
    code_record = db.query(AccessCode).filter(AccessCode.code == entered_code).first()
    
    # إذا كان الكود غير موجود أو تم استخدامه مسبقاً
    if not code_record or code_record.is_used:
        return False, "❌ الكود غير صحيح أو تم استخدامه من قبل. تأكد من الكود وحاول مجدداً."
    
    # التحقق مما إذا كان المستخدم مسجلاً بالفعل (في حال حذف البوت ورجع)
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if not user:
        # إنشاء مستخدم جديد وتعيينه على المستوى الأول
        user = User(telegram_id=telegram_id, username=username, current_level=1)
        db.add(user)
        db.flush() # لتوليد المعرف (ID) الخاص بالمستخدم قبل الحفظ النهائي
    
    # حرق الكود: جعله مستخدماً وربطه بمعرف المستخدم
    code_record.is_used = True
    code_record.used_by_id = user.id
    
    # حفظ التعديلات في قاعدة البيانات
    db.commit()
    return True, "✅ تم تفعيل حسابك بنجاح! أنت الآن جاهز لبدء المستوى الأول."
