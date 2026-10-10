"""Contratos da API (entrada e saída)."""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class EmployeeIn(BaseModel):
    matricula: str = Field(min_length=1, max_length=32, examples=["12107"])
    nome: str = Field(min_length=1, max_length=120, examples=["Ana Souza"])


class EmployeeOut(EmployeeIn):
    model_config = ConfigDict(from_attributes=True)


class EntryIn(BaseModel):
    matricula: str = Field(examples=["12107"])
    pcba: str = Field(max_length=80, examples=["00252700691435F300166713"])
    linha_producao: str = Field(max_length=60, examples=["Linha 3"])
    lado: str = Field(max_length=40, examples=["Lado A"])
    posicao: str = Field(max_length=40, examples=["Linha L1"])
    localizacao: str = Field(max_length=40, examples=["G3"])
    tipo: Literal["Running", "Aging"] = "Running"
    aging_horas: int | None = Field(default=None, examples=[24])


class ExitIn(BaseModel):
    motivo: str | None = Field(default=None, max_length=120, examples=["Troca de turno"])


class ExitByPcbaIn(ExitIn):
    pcba: str = Field(max_length=80)


class RecordOut(BaseModel):
    id: str
    matricula: str
    nome: str
    pcba: str
    linha_producao: str
    lado: str
    posicao: str
    localizacao: str
    tipo: str
    planejado_min: int | None
    entrada_em: datetime
    saida_em: datetime | None
    motivo: str
    pausa_programada: bool
    ajuste: str = ""
    # calculados no momento da consulta
    alertas_enviados: int = 0
    ciente_em: datetime | None = None
    ciente_nome: str = ""
    tempo_min: float = Field(description="Tempo efetivo (Running) ou real (Aging), em minutos")
    limite_min: float
    warn_min: float = Field(description="A partir de quantos minutos o status fica amarelo")
    status: Literal["ok", "warn", "crit", "paused"]
    em_atraso: bool


class SettingsOut(BaseModel):
    threshold_min: int
    aging_options_h: list[int]
    group_capacity: list[int]
    rows_per_side: int
    lines: list[str]
    reasons: list[str]
    baseline_min: float | None = None
    baseline_fonte: str = ""


class ErrorOut(BaseModel):
    code: str
    message: str
    errors: list[str] = []


class AckIn(BaseModel):
    matricula: str = Field(examples=["12107"], description="Leitura do crachá de quem assumiu o alerta")


class AckOut(BaseModel):
    ja_registrado: bool
    ciente_nome: str
    ciente_em: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 (tipo do token, não é senha)
    expires_in: int


class AdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    email: str
    nome: str
    cargo: str


class ThresholdIn(BaseModel):
    threshold_min: int = Field(gt=0, le=24 * 60)


class ReasonsIn(BaseModel):
    reasons: list[Annotated[str, StringConstraints(max_length=120)]] = Field(min_length=1)


class ResponsibleRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    linha: str = Field(max_length=60, examples=["Linha 1"])
    funcao: Literal["Monitor", "Lider", "Auditor", "Supervisor"]
    turno1: str = Field(default="", examples=["monitor.linha1@example.com"])
    turno2: str = ""


class CheckSummaryOut(BaseModel):
    ativos: int
    em_atraso: int
    pausados: int
    enviados: int
    por_nivel: dict[int, int]
    sem_destinatario: list[str]
    erros: list[str]


# ---------------------------------------------------------------- etapa 4: KPI, qualidade, plano de ação

class BaselineIn(BaseModel):
    minutos: float = Field(gt=0, le=1440, examples=[95], description="Tempo médio ANTES do kaizen")
    fonte: str = Field(min_length=3, max_length=300, examples=["Cronoanálise jun/2026, 40 amostras, linhas 1 a 3"])


class ActionIn(BaseModel):
    linha: str = Field(default="", max_length=60, examples=["Linha 2"], description='Vazio = todas as linhas')
    origem: str = Field(default="", max_length=200, examples=["KPI · Principal motivo de atraso"])
    problema: str = Field(max_length=2000)
    acao: str = Field(max_length=2000)
    responsavel: str = Field(max_length=120)
    prazo: date
    etapa: Literal["Planejar", "Executar", "Verificar", "Agir", "Concluída"] = "Planejar"
    resultado: str = Field(default="", max_length=2000)


class ActionOut(ActionIn):
    model_config = ConfigDict(from_attributes=True)
    id: str
    criado_em: datetime
    criado_por: str
    atualizado_em: datetime
    atualizado_por: str
    concluido_em: datetime | None
    atrasada: bool = False
