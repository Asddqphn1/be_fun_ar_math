
import random
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.database import get_session
from app.models import AnswerGenerated, OptionLabelEnum, QuestionGenerated, QuestionTemplate
from app.schemas.soal_generated import QuestionGeneratedResponse
from app.schemas.soal_template import GenerateRequest, QuestionResponse
from app.services.ai_service import generate_soal_with_ai



router = APIRouter(
    prefix="/soal",
    tags=["bank_soal"],
)

@router.get("/", response_model=List[QuestionResponse])
def getAllSoal(session: Session= Depends(get_session)):
    soal = select(QuestionTemplate) 
    results = session.exec(soal).all()
    return results

@router.get("/{soal_id}", response_model=QuestionResponse)
def getSoalById(soal_id: int, session: Session= Depends(get_session)):
    soal = session.get(QuestionTemplate, soal_id)
    if not soal:
        raise HTTPException(status_code=404, detail="Soal tidak ditemukan")
    return soal

@router.get("/generated", response_model=List[QuestionGeneratedResponse])
def getAllGeneratedSoal(session: Session= Depends(get_session)):
    soal = select(QuestionGenerated)
    results = session.exec(soal).all()
    return results

@router.post("/generate", response_model=QuestionResponse)
def generate_question(
    request: GenerateRequest, 
    session: Session = Depends(get_session)
):
    # 1. Cari Template
    statement = select(QuestionTemplate).where(
        QuestionTemplate.topic == request.topic,
        QuestionTemplate.difficulty == request.difficulty
    )
    templates = session.exec(statement).all()
    
    if not templates:
        raise HTTPException(status_code=404, detail="Template topik ini belum ada!")
    
    selected_template = random.choice(templates)
    
    # 2. Panggil AI
    ai_result = generate_soal_with_ai(selected_template)

    # 3. Simpan Parent (Logic Int Baru)
    # Kita pakai .get() biar aman kalau key difficulty gak ada
    final_difficulty = ai_result.get("difficulty", request.difficulty)
    
    new_question = QuestionGenerated(
        question_template_id=selected_template.id,
        topic=ai_result["topic"],
        difficulty=final_difficulty, # Langsung Int
        question_text=ai_result["question_text"]
    )
    session.add(new_question)
    session.commit()
    session.refresh(new_question)
    
    # 4. Simpan Jawaban (Logic Shuffle Lama)
    list_jawaban = ai_result.get("answers", [])
    if list_jawaban:
        random.shuffle(list_jawaban)
        label_urut = ["A", "B", "C", "D"]
        for index, ans in enumerate(list_jawaban):
            if index < 4:
                new_answer = AnswerGenerated(
                    question_generated_id=new_question.id,
                    option_label=OptionLabelEnum(label_urut[index]), 
                    option_text=str(ans["text"]),
                    is_correct=ans["is_correct"]
                )
                session.add(new_answer)
        session.commit()
        session.refresh(new_question)
    
    # 5. RETURN SAKTI (BALIK KE CODINGAN LAMA)
    # Gak usah manual mapping. Biarkan FastAPI kerja sendiri.
    return new_question