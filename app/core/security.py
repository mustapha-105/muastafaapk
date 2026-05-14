from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import os
import base64
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import get_db

_PASSWORD_ALGORITHM = "pbkdf2_sha256"
_PASSWORD_ITERATIONS = 260_000
_SALT_BYTES = 16
_HASH_BYTES = 32

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f'{settings.api_prefix}/auth/login')


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode('ascii').rstrip('=')


def _b64decode(value: str) -> bytes:
    padding = '=' * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode('ascii'))


def hash_password(password: str) -> str:
    if password is None:
        password = ''
    password_bytes = str(password).encode('utf-8')
    salt = os.urandom(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac('sha256', password_bytes, salt, _PASSWORD_ITERATIONS, dklen=_HASH_BYTES)
    return f"{_PASSWORD_ALGORITHM}${_PASSWORD_ITERATIONS}${_b64encode(salt)}${_b64encode(digest)}"


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False

    # New safe hash format.
    if password_hash.startswith(f"{_PASSWORD_ALGORITHM}$"):
        try:
            _algorithm, iterations, salt_b64, digest_b64 = password_hash.split('$', 3)
            salt = _b64decode(salt_b64)
            expected = _b64decode(digest_b64)
            actual = hashlib.pbkdf2_hmac(
                'sha256',
                str(password or '').encode('utf-8'),
                salt,
                int(iterations),
                dklen=len(expected),
            )
            return hmac.compare_digest(actual, expected)
        except Exception:
            return False

    if password_hash.startswith('$2'):
        try:
            from passlib.context import CryptContext
            legacy_context = CryptContext(schemes=['bcrypt'], deprecated='auto')
            return legacy_context.verify(password, password_hash)
        except Exception:
            return False

    return False


def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode({'sub': subject, 'exp': expire}, settings.secret_key, algorithm='HS256')


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    from app.models.user import User
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=['HS256'])
        user_id = payload.get('sub')
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token')
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token')
    user = db.get(User, int(user_id))
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Inactive or missing user')
    return user


def require_admin(current_user=Depends(get_current_user)):
    if current_user.role not in {'admin', 'dispatcher', 'super_admin'}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Admin access required')
    return current_user
