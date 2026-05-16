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

    # Pilih template secara acak sebanyak 'amount' (misal: 3)
    selected_templates = [random.choice(templates) for _ in range(amount)]
    
    # 2. EKSEKUSI PARALEL (Multithreading) KHUSUS UNTUK CALL AI
    ai_results = []
    
    # Gunakan ThreadPoolExecutor. max_workers diset sesuai jumlah soal.
    with concurrent.futures.ThreadPoolExecutor(max_workers=amount) as executor:
        # Submit tugas ke thread pool (HANYA fungsi call AI, tanpa kirim session DB)
        # Kita menggunakan dictionary (future_to_template) agar tahu template mana menghasilkan AI yang mana
        future_to_template = {
            executor.submit(generate_soal_with_ai, tmpl): tmpl for tmpl in selected_templates
        }
        
        # As_completed akan langsung memproses hasil yang sudah selesai duluan
        for future in concurrent.futures.as_completed(future_to_template):
            template_asal = future_to_template[future]
            try:
                ai_json = future.result()
                # Kita gabungkan hasil AI dengan ID template asal agar bisa disimpan ke DB
                ai_results.append({
                    "template_id": template_asal.id,
                    "ai_data": ai_json
                })
            except Exception as e:
                # Log jika ada 1 soal gagal digenerate, sisanya tetap jalan
                print(f"Error generate AI untuk template {template_asal.id}: {e}")

    # Validasi jika gagal total
    if not ai_results:
        raise HTTPException(status_code=502, detail="Gagal meng-generate seluruh soal dari AI. Silakan coba lagi.")

    # 3. SIMPAN KE DATABASE DI MAIN THREAD (Aman & Tidak Bentrok)
    formatted_questions_for_frontend = []
    
    for result_item in ai_results:
        template_id = result_item["template_id"]
        ai_data = result_item["ai_data"]
        
        # Simpan Soal Generated
        new_gen_question = QuestionGenerated(
            question_template_id=template_id,
            topic=topic,
            difficulty=ai_data.get("difficulty", difficulty),
            question_text=ai_data["question_text"]
        )
        session.add(new_gen_question)
        session.commit()
        session.refresh(new_gen_question)
        
        # Simpan Jawaban
        list_jawaban = ai_data.get("answers", [])
        random.shuffle(list_jawaban) # Acak opsi A, B, C, D
        label_urut = ["A", "B", "C", "D"]
        formatted_options = []
        
        for idx, ans in enumerate(list_jawaban[:4]):
            new_answer = AnswerGenerated(
                question_generated_id=new_gen_question.id,
                option_label=OptionLabelEnum(label_urut[idx]), 
                option_text=str(ans["text"]),
                is_correct=ans["is_correct"]
            )
            session.add(new_answer)
            
            # Format untuk balikan ke response JSON
            formatted_options.append({
                "label": label_urut[idx],
                "text": str(ans["text"])
            })
            
        session.commit() # Commit seluruh jawaban
        
        # Link Soal ke Sesi Ujian (ExamQuestion)
        exam_q = ExamQuestion(
            exam_session_id=exam_session_id,
            generated_question_id=new_gen_question.id,
            status="UNANSWERED"
        )
        session.add(exam_q)
        session.commit()
        session.refresh(exam_q)
        
        # Susun data untuk dikirim ke Frontend
        formatted_questions_for_frontend.append({
            "exam_question_id": exam_q.id,
            "text": new_gen_question.question_text,
            "difficulty": new_gen_question.difficulty,
            "options": formatted_options
        })
        
    return formatted_questions_for_frontend