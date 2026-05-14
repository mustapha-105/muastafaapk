from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import hash_password, verify_password, create_access_token, get_current_user
from app.models.user import User
from app.schemas.auth import RegisterIn, LoginIn, TokenOut, UserOut

router = APIRouter(prefix='/auth', tags=['auth'])

@router.post('/register', response_model=TokenOut)
def register(payload: RegisterIn, db: Session = Depends(get_db)):
    exists = db.query(User).filter(User.phone == payload.phone.strip()).first()
    if exists:
        raise HTTPException(status_code=409, detail='Phone already registered')
    user = User(
        full_name=payload.full_name.strip(),
        phone=payload.phone.strip(),
        password_hash=hash_password(payload.password),
        role='citizen',
        city=(payload.city or '').strip() or None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {'access_token': create_access_token(str(user.id)), 'user': user}

@router.post('/login', response_model=TokenOut)
def login(payload: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.phone == payload.phone.strip()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Wrong phone or password')
    return {'access_token': create_access_token(str(user.id)), 'user': user}

@router.get('/me', response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user
