from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_admin
from app.db import get_db
from app.domain.position import normalize_matricula
from app.exceptions import Conflict, NotFound
from app.models import Employee
from app.schemas import EmployeeIn, EmployeeOut

router = APIRouter(prefix="/employees", tags=["Colaboradores"])


@router.get("", response_model=list[EmployeeOut])
def list_employees(db: Session = Depends(get_db)):
    return list(db.scalars(select(Employee).order_by(Employee.nome)))


@router.post("", response_model=EmployeeOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(current_admin)])
def create_employee(body: EmployeeIn, db: Session = Depends(get_db)):
    mat = normalize_matricula(body.matricula)
    if any(normalize_matricula(e.matricula) == mat for e in db.scalars(select(Employee))):
        raise Conflict("MATRICULA_DUPLICADA", "Já existe um colaborador com essa matrícula.")
    emp = Employee(matricula=mat, nome=body.nome.strip())
    db.add(emp)
    db.commit()
    return emp


@router.delete("/{matricula}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(current_admin)])
def delete_employee(matricula: str, db: Session = Depends(get_db)):
    emp = db.get(Employee, normalize_matricula(matricula))
    if emp is None:
        raise NotFound("MATRICULA_NAO_ENCONTRADA", "Colaborador não encontrado.")
    db.delete(emp)
    db.commit()
