from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api.deps import current_admin
from app.config import settings
from app.db import get_db
from app.models import Admin
from app.schemas import AdminOut, TokenOut
from app.services.auth import authenticate, create_token

router = APIRouter(prefix="/auth", tags=["Autenticação"])


@router.post("/login", response_model=TokenOut)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Login de administrador. `username` = e-mail."""
    admin = authenticate(db, form.username, form.password)
    return TokenOut(access_token=create_token(admin), expires_in=settings.jwt_expire_hours * 3600)


@router.get("/me", response_model=AdminOut)
def me(admin: Admin = Depends(current_admin)):
    return admin
