from typing import Annotated
from fastapi import Depends
from sqlmodel import Session
from app.database import get_session
from app.services.nilai_services import NilaiServices

SessionsDep = Annotated[Session, Depends(get_session)]

def get_nilai_services(session: SessionsDep):
    return NilaiServices(session)


NilaiServicesDepedencies = Annotated[NilaiServices, Depends(get_nilai_services)]