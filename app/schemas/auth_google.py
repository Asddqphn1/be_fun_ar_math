from pydantic import BaseModel


class GoogleLoginRequest(BaseModel):
    token: str # Token dari Google (Dikirim Frontend)

class DevLoginRequest(BaseModel):
    email: str # Buat nembak langsung dari Postman

class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    user_id: int
    full_name: str
    is_new_user: bool