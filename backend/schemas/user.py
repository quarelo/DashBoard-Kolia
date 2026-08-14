from pydantic import BaseModel, EmailStr
from enum import Enum

class RoleEnum(str, Enum):
    SALES_DIRECTOR = "SALES_DIRECTOR"
    USER = "USER"

class UserCreate(BaseModel):
    name: str
    email: EmailStr
    role: RoleEnum
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str
    expires_in_days: int