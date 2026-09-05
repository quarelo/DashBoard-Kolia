import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config import settings
from core.database import get_db
from models.user import UserModel

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> UserModel:
    unauthorized = HTTPException(401, "Autenticação necessária.", headers={"WWW-Authenticate": "Bearer"})
    if credentials is None:
        raise unauthorized
    try:
        payload = jwt.decode(credentials.credentials, settings.secret_key,
                             algorithms=[settings.algorithm], options={"require": ["exp", "sub"]})
    except jwt.InvalidTokenError:
        raise unauthorized
    user = db.scalar(select(UserModel).where(UserModel.email == payload["sub"]))
    if user is None:
        raise unauthorized
    return user
