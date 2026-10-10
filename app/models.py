"""Modelo de dados."""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, UTCDateTime

TIPO_RUNNING = "Running"
TIPO_AGING = "Aging"


class Employee(Base):
    __tablename__ = "employees"

    matricula: Mapped[str] = mapped_column(String(32), primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))


class ProductionLine(Base):
    __tablename__ = "production_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(60), unique=True)  # normalizado: "LINHA 1"


class DelayReason(Base):
    __tablename__ = "delay_reasons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    texto: Mapped[str] = mapped_column(String(120), unique=True)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class Record(Base):
    """Uma peça na estação: da entrada à saída."""

    __tablename__ = "records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    # Sem chave estrangeira de propósito: o registro guarda um retrato de quem fez a entrada,
    # e o histórico precisa sobreviver à saída do colaborador do cadastro.
    matricula: Mapped[str] = mapped_column(String(32), index=True)
    nome: Mapped[str] = mapped_column(String(120))
    pcba: Mapped[str] = mapped_column(String(80), index=True)
    linha_producao: Mapped[str] = mapped_column(String(60))
    lado: Mapped[str] = mapped_column(String(10))
    posicao: Mapped[str] = mapped_column(String(20))
    localizacao: Mapped[str] = mapped_column(String(20))
    tipo: Mapped[str] = mapped_column(String(10), default=TIPO_RUNNING)
    planejado_min: Mapped[int | None] = mapped_column(Integer, nullable=True)  # só Aging
    entrada_em: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    saida_em: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True, index=True)
    motivo: Mapped[str] = mapped_column(String(120), default="")
    duracao_efetiva_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    pausa_programada: Mapped[bool] = mapped_column(Boolean, default=False)
    # Escalonamento: quando cada nível foi enviado; ciente = quem assumiu o tratamento
    alerta1_em: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    alerta2_em: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    alerta3_em: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    ciente_em: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    ciente_matricula: Mapped[str] = mapped_column(String(32), default="")
    ciente_nome: Mapped[str] = mapped_column(String(120), default="")
    # Qualidade dos dados: preenchido quando o registro é encerrado por ajuste (ex.: saída esquecida).
    # Registros com ajuste ficam fora das médias dos KPIs, mas continuam rastreáveis.
    ajuste: Mapped[str] = mapped_column(String(200), default="")

    def alert_sent_at(self, level: int) -> datetime | None:
        return getattr(self, f"alerta{level}_em")

    def mark_alert(self, level: int, when: datetime) -> None:
        setattr(self, f"alerta{level}_em", when)


class Admin(Base):
    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(160), unique=True)  # sempre minúsculo
    nome: Mapped[str] = mapped_column(String(120))
    cargo: Mapped[str] = mapped_column(String(120), default="")
    senha_hash: Mapped[str] = mapped_column(String(100))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class Responsible(Base):
    """Matriz de escalonamento: quem recebe cada nível, por linha e turno."""

    __tablename__ = "responsibles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    linha: Mapped[str] = mapped_column(String(60))  # "LINHA 1" ou "TODAS"
    funcao: Mapped[str] = mapped_column(String(20))  # Monitor | Lider | Auditor | Supervisor
    turno1: Mapped[str] = mapped_column(Text, default="")  # e-mails separados por vírgula
    turno2: Mapped[str] = mapped_column(Text, default="")


class AlertLog(Base):
    """Trilha de auditoria de cada e-mail de alerta enviado."""

    __tablename__ = "alert_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    record_id: Mapped[str] = mapped_column(ForeignKey("records.id", ondelete="CASCADE"), index=True)
    nivel: Mapped[int] = mapped_column(Integer)
    enviado_em: Mapped[datetime] = mapped_column(UTCDateTime)
    destinatarios: Mapped[str] = mapped_column(Text)


ETAPAS_PDCA = ("Planejar", "Executar", "Verificar", "Agir", "Concluída")


class Action(Base):
    """Plano de ação (PDCA): o que foi decidido a partir dos indicadores."""

    __tablename__ = "actions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    linha: Mapped[str] = mapped_column(String(60), default="")      # "" = todas
    origem: Mapped[str] = mapped_column(String(200), default="")    # ex.: insight do KPI que gerou a ação
    problema: Mapped[str] = mapped_column(Text)
    acao: Mapped[str] = mapped_column(Text)
    responsavel: Mapped[str] = mapped_column(String(120))
    prazo: Mapped[date] = mapped_column(Date)
    etapa: Mapped[str] = mapped_column(String(20), default="Planejar")
    resultado: Mapped[str] = mapped_column(Text, default="")
    criado_em: Mapped[datetime] = mapped_column(UTCDateTime)
    criado_por: Mapped[str] = mapped_column(String(120))
    atualizado_em: Mapped[datetime] = mapped_column(UTCDateTime)
    atualizado_por: Mapped[str] = mapped_column(String(120))
    concluido_em: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
