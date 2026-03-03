from sqlmodel import Session, select
from sqlalchemy.orm import selectinload

from app.models import ExamSession


class NilaiServices:
    def __init__(self, session : Session):
        self.session = session
    
    def getNilai(self):
        nilai = select(ExamSession).options(selectinload(ExamSession.user))
        tampil_nilai = self.session.exec(nilai).all()
        return tampil_nilai

    def getNilaiByUserId(self, user_id: int):
        query = select(ExamSession).where(
            ExamSession.user_id == user_id
        ).options(selectinload(ExamSession.user))
        hasil = self.session.exec(query).all()
        return hasil