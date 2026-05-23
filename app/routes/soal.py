
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
from app.services.ai_service import generate_soal_with_ai, parse_bulk_questions, stream_bulk_soal_with_ai



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

    difficulty_levels = [1, 2, 3]
    per_difficulty = 80
    templates_by_level = {}
    missing_levels = []

    for level in difficulty_levels:
        templates = session.exec(
            select(QuestionTemplate).where(
                QuestionTemplate.topic == request.topic,
                QuestionTemplate.difficulty == level,
            )
        ).all()

        if not templates:
            missing_levels.append(level)
            continue

        templates_by_level[level] = templates

    if missing_levels:
        missing_str = ", ".join(str(level) for level in missing_levels)
        raise HTTPException(
            status_code=404,
            detail=f"Template topik ini belum ada untuk difficulty: {missing_str}",
        )

    total_questions = per_difficulty * len(difficulty_levels)

    def _sse_event(event: str, payload: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(payload)}\n\n"

    def _iter_thinking_events(details, level: int):
        if isinstance(details, dict):
            detail_type = details.get("type")
            text = details.get("text")
            if detail_type == "thinking" and text:
                yield _sse_event("thinking", {"text": text, "difficulty": level})
            return

        if isinstance(details, list):
            for item in details:
                yield from _iter_thinking_events(item, level)

    def _pick_template(options: List[QuestionTemplate], last_template_id):
        if len(options) == 1:
            return options[0]
        candidates = [t for t in options if t.id != last_template_id]
        return random.choice(candidates)

    async def event_stream():
        saved_total = 0
        yield _sse_event(
            "start",
            {
                "total": total_questions,
                "per_difficulty": per_difficulty,
                "levels": difficulty_levels,
            },
        )

        try:
            warning_sent = False
            max_attempts = int(os.getenv("BULK_MAX_ATTEMPTS", "2"))
            batch_size = int(os.getenv("BULK_BATCH_SIZE", "10"))
            if batch_size <= 0:
                batch_size = 10
            if max_attempts <= 0:
                max_attempts = 2

            for level in difficulty_levels:
                templates = templates_by_level[level]
                yield _sse_event(
                    "status",
                    {"message": f"generate soal difficulty {level}", "difficulty": level},
                )

                remaining = per_difficulty
                saved_in_level = 0
                last_template_id = None

                while remaining > 0:
                    template = _pick_template(templates, last_template_id)
                    last_template_id = template.id

                    batch_total = min(batch_size, remaining)
                    attempts = 0
                    ai_questions = []

                    while attempts < max_attempts and not ai_questions:
                        attempts += 1
                        yield _sse_event(
                            "status",
                            {
                                "message": f"think/reasoning difficulty {level}",
                                "difficulty": level,
                                "attempt": attempts,
                            },
                        )

                        content_parts = []
                        async for chunk in stream_bulk_soal_with_ai(
                            template,
                            total_questions=batch_total,
                        ):
                            if not chunk:
                                continue
                            reasoning_details = chunk.get("reasoning_details")
                            if reasoning_details:
                                for event in _iter_thinking_events(reasoning_details, level):
                                    yield event

                            token = chunk.get("text")
                            if token:
                                content_parts.append(token)
                                yield _sse_event(
                                    "token",
                                    {"text": token, "difficulty": level},
                                )

                        content = "".join(content_parts)
                        try:
                            ai_questions = parse_bulk_questions(content, batch_total)
                        except Exception:
                            ai_questions = []

                    if not ai_questions:
                        yield _sse_event(
                            "warning",
                            {
                                "saved": saved_total,
                                "total": total_questions,
                                "difficulty": level,
                                "attempts": attempts,
                            },
                        )
                        warning_sent = True
                        break

                    for ai_q in ai_questions[:batch_total]:
                        if saved_in_level >= per_difficulty:
                            break

                        list_jawaban = ai_q["answers"]
                        random.shuffle(list_jawaban)

                        new_question = QuestionGenerated(
                            question_template_id=template.id,
                            topic=request.topic,
                            difficulty=level,
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

                        saved_total += 1
                        saved_in_level += 1
                        remaining = per_difficulty - saved_in_level

                        yield _sse_event(
                            "question",
                            {
                                "index": saved_total,
                                "difficulty": level,
                                "question_id": new_question.id,
                            },
                        )

                        if saved_in_level % 10 == 0 or saved_in_level == per_difficulty:
                            yield _sse_event(
                                "progress",
                                {
                                    "saved": saved_total,
                                    "total": total_questions,
                                    "difficulty": level,
                                    "saved_in_level": saved_in_level,
                                    "total_in_level": per_difficulty,
                                },
                            )

                if warning_sent:
                    break

            if saved_total < total_questions and not warning_sent:
                yield _sse_event(
                    "warning",
                    {"saved": saved_total, "total": total_questions},
                )

            yield _sse_event("done", {"total_saved": saved_total})
        except Exception as e:
            session.rollback()
            yield _sse_event("error", {"message": str(e)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )