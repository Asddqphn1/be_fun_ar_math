# app/schemas/ujian_request.py
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel
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

# --- REQUEST START ---
class StartExamRequest(BaseModel):
    topic: str

# --- REQUEST SUBMIT BATCH (Dari Flutter) ---
class AnswerItem(BaseModel):
    exam_question_id: int
    answer_label: OptionLabelEnum
    time_seconds: int = 0  # Waktu menjawab soal ini (dalam detik)

class SubmitBatchRequest(BaseModel):
    session_id: int
    answers: List[AnswerItem] # List jawaban user (3 atau 4 item)

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