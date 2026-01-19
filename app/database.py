from sqlmodel import SQLModel, create_engine, Session
from typing import Generator

DATABASE_URL = "postgresql://postgres:12345@localhost:5432/math_app_db"

engine = create_engine(DATABASE_URL, echo=True)


def create_db_and_tables(): 
    
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session