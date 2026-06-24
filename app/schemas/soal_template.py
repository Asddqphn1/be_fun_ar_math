from typing import List
from pydantic import BaseModel, Field

from app.models import OptionLabelEnum


class GenerateRequest(BaseModel):
    topic: str
    difficulty: int

class GenerateBulkRequest(BaseModel):
    token: str = Field(pattern=r"^\d{6}$")
    topic: str
    difficulty: int

class AnswerResponse(BaseModel):
    option_label: OptionLabelEnum
    option_text: str
    is_correct: bool

class QuestionResponse(BaseModel):
    id: int
    topic: str
    difficulty: int
    question_text: str
    answers: List[AnswerResponse]
