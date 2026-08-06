from sqlalchemy import create_engine, Column, Integer, BigInteger, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from datetime import datetime
import os

DATABASE_URL = os.getenv("DATABASE_URL") or "sqlite:///bot_db.sqlite"

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, index=True, nullable=False)
    username = Column(String(100), nullable=True)
    current_level = Column(Integer, default=1)
    current_lesson_step = Column(Integer, default=0)  # فين وصل الطالب في دروس المستوى الحالي (0 = أول درس)
    is_banned = Column(Boolean, default=False)
    join_date = Column(DateTime, default=datetime.utcnow)
    used_code = relationship("AccessCode", back_populates="user", uselist=False)

class AccessCode(Base):
    __tablename__ = 'access_codes'
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, index=True, nullable=False)
    is_used = Column(Boolean, default=False)
    used_by_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    user = relationship("User", back_populates="used_code")

class Level(Base):
    __tablename__ = 'levels'
    id = Column(Integer, primary_key=True, index=True)
    level_number = Column(Integer, unique=True, nullable=False)
    title = Column(String(200), nullable=False)
    passing_score = Column(Integer, default=80)  # نسبة النجاح المطلوبة بالمئة
    is_final = Column(Boolean, default=False)  # آخر مستوى = تخرج
    lessons = relationship("Lesson", back_populates="level", order_by="Lesson.order")
    questions = relationship("Question", back_populates="level")

class Lesson(Base):
    __tablename__ = 'lessons'
    id = Column(Integer, primary_key=True, index=True)
    level_id = Column(Integer, ForeignKey('levels.id'), nullable=False)
    order = Column(Integer, nullable=False)  # ترتيب الدرس جوه المستوى (0, 1, 2...)
    content_type = Column(String(10), nullable=False)  # 'text' أو 'video'
    title = Column(String(200), nullable=True)  # عنوان قصير يظهر فوق الفيديو مثلاً
    content = Column(Text, nullable=False)  # النص نفسه لو 'text'، أو الـ file_id لو 'video'
    level = relationship("Level", back_populates="lessons")

class Question(Base):
    __tablename__ = 'questions'
    id = Column(Integer, primary_key=True, index=True)
    level_id = Column(Integer, ForeignKey('levels.id'), nullable=False)
    question_text = Column(Text, nullable=False)
    option_a = Column(String(200), nullable=False)
    option_b = Column(String(200), nullable=False)
    option_c = Column(String(200), nullable=False)
    option_d = Column(String(200), nullable=False)
    correct_answer = Column(String(1), nullable=False)
    explanation = Column(Text, nullable=True)  # ليه الإجابة الصح هي دي - يظهر لو المستخدم غلط
    level = relationship("Level", back_populates="questions")

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)
