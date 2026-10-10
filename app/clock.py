"""Relógio injetável: em produção é o horário atual; nos testes, um instante fixo."""

from datetime import UTC, datetime


def get_now() -> datetime:
    return datetime.now(UTC)
