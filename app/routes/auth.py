from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import Session, select
from google.oauth2 import id_token
from google.auth.transport import requests
import os
import jwt
from datetime import datetime, timedelta

from app.database import get_session
from app.models import User
from app.schemas.auth_google import DevLoginRequest, GoogleLoginRequest, LoginResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Config
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
SECRET_KEY = os.getenv("SECRET_KEY", "rahasia_default")
ALGORITHM = "HS256"


# --- HELPER: Bikin Token JWT ---
def create_access_token(user_id: int, email: str):
    expire = datetime.utcnow() + timedelta(days=7) # Token berlaku 7 hari
    to_encode = {"sub": str(user_id), "email": email, "exp": expire}
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


@router.post("/google-login", response_model=LoginResponse)
def login_google(request: GoogleLoginRequest, session: Session = Depends(get_session)):
    try:
        # Verifikasi Token ke Google
        id_info = id_token.verify_oauth2_token(
            request.token, 
            requests.Request(), 
            GOOGLE_CLIENT_ID
        )

        email = id_info.get("email")
        name = id_info.get("name")
        google_id = id_info.get("sub")
        picture = id_info.get("picture")

        # Logic Simpan/Update User
        return process_login(session, email, name, google_id, picture)

    except ValueError:
        raise HTTPException(status_code=401, detail="Token Google Invalid")

# ==========================================
# 2. LOGIN DEVELOPER (Buat Test Postman)
# ==========================================
@router.post("/dev-login", response_model=LoginResponse)
def login_dev(request: DevLoginRequest, session: Session = Depends(get_session)):
    """
    Login jalur tikus untuk testing Backend.
    Cukup kirim email, otomatis dianggap user valid.
    HANYA UNTUK DEVELOPMENT!
    """
    # Kita pakai email sebagai dummy ID Google juga
    return process_login(session, request.email, "Developer User", f"dev_{request.email}", None)

# --- CORE LOGIC (Dipakai kedua login di atas) ---
def process_login(session: Session, email: str, name: str, google_id: str, picture: str):
    statement = select(User).where(User.email == email)
    user = session.exec(statement).first()
    
    is_new = False
    
    if not user:
        # Register Baru
        user = User(
            email=email,
            full_name=name,
            google_id=google_id,
            avatar_url=picture
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        is_new = True
    else:
        # Update Data (User Lama)
        user.full_name = name
        if picture:
            user.avatar_url = picture
        session.add(user)
        session.commit()
        session.refresh(user)

    # Bikin Tiket Masuk (JWT)
    token = create_access_token(user.id, user.email)

    return LoginResponse(
        access_token=token,
        token_type="bearer",
        user_id=user.id,
        full_name=user.full_name,
        is_new_user=is_new
    )

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/dev-login")

def get_current_user(token: str = Depends(oauth2_scheme), session: Session = Depends(get_session)) -> User:
    """
    Fungsi ini akan:
    1. Mencegat request
    2. Ambil token dari Header 'Authorization: Bearer ...'
    3. Validasi Token (Asli/Palsu/Expired)
    4. Kalau oke, balikin Object User yg login.
    """
    credentials_exception = HTTPException(
        status_code=401,
        detail="Token tidak valid atau sudah kadaluwarsa",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        # Dekode Token
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
        
    except jwt.PyJWTError:
        raise credentials_exception
        
    # Cek User di Database
    user = session.get(User, int(user_id))
    if user is None:
        raise credentials_exception
        
    return user

@router.get("/me", response_model=LoginResponse)
def read_users_me(current_user: User = Depends(get_current_user)):
    """
    Cek profil sendiri. 
    Hanya bisa diakses kalau bawa Token Valid di Header.
    """
    return LoginResponse(
        access_token="", # Gak perlu balikin token lagi
        token_type="bearer",
        user_id=current_user.id,
        full_name=current_user.full_name,
        is_new_user=False
    )