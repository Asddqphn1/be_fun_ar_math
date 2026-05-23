import logging
from typing import List
import random
from fastapi import HTTPException
from sqlmodel import Session, select
import concurrent.futures

from app.models import (
    AnswerGenerated, ExamQuestion, OptionLabelEnum, QuestionGenerated, 
    QuestionTemplate
)

from app.schemas.ujian_request import (
    QuestionItem, OptionResponse,
)
from app.services.ai_service import generate_soal_with_ai 

logger = logging.getLogger(__name__)


def _generate_batch_questions(
    session, 
    exam_session_id: int, 
    topic: str, 
    difficulty: int, 
    amount: int, 
    batch_num: int
):
    # 1. AMBIL TEMPLATE DARI DB
    statement = select(QuestionTemplate).where(
        QuestionTemplate.topic == topic,
        QuestionTemplate.difficulty == difficulty
    )
    templates = session.exec(statement).all()

    # Fallback jika template di level tersebut kosong
    if not templates:
        statement_fallback = select(QuestionTemplate).where(QuestionTemplate.topic == topic)
        templates = session.exec(statement_fallback).all()
        
    if not templates:
        raise HTTPException(status_code=404, detail=f"Belum ada bank soal untuk topik {topic}")

    # Pilih SATU template secara acak sebagai base
    selected_template = random.choice(templates)
    
    # 2. PANGGIL AI SATU KALI UNTUK MENGHASILKAN 3 VARIASI SEKALIGUS
    try:
        # Mengembalikan object Pydantic BatchQuestionsGenerated
        batch_response = generate_soal_with_ai(selected_template)
    except Exception as e:
        logger.error(f"Gagal meng-generate batch soal dari AI: {e}")
        raise HTTPException(status_code=502, detail="Gagal meng-generate soal dari AI. Silakan coba lagi.")

    if not batch_response or not batch_response.questions:
        raise HTTPException(status_code=502, detail="AI tidak mengembalikan daftar soal dengan benar.")

    # Ambil soal sebanyak 'amount' (jaga-jaga jika AI mengembalikan lebih/kurang)
    ai_questions = batch_response.questions[:amount]

    # 3. SIMPAN KE DATABASE (TUNGGAL COMMIT)
    formatted_questions_for_frontend = []
    
    for ai_q in ai_questions:
        # Simpan Soal Generated
        new_gen_question = QuestionGenerated(
            question_template_id=selected_template.id,
            topic=topic,
            difficulty=difficulty, # Gunakan difficulty dari level yg di-generate
            question_text=ai_q.question_text
        )
        session.add(new_gen_question)
        session.flush() # Flush agar dapat ID
        
        # Simpan Jawaban
        list_jawaban = ai_q.answers
        # Pastikan list_jawaban diacak agar posisi benar bervariasi
        list_jawaban_dict = [{"text": j.text, "is_correct": j.is_correct} for j in list_jawaban]
        random.shuffle(list_jawaban_dict)
        label_urut = ["A", "B", "C", "D"]
        formatted_options = []
        
        for idx, ans in enumerate(list_jawaban_dict[:4]):
            new_answer = AnswerGenerated(
                question_generated_id=new_gen_question.id,
                option_label=OptionLabelEnum(label_urut[idx]), 
                option_text=ans["text"],
                is_correct=ans["is_correct"]
            )
            session.add(new_answer)
            
            # Format untuk balikan ke response JSON
            formatted_options.append({
                "label": label_urut[idx],
                "text": ans["text"]
            })
            
        # Link Soal ke Sesi Ujian (ExamQuestion)
        exam_q = ExamQuestion(
            exam_session_id=exam_session_id,
            generated_question_id=new_gen_question.id,
            status="UNANSWERED"
        )
        session.add(exam_q)
        session.flush() # Flush lagi untuk mendapatkan exam_q.id
        
        # Susun data untuk dikirim ke Frontend
        formatted_questions_for_frontend.append({
            "exam_question_id": exam_q.id,
            "text": new_gen_question.question_text,
            "difficulty": new_gen_question.difficulty,
            "options": formatted_options
        })

    # COMMIT SATU KALI DI AKHIR
    session.commit()
        
    return formatted_questions_for_frontend