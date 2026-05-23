from sqlmodel import Session, select
from sqlalchemy.orm import selectinload

from app.models import ExamSession, ExamStatusEnum, User


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