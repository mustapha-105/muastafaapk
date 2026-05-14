from datetime import datetime
from pydantic import BaseModel, Field

class RequestCreate(BaseModel):
    type: str = 'complaint'
    title: str = Field(min_length=3, max_length=200)
    category: str | None = None
    description: str = Field(min_length=3)
    latitude: float | None = None
    longitude: float | None = None
    city: str | None = None
    priority: str = 'normal'

class RequestUpdate(BaseModel):
    status: str | None = None
    priority: str | None = None
    admin_reply: str | None = None
    assigned_admin_id: int | None = None
    note: str | None = None

class RequestOut(BaseModel):
    id: int
    user_id: int
    assigned_admin_id: int | None = None
    type: str
    title: str
    category: str | None = None
    description: str
    latitude: float | None = None
    longitude: float | None = None
    city: str | None = None
    priority: str
    status: str
    admin_reply: str | None = None
    citizen_name: str | None = None
    citizen_phone: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    class Config:
        from_attributes = True

class HistoryOut(BaseModel):
    id: int
    action: str
    old_status: str | None = None
    new_status: str | None = None
    note: str | None = None
    created_at: datetime | None = None
    class Config:
        from_attributes = True
