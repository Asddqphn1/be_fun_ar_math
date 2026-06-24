from typing import List, Optional
import random
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from datetime import datetime

from app.core.depedencies import NilaiServicesDepedencies
from app.database import get_session
from app.helper.generated_helper import _generate_batch_questions, _select_existing_batch_questions
from app.models import AnswerGenerated, ExamQuestion, User, ExamSession, ExamStatusEnum, QuestionGenerated, SchoolToken
from app.routes.auth import get_current_user
from app.schemas.base_schemas import BaseResponse
from app.schemas.ujian_request import (
    StartExamRequest, 
    StartExamTokenRequest,
    ExamBatchResponse, 
    SubmitBatchRequest, 
    SubmitBatchTokenRequest,
    SubmitBatchResponse, 
    ExamValuesUsers,
    ExamDetailResponse
)
 # Import Satpam

TOTAL_BATCHES = 4
BATCH_SIZE = 10
ROUTING_DOWN_THRESHOLD = 0.4
ROUTING_UP_THRESHOLD = 0.8
RAPID_GUESS_RATIO = 0.1
TIME_LIMITS = {
    1: {"normal": 30},
    2: {"normal": 45},
    3: {"normal": 60},
}

MAX_QUESTIONS = TOTAL_BATCHES * BATCH_SIZE


def _stage1_difficulty_plan(batch_size: int) -> List[tuple[int, int]]:
    level2_count = batch_size // 2
    level1_count = batch_size - level2_count
    return [(1, level1_count), (2, level2_count)]


def _route_level(correct_count: int, valid_count: int) -> int:
    if valid_count <= 0:
        return 2
    accuracy = correct_count / valid_count
    if accuracy <= ROUTING_DOWN_THRESHOLD:
        return 1
    if accuracy >= ROUTING_UP_THRESHOLD:
        return 3
    return 2


def _route_message(next_level: int, valid_count: int) -> str:
    if valid_count <= 0:
        return "Routing default ke Level 2 (data waktu belum tersedia)"
    if next_level == 1:
        return "Routing ke Level 1 (Mudah)"
    if next_level == 3:
        return "Routing ke Level 3 (Sulit)"
    return "Routing ke Level 2 (Sedang)"


def _build_batch_questions(
    session: Session,
    exam_session_id: int,
    topic: str,
    batch_num: int,
    difficulty_plan: List[tuple[int, int]],
    school_token_id: Optional[int] = None,
):
    questions = []
    for difficulty, amount in difficulty_plan:
        if amount <= 0:
            continue
        if school_token_id is None:
            questions.extend(
                _generate_batch_questions(
                    session=session,
                    exam_session_id=exam_session_id,
                    topic=topic,
                    difficulty=difficulty,
                    amount=amount,
                    batch_num=batch_num,
                )
            )
        else:
            questions.extend(
                _select_existing_batch_questions(
                    session=session,
                    exam_session_id=exam_session_id,
                    topic=topic,
                    difficulty=difficulty,
                    amount=amount,
                    batch_num=batch_num,
                    school_token_id=school_token_id,
                )
            )
    if len(questions) > 1:
        random.shuffle(questions)
    return questions

router = APIRouter(prefix="/ujian", tags=["Sistem Ujian"])


@router.post("/start", response_model=ExamBatchResponse)
def start_exam(
    request: StartExamRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    # Cek sesi ongoing
    ongoing = session.exec(select(ExamSession).where(
         ExamSession.user_id == current_user.id,
         ExamSession.status == ExamStatusEnum.ONGOING
    )).first()
    
    if ongoing:
        # Cari soal-soal yang belum dijawab di sesi ini
        unanswered_questions = session.exec(select(ExamQuestion).where(
            ExamQuestion.exam_session_id == ongoing.id,
            ExamQuestion.user_answer_label == None
        )).all()
        
        if unanswered_questions:
            # Hitung riwayat skor & jawaban user di sesi ini (sebelum terputus)
            answered_questions = session.exec(select(ExamQuestion).where(
                ExamQuestion.exam_session_id == ongoing.id,
                ExamQuestion.user_answer_label != None
            )).all()
            
            past_correct = sum(1 for eq in answered_questions if eq.is_correct)
            past_answered = len(answered_questions)
            
            # REKONSTRUKSI SOAL UNTUK DILANJUTKAN USER
            formatted_questions = []
            for eq in unanswered_questions:
                # Ambil detail soal
                gen_q = session.get(QuestionGenerated, eq.generated_question_id)
                # Ambil pilihan ganda
                answers_db = session.exec(select(AnswerGenerated).where(
                    AnswerGenerated.question_generated_id == gen_q.id
                )).all()
                formatted_options = [
                    {"label": a.option_label, "text": a.option_text} for a in answers_db
                ]
                formatted_questions.append({
                    "exam_question_id": eq.id,
                    "text": gen_q.question_text,
                    "difficulty": gen_q.difficulty,
                    "options": formatted_options
                })
                
            return ExamBatchResponse(
                session_id=ongoing.id,
                batch_index=ongoing.current_batch_index,
                questions=formatted_questions,
                message=f"Melanjutkan Ujian (Batch {ongoing.current_batch_index})",
                is_finished=False,
                past_total_correct=past_correct,
                past_total_answered=past_answered,
                past_total_score=ongoing.total_score
            )
        else:
            # Jika sesi ongoing tapi tidak punya soal (mungkin karena AI error sebelumnya)
            # Hapus sesi yang rusak ini agar bisa buat yang baru
            session.delete(ongoing)
            session.commit()

    # Buat Sesi Baru
    new_session = ExamSession(
        user_id=current_user.id,
        topic=request.topic,
        start_time=datetime.now(),
        current_difficulty_level=2, # Start Level 2 (routing stage)
        current_batch_index=1,      # Start Batch 1
        status=ExamStatusEnum.ONGOING,
        total_score=0.0
    )
    session.add(new_session)
    session.commit()
    session.refresh(new_session)
    
    try:
        # Generate BATCH 1 (routing stage)
        questions = _build_batch_questions(
            session=session,
            exam_session_id=new_session.id,
            topic=request.topic,
            batch_num=1,
            difficulty_plan=_stage1_difficulty_plan(BATCH_SIZE),
        )
    except Exception as e:
        # Jika AI gagal, hapus sesi ini agar tidak menggantung rusak
        session.delete(new_session)
        session.commit()
        raise HTTPException(status_code=500, detail=f"Gagal menyiapkan ujian dari AI: {str(e)}")
    
    return ExamBatchResponse(
        session_id=new_session.id,
        batch_index=1,
        questions=questions,
        message=f"Batch 1 dimulai ({BATCH_SIZE} Soal)",
        is_finished=False
    )


@router.post("/start-token", response_model=ExamBatchResponse)
def start_exam_token(
    request: StartExamTokenRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    school_token = session.exec(
        select(SchoolToken).where(SchoolToken.token == request.token)
    ).first()
    if not school_token:
        raise HTTPException(status_code=400, detail="Token sekolah tidak valid")

    ongoing = session.exec(select(ExamSession).where(
        ExamSession.user_id == current_user.id,
        ExamSession.status == ExamStatusEnum.ONGOING,
        ExamSession.school_token_id == school_token.id,
        ExamSession.topic == request.topic
    )).first()

    if ongoing:
        unanswered_questions = session.exec(select(ExamQuestion).where(
            ExamQuestion.exam_session_id == ongoing.id,
            ExamQuestion.user_answer_label == None
        )).all()

        if unanswered_questions:
            answered_questions = session.exec(select(ExamQuestion).where(
                ExamQuestion.exam_session_id == ongoing.id,
                ExamQuestion.user_answer_label != None
            )).all()

            past_correct = sum(1 for eq in answered_questions if eq.is_correct)
            past_answered = len(answered_questions)

            formatted_questions = []
            for eq in unanswered_questions:
                gen_q = session.get(QuestionGenerated, eq.generated_question_id)
                answers_db = session.exec(select(AnswerGenerated).where(
                    AnswerGenerated.question_generated_id == gen_q.id
                )).all()
                formatted_options = [
                    {"label": a.option_label, "text": a.option_text} for a in answers_db
                ]
                formatted_questions.append({
                    "exam_question_id": eq.id,
                    "text": gen_q.question_text,
                    "difficulty": gen_q.difficulty,
                    "options": formatted_options
                })

            return ExamBatchResponse(
                session_id=ongoing.id,
                batch_index=ongoing.current_batch_index,
                questions=formatted_questions,
                message=f"Melanjutkan Ujian (Batch {ongoing.current_batch_index})",
                is_finished=False,
                past_total_correct=past_correct,
                past_total_answered=past_answered,
                past_total_score=ongoing.total_score
            )
        else:
            session.delete(ongoing)
            session.commit()

    new_session = ExamSession(
        user_id=current_user.id,
        topic=request.topic,
        start_time=datetime.now(),
        current_difficulty_level=2,
        current_batch_index=1,
        status=ExamStatusEnum.ONGOING,
        total_score=0.0,
        school_token_id=school_token.id,
    )
    session.add(new_session)
    session.commit()
    session.refresh(new_session)

    try:
        questions = _build_batch_questions(
            session=session,
            exam_session_id=new_session.id,
            topic=request.topic,
            batch_num=1,
            difficulty_plan=_stage1_difficulty_plan(BATCH_SIZE),
            school_token_id=school_token.id,
        )
    except HTTPException:
        session.delete(new_session)
        session.commit()
        raise
    except Exception as e:
        session.delete(new_session)
        session.commit()
        raise HTTPException(status_code=500, detail=f"Gagal menyiapkan ujian: {str(e)}")

    return ExamBatchResponse(
        session_id=new_session.id,
        batch_index=1,
        questions=questions,
        message=f"Batch 1 dimulai ({BATCH_SIZE} Soal)",
        is_finished=False
    )

# @router.post("/next", response_model=ExamQuestionResponse)
# def get_next_question(
#     request: NextQuestionRequest,
#     current_user: User = Depends(get_current_user),
#     session: Session = Depends(get_session)
# ):
#     # 1. Validasi Sesi Ujian
#     exam_session = session.get(ExamSession, request.session_id)
#     if not exam_session:
#         raise HTTPException(status_code=404, detail="Sesi ujian tidak ditemukan")
    
#     if exam_session.user_id != current_user.id:
#         raise HTTPException(status_code=403, detail="Ini bukan sesi ujianmu!")
        
#     if exam_session.status == ExamStatusEnum.COMPLETED:
#         raise HTTPException(status_code=400, detail="Ujian ini sudah selesai!")

#     # 2. Cek Level User Saat Ini
#     current_level = exam_session.current_difficulty_level
#     topic = exam_session.topic
    
#     # 3. Cari Template yang Cocok (Topik sama + Level sama)
#     #    Kalau user jago (Level naik), kita carikan template yang susah.
#     statement = select(QuestionTemplate).where(
#         QuestionTemplate.topic == topic,
#         QuestionTemplate.difficulty == current_level
#     )
#     templates = session.exec(statement).all()
    
#     # FALLBACK: Kalau template level itu habis/gak ada, cari level apa aja yang penting topik sama
#     # (Supaya user gak stuck error 404 kalau Pak Guru lupa input soal susah)
#     if not templates:
#         print(f"Warning: Template Level {current_level} kosong. Mengambil acak.")
#         statement_fallback = select(QuestionTemplate).where(QuestionTemplate.topic == topic)
#         templates = session.exec(statement_fallback).all()
        
#     if not templates:
#         raise HTTPException(status_code=404, detail=f"Belum ada bank soal untuk topik {topic}")

#     # 4. Pilih 1 Template Secara Acak & Generate AI
#     selected_template = random.choice(templates)
#     ai_result = generate_soal_with_ai(selected_template)
    
#     # 5. Simpan Soal Hasil AI (Copy logic dari routes/soal.py)
#     #    Kita simpan biar ada history-nya
#     final_difficulty = ai_result.get("difficulty", current_level)
    
#     new_gen_question = QuestionGenerated(
#         question_template_id=selected_template.id,
#         topic=topic,
#         difficulty=final_difficulty,
#         question_text=ai_result["question_text"]
#     )
#     session.add(new_gen_question)
#     session.commit()
#     session.refresh(new_gen_question)
    
#     # Simpan Jawaban
#     list_jawaban = ai_result.get("answers", [])
#     if list_jawaban:
#         random.shuffle(list_jawaban)
#         label_urut = ["A", "B", "C", "D"]
#         for index, ans in enumerate(list_jawaban):
#             if index < 4:
#                 new_answer = AnswerGenerated(
#                     question_generated_id=new_gen_question.id,
#                     option_label=OptionLabelEnum(label_urut[index]), 
#                     option_text=str(ans["text"]),
#                     is_correct=ans["is_correct"]
#                 )
#                 session.add(new_answer)
#     session.commit() # Commit jawaban
    
#     # 6. LINK KE SESI UJIAN (PENTING!)
#     #    Kita catat: "Di sesi ini, user dapet soal ID sekian"
#     exam_question_entry = ExamQuestion(
#         exam_session_id=exam_session.id,
#         generated_question_id=new_gen_question.id,
#         status="UNANSWERED" # (Optional kalau mau nambah status per soal)
#     )
#     session.add(exam_question_entry)
#     session.commit()
#     session.refresh(exam_question_entry)
    
#     # 7. Format Response biar enak dibaca Frontend
#     #    Frontend cuma butuh Teks Soal & Pilihan Ganda (Jawaban Benar JANGAN dikirim!)
    
#     # Ambil jawaban dari DB yang baru disimpan
#     answers_query = select(AnswerGenerated).where(AnswerGenerated.question_generated_id == new_gen_question.id)
#     answers_db = session.exec(answers_query).all()
    
#     formatted_answers = [
#         {"label": a.option_label, "text": a.option_text} for a in answers_db
#     ]

#     return ExamQuestionResponse(
#         exam_question_id=exam_question_entry.id,
#         question={
#             "text": new_gen_question.question_text,
#             "difficulty": new_gen_question.difficulty,
#             "options": formatted_answers
#         }
#     )

# @router.post("/submit", response_model=SubmitAnswerResponse)
# def submit_answer(
#     request: SubmitAnswerRequest,
#     current_user: User = Depends(get_current_user),
#     session: Session = Depends(get_session)
# ):
#     # 1. Cari data "Sejarah Soal" ini
#     exam_question = session.get(ExamQuestion, request.exam_question_id)
#     if not exam_question:
#         raise HTTPException(status_code=404, detail="Data soal tidak ditemukan")
    
#     # Validasi: Jangan sampai jawab 2 kali
#     if exam_question.user_answer_label is not None:
#         raise HTTPException(status_code=400, detail="Soal ini sudah dijawab!")

#     # 2. Ambil Sesi Ujian-nya
#     exam_session = session.get(ExamSession, exam_question.exam_session_id)
#     if exam_session.user_id != current_user.id:
#         raise HTTPException(status_code=403, detail="Bukan ujianmu!")

#     # 3. Cek Kunci Jawaban (Ambil dari tabel GeneratedAnswers)
#     #    Kita cari mana opsi yang labelnya dipilih user
#     #    Relasi: ExamQuestion -> QuestionGenerated -> AnswerGenerated
    
#     # Cara query: Cari jawaban yang labelnya == request.answer_label DAN punya question_id yang sama
#     stmt = select(AnswerGenerated).where(
#         AnswerGenerated.question_generated_id == exam_question.generated_question_id,
#         AnswerGenerated.option_label == request.answer_label
#     )
#     user_choice = session.exec(stmt).first()
    
#     # Cari label yang BENAR buat dikasih tau ke user
#     stmt_correct = select(AnswerGenerated).where(
#         AnswerGenerated.question_generated_id == exam_question.generated_question_id,
#         AnswerGenerated.is_correct
#     )
#     correct_answer_data = session.exec(stmt_correct).first()
#     correct_label = correct_answer_data.option_label if correct_answer_data else "Unknown"

#     # 4. Tentukan Benar/Salah
#     is_correct = False
#     if user_choice and user_choice.is_correct:
#         is_correct = True
    
#     # 5. LOGIKA ADAPTIF (Disini otaknya!) 🧠
#     poin = 0
#     message = ""
    
#     if is_correct:
#         # Rumus Poin: Level * 10 (Level 1=10, Level 3=30)
#         poin = exam_session.current_difficulty_level * 10
#         exam_session.total_score += poin
        
#         # Logic Naik Level
#         if exam_session.current_difficulty_level < 3:
#             exam_session.current_difficulty_level += 1
#             message = "Jawaban Benar! Level Naik! 🚀"
#         else:
#             message = "Jawaban Benar! Pertahankan performa! 🔥"
#     else:
#         # Logic Turun Level
#         if exam_session.current_difficulty_level > 1:
#             exam_session.current_difficulty_level -= 1
#             message = "Jawaban Salah. Level Turun, ayo fokus lagi! 📉"
#         else:
#             message = "Jawaban Salah. Jangan menyerah! 💪"

#     # 6. Simpan Jawaban User ke DB
#     exam_question.user_answer_label = request.answer_label
#     exam_question.is_correct = is_correct
#     session.add(exam_question)
    
#     # 7. Cek Apakah Ujian Sudah Selesai? (Count soal yg sudah dijawab)
#     #    Kita hitung berapa row di exam_questions milik sesi ini
#     count_stmt = select(func.count(ExamQuestion.id)).where(ExamQuestion.exam_session_id == exam_session.id)
#     total_answered = session.exec(count_stmt).one()
    
#     if total_answered >= MAX_QUESTIONS:
#         exam_session.status = ExamStatusEnum.COMPLETED
#         exam_session.end_time = datetime.now()
#         message += " (UJIAN SELESAI)"
        
#     session.add(exam_session)
#     session.commit()
#     session.refresh(exam_session)

#     return SubmitAnswerResponse(
#         is_correct=is_correct,
#         correct_label=correct_label,
#         message=message,
#         current_score=exam_session.total_score,
#         next_level=exam_session.current_difficulty_level
#     )

@router.post("/submit-batch", response_model=SubmitBatchResponse)
def submit_batch(
    request: SubmitBatchRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    # 1. Validasi Sesi
    exam_session = session.get(ExamSession, request.session_id)
    if not exam_session or exam_session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Sesi tidak valid")
    
    if exam_session.status == ExamStatusEnum.COMPLETED:
        raise HTTPException(status_code=400, detail="Ujian sudah selesai")

    # 2. Proses Jawaban User
    correct_count = 0
    valid_count = 0
    score_gained = 0.0
    total_time = 0
    timed_count = 0
    
    for answer_item in request.answers:
        # Cari soal di DB
        exam_question = session.get(ExamQuestion, answer_item.exam_question_id)
        if not exam_question: 
            continue # Skip kalau ID ngaco
            
        gen_q = session.get(QuestionGenerated, exam_question.generated_question_id)
        question_level = gen_q.difficulty if gen_q else exam_session.current_difficulty_level
        time_limit = TIME_LIMITS.get(question_level, TIME_LIMITS[2])
        rapid_threshold = time_limit["normal"] * RAPID_GUESS_RATIO
        is_rapid_guess = (
            answer_item.time_seconds > 0
            and answer_item.time_seconds <= rapid_threshold
        )

        correct_ans = session.exec(select(AnswerGenerated).where(
            AnswerGenerated.question_generated_id == exam_question.generated_question_id,
            AnswerGenerated.is_correct
        )).first()
        
        is_correct = False
        if correct_ans and correct_ans.option_label == answer_item.answer_label:
            is_correct = True

        if not is_rapid_guess:
            valid_count += 1
            if is_correct:
                correct_count += 1
                score_gained += (question_level * 10)
        
        # Update DB (termasuk waktu menjawab)
        exam_question.user_answer_label = answer_item.answer_label
        exam_question.is_correct = is_correct
        exam_question.thinking_time_seconds = answer_item.time_seconds
        if answer_item.time_seconds > 0:
            total_time += answer_item.time_seconds
            timed_count += 1
        session.add(exam_question)
    
    avg_time = total_time / timed_count if timed_count > 0 else 0
    time_bonus = 0.0

    exam_session.total_score += score_gained
    next_level = _route_level(correct_count, valid_count)
    exam_session.current_difficulty_level = next_level
    message = _route_message(next_level, valid_count)

    # 4. Tentukan Nasib Selanjutnya (Next Batch atau Finish?)
    current_batch = exam_session.current_batch_index
    next_batch_response = None
    
    if current_batch < TOTAL_BATCHES:
        next_batch_index = current_batch + 1
        exam_session.current_batch_index = next_batch_index

        new_questions = _build_batch_questions(
            session=session,
            exam_session_id=exam_session.id,
            topic=exam_session.topic,
            batch_num=next_batch_index,
            difficulty_plan=[(exam_session.current_difficulty_level, BATCH_SIZE)],
        )
        
        next_batch_response = ExamBatchResponse(
            session_id=exam_session.id,
            batch_index=next_batch_index,
            questions=new_questions,
            message=f"Lanjut ke Batch {next_batch_index}",
            is_finished=False
        )
    else:
        # --- FINISH EXAM ---
        session.add(exam_session)
        session.commit()
        session.refresh(exam_session)

    return SubmitBatchResponse(
        batch_index_just_finished=current_batch,
        score_gained=score_gained,
        correct_count=correct_count,
        total_score=exam_session.total_score,
        next_level=exam_session.current_difficulty_level,
        message=message,
        avg_time_seconds=round(avg_time, 1),
        time_bonus=time_bonus,
        next_batch=next_batch_response
    )


@router.post("/submit-batch-token", response_model=SubmitBatchResponse)
def submit_batch_token(
    request: SubmitBatchTokenRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    exam_session = session.get(ExamSession, request.session_id)
    if not exam_session or exam_session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Sesi tidak valid")

    if exam_session.status == ExamStatusEnum.COMPLETED:
        raise HTTPException(status_code=400, detail="Ujian sudah selesai")

    if not exam_session.school_token_id:
        raise HTTPException(status_code=400, detail="Token sekolah tidak terkait di sesi ini")

    school_token = session.exec(
        select(SchoolToken).where(SchoolToken.token == request.token)
    ).first()
    if not school_token:
        raise HTTPException(status_code=400, detail="Token sekolah tidak valid")

    if exam_session.school_token_id != school_token.id:
        raise HTTPException(status_code=403, detail="Token sekolah tidak sesuai dengan sesi ini")

    correct_count = 0
    valid_count = 0
    score_gained = 0.0
    total_time = 0
    timed_count = 0

    for answer_item in request.answers:
        exam_question = session.get(ExamQuestion, answer_item.exam_question_id)
        if not exam_question:
            continue

        gen_q = session.get(QuestionGenerated, exam_question.generated_question_id)
        question_level = gen_q.difficulty if gen_q else exam_session.current_difficulty_level
        time_limit = TIME_LIMITS.get(question_level, TIME_LIMITS[2])
        rapid_threshold = time_limit["normal"] * RAPID_GUESS_RATIO
        is_rapid_guess = (
            answer_item.time_seconds > 0
            and answer_item.time_seconds <= rapid_threshold
        )

        correct_ans = session.exec(select(AnswerGenerated).where(
            AnswerGenerated.question_generated_id == exam_question.generated_question_id,
            AnswerGenerated.is_correct
        )).first()

        is_correct = False
        if correct_ans and correct_ans.option_label == answer_item.answer_label:
            is_correct = True

        if not is_rapid_guess:
            valid_count += 1
            if is_correct:
                correct_count += 1
                score_gained += (question_level * 10)

        exam_question.user_answer_label = answer_item.answer_label
        exam_question.is_correct = is_correct
        exam_question.thinking_time_seconds = answer_item.time_seconds
        if answer_item.time_seconds > 0:
            total_time += answer_item.time_seconds
            timed_count += 1
        session.add(exam_question)

    avg_time = total_time / timed_count if timed_count > 0 else 0
    time_bonus = 0.0

    exam_session.total_score += score_gained
    next_level = _route_level(correct_count, valid_count)
    exam_session.current_difficulty_level = next_level
    message = _route_message(next_level, valid_count)

    current_batch = exam_session.current_batch_index
    next_batch_response = None

    if current_batch < TOTAL_BATCHES:
        next_batch_index = current_batch + 1
        exam_session.current_batch_index = next_batch_index

        new_questions = _build_batch_questions(
            session=session,
            exam_session_id=exam_session.id,
            topic=exam_session.topic,
            batch_num=next_batch_index,
            difficulty_plan=[(exam_session.current_difficulty_level, BATCH_SIZE)],
            school_token_id=exam_session.school_token_id,
        )

        next_batch_response = ExamBatchResponse(
            session_id=exam_session.id,
            batch_index=next_batch_index,
            questions=new_questions,
            message=f"Lanjut ke Batch {next_batch_index}",
            is_finished=False
        )
    else:
        session.add(exam_session)
        session.commit()
        session.refresh(exam_session)

    return SubmitBatchResponse(
        batch_index_just_finished=current_batch,
        score_gained=score_gained,
        correct_count=correct_count,
        total_score=exam_session.total_score,
        next_level=exam_session.current_difficulty_level,
        message=message,
        avg_time_seconds=round(avg_time, 1),
        time_bonus=time_bonus,
        next_batch=next_batch_response
    )


@router.patch("/complete/{session_id}", response_model=BaseResponse)
def complete_exam(
    session_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """Endpoint untuk menyelesaikan ujian (update status ONGOING -> COMPLETED)."""
    exam_session = session.get(ExamSession, session_id)
    
    if not exam_session:
        raise HTTPException(status_code=404, detail="Sesi ujian tidak ditemukan")
    
    if exam_session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Ini bukan sesi ujianmu!")
    
    if exam_session.status == ExamStatusEnum.COMPLETED:
        raise HTTPException(status_code=400, detail="Ujian ini sudah berstatus COMPLETED")
    
    exam_session.status = ExamStatusEnum.COMPLETED
    exam_session.end_time = datetime.now()
    
    session.add(exam_session)
    session.commit()
    session.refresh(exam_session)
    
    return BaseResponse(
        success="true",
        message="Ujian berhasil diselesaikan",
        data={
            "session_id": exam_session.id,
            "status": exam_session.status,
            "total_score": exam_session.total_score,
            "end_time": str(exam_session.end_time)
        }
    )


@router.get("/nilai", response_model=List[ExamValuesUsers])
def getNilai(
    token: str,
    services: NilaiServicesDepedencies,
    session: Session = Depends(get_session),
):
    school_token = session.exec(
        select(SchoolToken).where(SchoolToken.token == token)
    ).first()
    if not school_token:
        raise HTTPException(status_code=400, detail="Token sekolah tidak valid")
    return services.getNilaiByToken(school_token.id)


@router.get("/nilai/{user_id}", response_model=BaseResponse[List[ExamValuesUsers]])
def getNilaiByUserId(
    user_id: int,
    token: str,
    services: NilaiServicesDepedencies,
    session: Session = Depends(get_session),
):
    school_token = session.exec(
        select(SchoolToken).where(SchoolToken.token == token)
    ).first()
    if not school_token:
        raise HTTPException(status_code=400, detail="Token sekolah tidak valid")

    hasil = services.getNilaiByUserIdAndToken(user_id, school_token.id)
    
    if not hasil:
        raise HTTPException(status_code=404, detail="Data nilai tidak ditemukan untuk user ini")
    
    return BaseResponse(
        success="true",
        message="Data nilai berhasil ditemukan",
        data=hasil
    )


@router.get("/nilai/nama/{nama}", response_model=BaseResponse[List[ExamValuesUsers]])
def getNilaiByNama(
    nama: str,
    token: str,
    services: NilaiServicesDepedencies,
    session: Session = Depends(get_session),
):
    school_token = session.exec(
        select(SchoolToken).where(SchoolToken.token == token)
    ).first()
    if not school_token:
        raise HTTPException(status_code=400, detail="Token sekolah tidak valid")

    hasil = services.getNilaiByNamaAndToken(nama, school_token.id)

    if not hasil:
        raise HTTPException(status_code=404, detail="Data nilai tidak ditemukan untuk nama ini")

    return BaseResponse(
        success="true",
        message="Data nilai berhasil ditemukan",
        data=hasil
    )


@router.get("/nilai/detail/{session_id}", response_model=BaseResponse[ExamDetailResponse])
def getNilaiDetail(
    session_id: int,
    token: str,
    services: NilaiServicesDepedencies,
    session: Session = Depends(get_session),
):
    """
    Endpoint detail nilai per sesi ujian.
    Menampilkan:
    - Setiap soal yang didapatkan user
    - Jawaban yang dipilih user
    - Apakah jawaban benar atau salah
    - Jawaban yang benar (selalu ditampilkan)
    - Waktu berpikir per soal
    - Statistik: total benar, total salah, akurasi %
    """
    school_token = session.exec(
        select(SchoolToken).where(SchoolToken.token == token)
    ).first()
    if not school_token:
        raise HTTPException(status_code=400, detail="Token sekolah tidak valid")

    hasil = services.getNilaiDetail(session_id, school_token.id)

    if not hasil:
        raise HTTPException(
            status_code=404,
            detail="Sesi ujian tidak ditemukan atau belum selesai"
        )

    return BaseResponse(
        success="true",
        message="Detail nilai berhasil ditemukan",
        data=hasil
    )


