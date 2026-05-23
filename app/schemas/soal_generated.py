from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel
# Hapus DifficultyEnum dari import
from app.models import OptionLabelEnum

class AnswerGeneratedResponse(BaseModel):
    option_label: OptionLabelEnum
    option_text: str
    is_correct: bool

class QuestionGeneratedResponse(BaseModel):
    id: int
    question_template_id: Optional[int]
    topic: str
    difficulty: int
    question_text: str
    created_at: datetime
    answers: List[AnswerGeneratedResponse]

# Model Pydantic untuk mapping respons dari LLM
class AnswerAI(BaseModel):
    label: str
    text: str
    is_correct: bool

class QuestionAI(BaseModel):
    question_text: str
    answers: List[AnswerAI]

class BatchQuestionsGenerated(BaseModel):
    questions: List[QuestionAI]
