from sqlalchemy import Column, Integer, String, Enum as SQLEnum
from core.database import Base
from schemas.user import RoleEnum

class UserModel(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "core"}

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    role = Column(SQLEnum(RoleEnum), nullable=False, default=RoleEnum.USER)
    
    password = Column(String, nullable=False)