"""Plano de ação (PDCA): leitura aberta, escrita só para administrador (fica registrado quem fez)."""

from datetime import datetime

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import current_admin
from app.clock import get_now
from app.db import get_db
from app.models import Action, Admin
from app.schemas import ActionIn, ActionOut
from app.services import actions as svc

router = APIRouter(prefix="/actions", tags=["Plano de ação"])


def to_out(a: Action, now: datetime) -> ActionOut:
    return ActionOut.model_validate(a).model_copy(update={"atrasada": svc.is_late(a, now)})


@router.get("", response_model=list[ActionOut])
def list_actions(db: Session = Depends(get_db), now: datetime = Depends(get_now)):
    return [to_out(a, now) for a in svc.list_actions(db)]


@router.post("", response_model=ActionOut, status_code=status.HTTP_201_CREATED)
def create(body: ActionIn, db: Session = Depends(get_db), now: datetime = Depends(get_now),
           admin: Admin = Depends(current_admin)):
    return to_out(svc.save(db, now, admin, body.model_dump()), now)


@router.put("/{action_id}", response_model=ActionOut)
def update(action_id: str, body: ActionIn, db: Session = Depends(get_db), now: datetime = Depends(get_now),
           admin: Admin = Depends(current_admin)):
    return to_out(svc.save(db, now, admin, body.model_dump(), action_id), now)


@router.delete("/{action_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(current_admin)])
def delete(action_id: str, db: Session = Depends(get_db)):
    svc.delete(db, action_id)
