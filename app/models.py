from typing import Optional, List
from sqlmodel import SQLModel, Field, Relationship
from datetime import datetime
from sqlalchemy import Text
from enum import Enum as PyEnum

# Kita pakai Enum cuma buat Label (A,B,C,D) dan Status Ujian
class OptionLabelEnum(str, PyEnum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"

class ExamStatusEnum(str, PyEnum):
    ONGOING = "ONGOING"
    COMPLETED = "COMPLETED"

# ==========================================
# 1. USER MANAGEMENT (Login Google)
# ==========================================
class User(SQLModel, table=True):
    __tablename__ = "users"
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True, max_length=255)
    full_name: str = Field(max_length=255)
    google_id: str = Field(unique=True, index=True, max_length=255) # ID dari Google
    avatar_url: Optional[str] = Field(default=None, sa_type=Text)
    created_at: datetime = Field(default_factory=datetime.now)
    
    # Relasi: Satu user bisa punya banyak sesi ujian
    exam_sessions: List["ExamSession"] = Relationship(back_populates="user")

# ==========================================
# 2. TEMPLATE SOAL (Data Mentah Guru)
# ==========================================
class QuestionTemplate(SQLModel, table=True):
    __tablename__ = "question_templates"
    id: Optional[int] = Field(default=None, primary_key=True)
    topic: str = Field(max_length=100)
    difficulty: int = Field(default=1) 
    
    question_text: str = Field(sa_type=Text) 
    created_at: datetime = Field(default_factory=datetime.now)
    
    answers: List["AnswerTemplate"] = Relationship(back_populates="template")
    generated_questions: List["QuestionGenerated"] = Relationship(back_populates="template")

class AnswerTemplate(SQLModel, table=True):
    __tablename__ = "answer_templates"
    id: Optional[int] = Field(default=None, primary_key=True)
    question_template_id: int = Field(foreign_key="question_templates.id")
    option_label: OptionLabelEnum 
    option_text: str = Field(sa_type=Text)
    is_correct: bool = Field(default=False)
    template: Optional[QuestionTemplate] = Relationship(back_populates="answers")

# ==========================================
# 3. GENERATED SOAL (Hasil AI)
# ==========================================
class QuestionGenerated(SQLModel, table=True):
    __tablename__ = "generated_questions"
    id: Optional[int] = Field(default=None, primary_key=True)
    question_template_id: Optional[int] = Field(default=None, foreign_key="question_templates.id")
    topic: str = Field(max_length=100)
    
    # UPDATE: Difficulty jadi int juga
    difficulty: int = Field(default=1)
    
    question_text: str = Field(sa_type=Text)
    created_at: datetime = Field(default_factory=datetime.now)
    
    template: Optional[QuestionTemplate] = Relationship(back_populates="generated_questions")
    answers: List["AnswerGenerated"] = Relationship(back_populates="question")
    
    # Relasi ke History Ujian (Soal ini pernah dipakai di sesi mana aja?)
    exam_questions: List["ExamQuestion"] = Relationship(back_populates="question_generated")

class AnswerGenerated(SQLModel, table=True):
    __tablename__ = "generated_answers"
    id: Optional[int] = Field(default=None, primary_key=True)
    question_generated_id: int = Field(foreign_key="generated_questions.id")
    option_label: OptionLabelEnum 
    option_text: str = Field(sa_type=Text)
    is_correct: bool = Field(default=False)
    question: Optional[QuestionGenerated] = Relationship(back_populates="answers")

# ==========================================
# 4. SESI UJIAN (Adaptive System Core)
# ==========================================
class ExamSession(SQLModel, table=True):
    __tablename__ = "exam_sessions"
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id")
    
    start_time: datetime = Field(default_factory=datetime.now)
    end_time: Optional[datetime] = Field(default=None) # Null kalau belum selesai
    current_difficulty_level: int = Field(default=1)
    topic: str = Field(max_length=100)
    
    status: ExamStatusEnum = Field(default=ExamStatusEnum.ONGOING)
    total_score: float = Field(default=0.0)
    
    user: Optional[User] = Relationship(back_populates="exam_sessions")
    exam_questions: List["ExamQuestion"] = Relationship(back_populates="exam_session")

class ExamQuestion(SQLModel, table=True):
    """
    Tabel ini mencatat: "User X di Sesi Y dapet Soal Z, jawabnya apa, bener gak?"
    """
    __tablename__ = "exam_questions"
    id: Optional[int] = Field(default=None, primary_key=True)
    
    exam_session_id: int = Field(foreign_key="exam_sessions.id")
    generated_question_id: int = Field(foreign_key="generated_questions.id")
    
    # Jawaban user (Bisa kosong dulu pas soal baru dikirim ke FE)
    user_answer_label: Optional[OptionLabelEnum] = Field(default=None)
    is_correct: bool = Field(default=False)
    
    # Data penting buat AI: Berapa lama user mikir? (Detik)
    thinking_time_seconds: int = Field(default=0)
    
    created_at: datetime = Field(default_factory=datetime.now)
    
    exam_session: Optional[ExamSession] = Relationship(back_populates="exam_questions")
    question_generated: Optional[QuestionGenerated] = Relationship(back_populates="exam_questions")