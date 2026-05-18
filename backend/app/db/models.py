from sqlalchemy import Boolean, Column, DateTime, Integer, Text
from sqlalchemy.sql import func

from app.db.base import Base


class User(Base):
    """
    Учётная запись пользователя для JWT-аутентификации.
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(Text, unique=True, nullable=False)
    password_hash = Column(Text, nullable=False)
    role = Column(Text, nullable=False, default="user")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
