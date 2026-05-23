
import json
import os
import random
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from app.database import get_session
from app.models import AnswerGenerated, OptionLabelEnum, QuestionGenerated, QuestionTemplate, SchoolToken
from app.schemas.soal_generated import QuestionGeneratedResponse
from app.schemas.soal_template import GenerateBulkRequest, GenerateRequest, QuestionResponse
from app.services.ai_service import generate_bulk_soal_with_ai, generate_soal_with_ai



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


@router.post("/buatsoal")
def generate_bulk_questions(
    request: GenerateBulkRequest,
    session: Session = Depends(get_session),
):
    school_token = session.exec(
        select(SchoolToken).where(SchoolToken.token == request.token)
    ).first()
    if not school_token:
        raise HTTPException(status_code=400, detail="Token sekolah tidak valid")

    templates = session.exec(
        select(QuestionTemplate).where(
            QuestionTemplate.topic == request.topic,
            QuestionTemplate.difficulty == request.difficulty,
        )
    ).all()

    if not templates:
        raise HTTPException(status_code=404, detail="Template topik ini belum ada!")

    total_questions = 100

    def _sse_event(event: str, payload: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(payload)}\n\n"

    def event_stream():
        saved_count = 0
        yield _sse_event("start", {"total": total_questions})

        try:
            warning_sent = False
            max_attempts = int(os.getenv("BULK_MAX_ATTEMPTS", "2"))
            batch_size = int(os.getenv("BULK_BATCH_SIZE", "10"))
            if batch_size <= 0:
                batch_size = 10
            if max_attempts <= 0:
                max_attempts = 2

            def _pick_template(last_template_id):
                if len(templates) == 1:
                    return templates[0]
                candidates = [t for t in templates if t.id != last_template_id]
                return random.choice(candidates)

            remaining = total_questions
            last_template_id = None

            while remaining > 0:
                template = _pick_template(last_template_id)
                last_template_id = template.id

                batch_total = min(batch_size, remaining)
                attempts = 0
                ai_questions = []

                while attempts < max_attempts and not ai_questions:
                    attempts += 1
                    ai_questions = generate_bulk_soal_with_ai(
                        template,
                        total_questions=batch_total,
                    )

                if not ai_questions:
                    yield _sse_event(
                        "warning",
                        {"saved": saved_count, "total": total_questions, "attempts": attempts},
                    )
                    warning_sent = True
                    break

                for ai_q in ai_questions[:batch_total]:
                    if saved_count >= total_questions:
                        break

                    list_jawaban = ai_q["answers"]
                    random.shuffle(list_jawaban)

                    new_question = QuestionGenerated(
                        question_template_id=template.id,
                        topic=request.topic,
                        difficulty=request.difficulty,
                        question_text=ai_q["question_text"],
                        school_token_id=school_token.id,
                    )
                    session.add(new_question)
                    session.flush()

                    label_urut = ["A", "B", "C", "D"]
                    for idx, ans in enumerate(list_jawaban[:4]):
                        new_answer = AnswerGenerated(
                            question_generated_id=new_question.id,
                            option_label=OptionLabelEnum(label_urut[idx]),
                            option_text=str(ans["text"]),
                            is_correct=ans["is_correct"],
                        )
                        session.add(new_answer)

                    session.commit()

                    saved_count += 1
                    remaining = total_questions - saved_count

                    yield _sse_event("question", {"index": saved_count, "question_id": new_question.id})

                    if saved_count % 10 == 0 or saved_count == total_questions:
                        yield _sse_event(
                            "progress",
                            {"saved": saved_count, "total": total_questions},
                        )

            if saved_count < total_questions and not warning_sent:
                yield _sse_event(
                    "warning",
                    {"saved": saved_count, "total": total_questions},
                )

            yield _sse_event("done", {"total_saved": saved_count})
        except Exception as e:
            session.rollback()
            yield _sse_event("error", {"message": str(e)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )