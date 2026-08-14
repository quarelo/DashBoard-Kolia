from fastapi import FastAPI, HTTPException, status, Depends
from sqlalchemy.orm import Session
from core.security import get_password_hash, verify_password, create_access_token
from core.database import engine, Base, get_db
from models.user import UserModel
from schemas.user import UserCreate, UserLogin, Token

app = FastAPI()

Base.metadata.create_all(bind=engine)

@app.post("/register", status_code=status.HTTP_201_CREATED)
def register_user(user: UserCreate, db: Session = Depends(get_db)):
    existing_user = db.query(UserModel).filter(UserModel.email == user.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email já cadastrado.")

    hashed_password = get_password_hash(user.password)
    
    new_user = UserModel(
        name=user.name,
        email=user.email,
        role=user.role,
        password=hashed_password
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return {"message": f"Usuário {new_user.name} criado com sucesso!"}

@app.post("/login", response_model=Token)
def login(user: UserLogin, db: Session = Depends(get_db)):
    db_user = db.query(UserModel).filter(UserModel.email == user.email).first()
    if not db_user or not verify_password(user.password, db_user.password):
        raise HTTPException(status_code=401, detail="Email ou senha incorretos")
    
    access_token = create_access_token(
        data={"sub": db_user.email, "role": db_user.role}
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in_days": 7
    }