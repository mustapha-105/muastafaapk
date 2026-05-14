from sqlalchemy import String, Text, Float, Integer, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

class Request(Base):
    __tablename__ = 'requests'
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True, nullable=False)
    assigned_admin_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True, index=True)
    type: Mapped[str] = mapped_column(String(30), default='complaint', index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    priority: Mapped[str] = mapped_column(String(30), default='normal', index=True)
    status: Mapped[str] = mapped_column(String(30), default='submitted', index=True)
    admin_reply: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    citizen = relationship('User', back_populates='requests', foreign_keys=[user_id])
    assigned_admin = relationship('User', foreign_keys=[assigned_admin_id])
    history = relationship('RequestHistory', back_populates='request', cascade='all, delete-orphan')
