import logging
from typing import List
import random
from fastapi import HTTPException
from sqlmodel import Session, select

from app.models import (
    AnswerGenerated, ExamQuestion, OptionLabelEnum, QuestionGenerated, 
    QuestionTemplate
)

from app.schemas.ujian_request import (
    QuestionItem, OptionResponse,
)
from app.services.ai_service import generate_soal_with_ai 

logger = logging.getLogger(__name__)


def _generate_batch_questions(session: Session, exam_session_id: int, topic: str, difficulty: int, amount: int, batch_num: int) -> List[QuestionItem]:
    """
    Fungsi bantu untuk generate N soal sekaligus.
    """
    questions_output = []

    # 1. Cari Template
    stmt = select(QuestionTemplate).where(
        QuestionTemplate.topic == topic,
        QuestionTemplate.difficulty == difficulty
    )
    templates = session.exec(stmt).all()
    
    # Fallback jika template habis
    if not templates:
        logger.warning(f"Template Level {difficulty} kosong. Mengambil acak topic {topic}.")
        stmt_fallback = select(QuestionTemplate).where(QuestionTemplate.topic == topic)
        templates = session.exec(stmt_fallback).all()
    
    if not templates:
        raise HTTPException(status_code=404, detail=f"Bank soal habis untuk topik {topic}")

    # 2. Loop sebanyak 'amount' (3 atau 4 kali)
    for _ in range(amount):
        selected_template = random.choice(templates)
        
        # Panggil AI (Satu per satu biar aman JSON-nya)
        ai_result = generate_soal_with_ai(selected_template)
        
        final_difficulty = ai_result.get("difficulty", difficulty)
        
        # Simpan Generated Question
        new_gen_question = QuestionGenerated(
            question_template_id=selected_template.id,
            topic=topic,
            difficulty=final_difficulty,
            question_text=ai_result["question_text"]
        )
        session.add(new_gen_question)
        session.commit()
        session.refresh(new_gen_question)
        
        # Simpan Jawaban
        list_jawaban = ai_result.get("answers", [])
        formatted_options = []
        if list_jawaban:
            random.shuffle(list_jawaban)
            label_urut = ["A", "B", "C", "D"]
            for index, ans in enumerate(list_jawaban):
                if index < 4:
                    new_answer = AnswerGenerated(
                        question_generated_id=new_gen_question.id,
                        option_label=OptionLabelEnum(label_urut[index]), 
                        option_text=str(ans["text"]),
                        is_correct=ans["is_correct"]
                    )
                    session.add(new_answer)
                    formatted_options.append(OptionResponse(label=label_urut[index], text=str(ans["text"])))
        session.commit()

        # Link ke Sesi Ujian
        exam_question_entry = ExamQuestion(
            exam_session_id=exam_session_id,
            generated_question_id=new_gen_question.id,
            batch_number=batch_num
        )
        session.add(exam_question_entry)
        session.commit()
        session.refresh(exam_question_entry)

        # Masukkan ke list output
        questions_output.append(QuestionItem(
            exam_question_id=exam_question_entry.id,
            text=new_gen_question.question_text,
            difficulty=new_gen_question.difficulty,
            options=formatted_options
        ))
    
    return questions_output