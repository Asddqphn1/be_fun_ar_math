from datetime import datetime
from pydantic import BaseModel, ConfigDict

from app.models import OptionLabelEnum


class StartExamRequest(BaseModel):
    topic: str # User mau ujian topik apa? (Misal: "Segitiga")

class ExamSessionResponse(BaseModel):
    session_id: int
    topic: str # Kita simpan topik ini di sesi biar gak lupa (NOTE: Nanti kita bahas cara simpannya)
    start_time: datetime
    status: str
    message: str

class NextQuestionRequest(BaseModel):
    session_id: int

class ExamQuestionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True) # Biar bisa baca object DB
    
    exam_question_id: int # ID Tracking (Penting buat submit jawaban)
    question: dict # Isinya detail soal (teks, pilihan ganda)


class SubmitAnswerRequest(BaseModel):
    exam_question_id: int # ID soal yang mau dijawab
    answer_label: OptionLabelEnum # Jawaban user (A/B/C/D)

class SubmitAnswerResponse(BaseModel):
    is_correct: bool
    correct_label: str
    message: str
    current_score: float
    next_level: int # Kasih tau user dia naik/turun level