"""Agendador: verifica atrasos a cada minuto e envia os alertas escalonados."""

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.clock import get_now
from app.config import settings
from app.db import SessionLocal
from app.services import config_store
from app.services.alerts import run_overdue_check
from app.services.mailer import default_sender

log = logging.getLogger("running_control.scheduler")


def check_job() -> None:
    with SessionLocal() as db:
        try:
            s = run_overdue_check(db, config_store.load(db), get_now(), default_sender())
            if s.enviados or s.erros or s.sem_destinatario:
                log.info("verificação: %s", s)
        except Exception:  # o agendador nunca pode morrer por um erro pontual
            log.exception("falha na verificação de atrasos")


def start() -> BackgroundScheduler:
    sched = BackgroundScheduler(timezone=str(settings.timezone))
    sched.add_job(check_job, "interval", seconds=settings.check_every_seconds, id="overdue-check",
                  max_instances=1, coalesce=True)
    sched.start()
    return sched
