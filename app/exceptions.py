"""Erros de domínio com código estável — o front-end decide pela chave, não pelo texto."""


class DomainError(Exception):
    status_code = 400

    def __init__(self, code: str, message: str, errors: list[str] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.errors = errors or []


class NotFound(DomainError):
    status_code = 404


class Conflict(DomainError):
    status_code = 409


class Unprocessable(DomainError):
    status_code = 422
