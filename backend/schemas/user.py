from pydantic import BaseModel, EmailStr, Field
from enum import Enum

class RoleEnum(str, Enum):
    SALES_DIRECTOR = "SALES_DIRECTOR"
    USER = "USER"

class UserCreate(BaseModel):
    name: str
    email: EmailStr
    role: RoleEnum
    password: str = Field(min_length=8, max_length=72)

class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)

class Token(BaseModel):
    access_token: str
    token_type: str
    expires_in_days: int


class UserOut(BaseModel):
    id: int
    name: str
    email: EmailStr
    role: RoleEnum

    model_config = {"from_attributes": True}