from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from jose import JWTError, jwt

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.user import User
from app.services.realtime import subscribe, event_stream

router = APIRouter(prefix='/events', tags=['events'])


def user_from_token(token: str) -> User:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=['HS256'])
        user_id = payload.get('sub')
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token')
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token')

    db = SessionLocal()
    try:
        user = db.get(User, int(user_id))
        if not user or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Inactive or missing user')
        # Detach the object from the session before closing it.
        db.expunge(user)
        return user
    finally:
        db.close()


@router.get('')
async def realtime_events(token: str = Query(...)):
    # EventSource cannot send Authorization headers reliably, so the token is passed as a query parameter.
    user_from_token(token)
    q = subscribe()
    return StreamingResponse(
        event_stream(q),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        },
    )
