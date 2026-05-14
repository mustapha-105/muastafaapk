from datetime import datetime
from pydantic import BaseModel

class NotificationOut(BaseModel):
    id: int
    title: str
    message: str
    is_read: bool
    created_at: datetime | None = None
    class Config:
        from_attributes = True
