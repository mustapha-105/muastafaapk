from pydantic import BaseModel, Field

class RegisterIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    phone: str = Field(min_length=3, max_length=40)
    password: str = Field(min_length=4, max_length=128)
    city: str | None = None

class LoginIn(BaseModel):
    phone: str
    password: str

class UserOut(BaseModel):
    id: int
    full_name: str
    phone: str
    role: str
    city: str | None = None
    class Config:
        from_attributes = True

class TokenOut(BaseModel):
    access_token: str
    token_type: str = 'bearer'
    user: UserOut
