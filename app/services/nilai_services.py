from sqlmodel import Session, select
from sqlalchemy.orm import selectinload

from app.models import (
    ExamSession, ExamStatusEnum, User, ExamQuestion,
    QuestionGenerated, AnswerGenerated
)


class NilaiServices:
    def __init__(self, session : Session):
        self.session = session
    
    def getNilai(self):
        nilai = select(ExamSession).where(
            ExamSession.status == ExamStatusEnum.COMPLETED
        ).options(selectinload(ExamSession.user))
        tampil_nilai = self.session.exec(nilai).all()
        return tampil_nilai

    def getNilaiByUserId(self, user_id: int):
        query = select(ExamSession).where(
            ExamSession.user_id == user_id,
            ExamSession.status == ExamStatusEnum.COMPLETED
        ).options(selectinload(ExamSession.user))
        hasil = self.session.exec(query).all()
        return hasil

    def getNilaiByNama(self, nama: str):
        query = select(ExamSession).join(User).where(
            User.full_name.ilike(f"%{nama}%"),
            ExamSession.status == ExamStatusEnum.COMPLETED
        ).options(selectinload(ExamSession.user))
        hasil = self.session.exec(query).all()
        return hasil

    def getNilaiByToken(self, school_token_id: int):
        nilai = select(ExamSession).where(
            ExamSession.status == ExamStatusEnum.COMPLETED,
            ExamSession.school_token_id == school_token_id,
        ).options(selectinload(ExamSession.user))
        tampil_nilai = self.session.exec(nilai).all()
        return tampil_nilai

    def getNilaiByUserIdAndToken(self, user_id: int, school_token_id: int):
        query = select(ExamSession).where(
            ExamSession.user_id == user_id,
            ExamSession.status == ExamStatusEnum.COMPLETED,
            ExamSession.school_token_id == school_token_id,
        ).options(selectinload(ExamSession.user))
        hasil = self.session.exec(query).all()
        return hasil

    def getNilaiByNamaAndToken(self, nama: str, school_token_id: int):
        query = select(ExamSession).join(User).where(
            User.full_name.ilike(f"%{nama}%"),
            ExamSession.status == ExamStatusEnum.COMPLETED,
            ExamSession.school_token_id == school_token_id,
        ).options(selectinload(ExamSession.user))
        hasil = self.session.exec(query).all()
        return hasil

    def getNilaiDetail(self, session_id: int, school_token_id: int):
        """
        Ambil detail lengkap sesi ujian:
        - Info sesi (skor, topik, waktu)
        - Tiap soal yang dikerjakan user
        - Jawaban user, benar/salah, dan jawaban benar-nya
        """
        # 1. Ambil sesi ujian + user
        exam_session = self.session.exec(
            select(ExamSession).where(
                ExamSession.id == session_id,
                ExamSession.status == ExamStatusEnum.COMPLETED,
                ExamSession.school_token_id == school_token_id,
            ).options(selectinload(ExamSession.user))
        ).first()

        if not exam_session:
            return None

        # 2. Ambil semua exam_questions di sesi ini, urut by batch lalu id
        exam_questions = self.session.exec(
            select(ExamQuestion).where(
                ExamQuestion.exam_session_id == session_id
            ).order_by(ExamQuestion.batch_number, ExamQuestion.id)
        ).all()

        # 3. Build detail per soal
        question_details = []
        total_correct = 0
        total_wrong = 0

        for eq in exam_questions:
            # Ambil soal generated
            gen_q = self.session.get(QuestionGenerated, eq.generated_question_id)
            if not gen_q:
                continue

            # Ambil semua opsi jawaban
            answers = self.session.exec(
                select(AnswerGenerated).where(
                    AnswerGenerated.question_generated_id == gen_q.id
                )
            ).all()

            # Cari jawaban yang benar
            correct_ans = next((a for a in answers if a.is_correct), None)

            # Cari teks jawaban user
            user_answer_text = None
            if eq.user_answer_label:
                user_choice = next(
                    (a for a in answers if a.option_label == eq.user_answer_label),
                    None
                )
                if user_choice:
                    user_answer_text = user_choice.option_text

            # Hitung benar/salah
            if eq.user_answer_label is not None:
                if eq.is_correct:
                    total_correct += 1
                else:
                    total_wrong += 1

            question_details.append({
                "exam_question_id": eq.id,
                "question_text": gen_q.question_text,
                "difficulty": gen_q.difficulty,
                "batch_number": eq.batch_number,
                "options": [
                    {"label": a.option_label, "text": a.option_text}
                    for a in answers
                ],
                "user_answer_label": eq.user_answer_label,
                "user_answer_text": user_answer_text,
                "is_correct": eq.is_correct,
                "correct_answer": {
                    "label": correct_ans.option_label if correct_ans else "?",
                    "text": correct_ans.option_text if correct_ans else "Tidak ditemukan",
                },
                "thinking_time_seconds": eq.thinking_time_seconds,
            })

        total_questions = len(question_details)
        accuracy = (total_correct / total_questions * 100) if total_questions > 0 else 0.0

        return {
            "session_id": exam_session.id,
            "topic": exam_session.topic,
            "status": exam_session.status,
            "total_score": exam_session.total_score,
            "start_time": exam_session.start_time,
            "end_time": exam_session.end_time,
            "user": {
                "full_name": exam_session.user.full_name,
                "email": exam_session.user.email,
            },
            "total_questions": total_questions,
            "total_correct": total_correct,
            "total_wrong": total_wrong,
            "accuracy_percent": round(accuracy, 1),
            "questions": question_details,
        }