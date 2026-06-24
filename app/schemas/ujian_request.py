# app/schemas/ujian_request.py
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field
from app.models import OptionLabelEnum

# --- SCHEMA DATA SOAL PER ITEM ---
class OptionResponse(BaseModel):
    label: str
    text: str

class QuestionItem(BaseModel):
    exam_question_id: int
    text: str
    difficulty: int
    options: List[OptionResponse]

# --- RESPONSE BATCH (Dikirim ke Flutter) ---
class ExamBatchResponse(BaseModel):
    session_id: int
    batch_index: int # Batch ke-1, 2, atau 3
    questions: List[QuestionItem]
    message: str
    is_finished: bool = False # Kalau true, frontend tampilin nilai
    
    # REKAP DATA SESI LAMA (Bila Resume)
    past_total_correct: int = 0
    past_total_answered: int = 0
    past_total_score: float = 0.0

# --- REQUEST START ---
class StartExamRequest(BaseModel):
    topic: str

class StartExamTokenRequest(BaseModel):
    token: str = Field(pattern=r"^\d{6}$")
    topic: str

# --- REQUEST SUBMIT BATCH (Dari Flutter) ---
class AnswerItem(BaseModel):
    exam_question_id: int
    answer_label: OptionLabelEnum
    time_seconds: int = 0  # Waktu menjawab soal ini (dalam detik)

class SubmitBatchRequest(BaseModel):
    session_id: int
    answers: List[AnswerItem] # List jawaban user (10-12 item)

class SubmitBatchTokenRequest(SubmitBatchRequest):
    token: str = Field(pattern=r"^\d{6}$")

# --- RESPONSE HASIL SUBMIT ---
class SubmitBatchResponse(BaseModel):
    batch_index_just_finished: int
    score_gained: float
    correct_count: int
    total_score: float
    next_level: int
    message: str
    avg_time_seconds: float = 0.0  # Rata-rata waktu menjawab per soal (detik)
    time_bonus: float = 0.0  # Bonus skor dari kecepatan menjawab
    
    # Data Batch Berikutnya (Kalau belum selesai)
    next_batch: Optional[ExamBatchResponse] = None

# --- SCHEMA DETAIL NILAI (Review Soal per Sesi) ---
class CorrectAnswerDetail(BaseModel):
    """Detail jawaban yang benar (ditampilkan kalau user salah)"""
    label: str
    text: str

class QuestionDetailItem(BaseModel):
    """Detail per soal: soal, jawaban user, benar/salah, dan koreksi"""
    exam_question_id: int
    question_text: str
    difficulty: int
    batch_number: int
    options: List[OptionResponse]
    user_answer_label: Optional[str] = None
    user_answer_text: Optional[str] = None
    is_correct: bool
    correct_answer: CorrectAnswerDetail  # Selalu ditampilkan
    thinking_time_seconds: int = 0

class ExamDetailResponse(BaseModel):
    """Response lengkap detail nilai per sesi ujian"""
    session_id: int
    topic: str
    status: str
    total_score: float
    start_time: datetime
    end_time: Optional[datetime] = None
    user: "DataUser"
    total_questions: int
    total_correct: int
    total_wrong: int
    accuracy_percent: float
    questions: List[QuestionDetailItem]

# ... Schema User/Nilai lama tetep ada di bawah ...
class DataUser(BaseModel):
    full_name : str
    email : str

class ExamValuesUsers(BaseModel):
    start_time : datetime
    end_time : datetime
    topic : str
    status: str
    total_score : int
    user: DataUser