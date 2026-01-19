import random
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, func, select
from datetime import datetime

from app.database import get_session
from app.models import AnswerGenerated, ExamQuestion, OptionLabelEnum, QuestionGenerated, QuestionTemplate, User, ExamSession, ExamStatusEnum
from app.routes.auth import get_current_user
from app.schemas.ujian import ExamQuestionResponse, ExamSessionResponse, NextQuestionRequest, StartExamRequest, SubmitAnswerRequest, SubmitAnswerResponse
from app.services.ai_service import generate_soal_with_ai # Import Satpam

MAX_QUESTIONS = 10

router = APIRouter(prefix="/ujian", tags=["Sistem Ujian"])


@router.post("/start", response_model=ExamSessionResponse)
def start_exam(
    request: StartExamRequest,
    current_user: User = Depends(get_current_user), # Harus Login!
    session: Session = Depends(get_session)
):
    """
    User memulai ujian baru untuk topik tertentu.
    Level otomatis dimulai dari 1 (EASY).
    """
    
    # 1. Cek apakah user punya ujian yang belum kelar? (Opsional, biar gak spam sesi)
    statement = select(ExamSession).where(
         ExamSession.user_id == current_user.id,
         ExamSession.status == ExamStatusEnum.ONGOING
    )
    ongoing = session.exec(statement).first()
    if ongoing:
        raise HTTPException(status_code=400, detail="Selesaikan dulu ujian yang sedang berjalan!")

    # 2. Buat Sesi Baru
    new_session = ExamSession(
        user_id=current_user.id,
        topic=request.topic,
        start_time=datetime.now(),
        current_difficulty_level=1, # Selalu mulai dari Level 1
        status=ExamStatusEnum.ONGOING,
        total_score=0.0
    )
    
    session.add(new_session)
    session.commit()
    session.refresh(new_session)
    
    return ExamSessionResponse(
        session_id=new_session.id,
        topic=request.topic,
        start_time=new_session.start_time,
        status=new_session.status,
        message="Sesi ujian berhasil dibuat. Silakan minta soal pertama!"
    )

@router.post("/next", response_model=ExamQuestionResponse)
def get_next_question(
    request: NextQuestionRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    # 1. Validasi Sesi Ujian
    exam_session = session.get(ExamSession, request.session_id)
    if not exam_session:
        raise HTTPException(status_code=404, detail="Sesi ujian tidak ditemukan")
    
    if exam_session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Ini bukan sesi ujianmu!")
        
    if exam_session.status == ExamStatusEnum.COMPLETED:
        raise HTTPException(status_code=400, detail="Ujian ini sudah selesai!")

    # 2. Cek Level User Saat Ini
    current_level = exam_session.current_difficulty_level
    topic = exam_session.topic
    
    # 3. Cari Template yang Cocok (Topik sama + Level sama)
    #    Kalau user jago (Level naik), kita carikan template yang susah.
    statement = select(QuestionTemplate).where(
        QuestionTemplate.topic == topic,
        QuestionTemplate.difficulty == current_level
    )
    templates = session.exec(statement).all()
    
    # FALLBACK: Kalau template level itu habis/gak ada, cari level apa aja yang penting topik sama
    # (Supaya user gak stuck error 404 kalau Pak Guru lupa input soal susah)
    if not templates:
        print(f"Warning: Template Level {current_level} kosong. Mengambil acak.")
        statement_fallback = select(QuestionTemplate).where(QuestionTemplate.topic == topic)
        templates = session.exec(statement_fallback).all()
        
    if not templates:
        raise HTTPException(status_code=404, detail=f"Belum ada bank soal untuk topik {topic}")

    # 4. Pilih 1 Template Secara Acak & Generate AI
    selected_template = random.choice(templates)
    ai_result = generate_soal_with_ai(selected_template)
    
    # 5. Simpan Soal Hasil AI (Copy logic dari routes/soal.py)
    #    Kita simpan biar ada history-nya
    final_difficulty = ai_result.get("difficulty", current_level)
    
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
    session.commit() # Commit jawaban
    
    # 6. LINK KE SESI UJIAN (PENTING!)
    #    Kita catat: "Di sesi ini, user dapet soal ID sekian"
    exam_question_entry = ExamQuestion(
        exam_session_id=exam_session.id,
        generated_question_id=new_gen_question.id,
        status="UNANSWERED" # (Optional kalau mau nambah status per soal)
    )
    session.add(exam_question_entry)
    session.commit()
    session.refresh(exam_question_entry)
    
    # 7. Format Response biar enak dibaca Frontend
    #    Frontend cuma butuh Teks Soal & Pilihan Ganda (Jawaban Benar JANGAN dikirim!)
    
    # Ambil jawaban dari DB yang baru disimpan
    answers_query = select(AnswerGenerated).where(AnswerGenerated.question_generated_id == new_gen_question.id)
    answers_db = session.exec(answers_query).all()
    
    formatted_answers = [
        {"label": a.option_label, "text": a.option_text} for a in answers_db
    ]

    return ExamQuestionResponse(
        exam_question_id=exam_question_entry.id,
        question={
            "text": new_gen_question.question_text,
            "difficulty": new_gen_question.difficulty,
            "options": formatted_answers
        }
    )

@router.post("/submit", response_model=SubmitAnswerResponse)
def submit_answer(
    request: SubmitAnswerRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    # 1. Cari data "Sejarah Soal" ini
    exam_question = session.get(ExamQuestion, request.exam_question_id)
    if not exam_question:
        raise HTTPException(status_code=404, detail="Data soal tidak ditemukan")
    
    # Validasi: Jangan sampai jawab 2 kali
    if exam_question.user_answer_label is not None:
        raise HTTPException(status_code=400, detail="Soal ini sudah dijawab!")

    # 2. Ambil Sesi Ujian-nya
    exam_session = session.get(ExamSession, exam_question.exam_session_id)
    if exam_session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Bukan ujianmu!")

    # 3. Cek Kunci Jawaban (Ambil dari tabel GeneratedAnswers)
    #    Kita cari mana opsi yang labelnya dipilih user
    #    Relasi: ExamQuestion -> QuestionGenerated -> AnswerGenerated
    
    # Cara query: Cari jawaban yang labelnya == request.answer_label DAN punya question_id yang sama
    stmt = select(AnswerGenerated).where(
        AnswerGenerated.question_generated_id == exam_question.generated_question_id,
        AnswerGenerated.option_label == request.answer_label
    )
    user_choice = session.exec(stmt).first()
    
    # Cari label yang BENAR buat dikasih tau ke user
    stmt_correct = select(AnswerGenerated).where(
        AnswerGenerated.question_generated_id == exam_question.generated_question_id,
        AnswerGenerated.is_correct
    )
    correct_answer_data = session.exec(stmt_correct).first()
    correct_label = correct_answer_data.option_label if correct_answer_data else "Unknown"

    # 4. Tentukan Benar/Salah
    is_correct = False
    if user_choice and user_choice.is_correct:
        is_correct = True
    
    # 5. LOGIKA ADAPTIF (Disini otaknya!) 🧠
    poin = 0
    message = ""
    
    if is_correct:
        # Rumus Poin: Level * 10 (Level 1=10, Level 3=30)
        poin = exam_session.current_difficulty_level * 10
        exam_session.total_score += poin
        
        # Logic Naik Level
        if exam_session.current_difficulty_level < 3:
            exam_session.current_difficulty_level += 1
            message = "Jawaban Benar! Level Naik! 🚀"
        else:
            message = "Jawaban Benar! Pertahankan performa! 🔥"
    else:
        # Logic Turun Level
        if exam_session.current_difficulty_level > 1:
            exam_session.current_difficulty_level -= 1
            message = "Jawaban Salah. Level Turun, ayo fokus lagi! 📉"
        else:
            message = "Jawaban Salah. Jangan menyerah! 💪"

    # 6. Simpan Jawaban User ke DB
    exam_question.user_answer_label = request.answer_label
    exam_question.is_correct = is_correct
    session.add(exam_question)
    
    # 7. Cek Apakah Ujian Sudah Selesai? (Count soal yg sudah dijawab)
    #    Kita hitung berapa row di exam_questions milik sesi ini
    count_stmt = select(func.count(ExamQuestion.id)).where(ExamQuestion.exam_session_id == exam_session.id)
    total_answered = session.exec(count_stmt).one()
    
    if total_answered >= MAX_QUESTIONS:
        exam_session.status = ExamStatusEnum.COMPLETED
        exam_session.end_time = datetime.now()
        message += " (UJIAN SELESAI)"
        
    session.add(exam_session)
    session.commit()
    session.refresh(exam_session)

    return SubmitAnswerResponse(
        is_correct=is_correct,
        correct_label=correct_label,
        message=message,
        current_score=exam_session.total_score,
        next_level=exam_session.current_difficulty_level
    )