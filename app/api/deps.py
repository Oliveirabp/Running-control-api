from datetime import datetime

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.clock import get_now
from app.db import get_db
from app.models import Admin
from app.services import config_store
from app.services.auth import admin_from_token
from app.services.config_store import AppConfig
from app.services.mailer import EmailSender, default_sender

oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_config(db: Session = Depends(get_db)) -> AppConfig:
    return config_store.load(db)


def get_sender() -> EmailSender:
    return default_sender()


def current_admin(token: str = Depends(oauth2), db: Session = Depends(get_db)) -> Admin:
    return admin_from_token(db, token)


__all__ = ["get_db", "get_now", "get_config", "get_sender", "current_admin", "AppConfig", "Session", "datetime", "Depends"]
