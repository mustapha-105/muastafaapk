from sqlalchemy.orm import Session
from app.models.notification import Notification

def notify(db: Session, user_id: int, title: str, message: str) -> Notification:
    n = Notification(user_id=user_id, title=title, message=message)
    db.add(n)
    return n
