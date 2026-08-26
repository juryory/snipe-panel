"""采购公司(供应商)管理。"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import active_user, admin_user
from ..models import Asset, Company, User
from ..schemas import CompanyCreate, CompanyOut, CompanyUpdate
from ..services import log

router = APIRouter(prefix="/api/companies", tags=["采购公司"])


def _asset_counts(db: Session) -> dict:
    """各公司名下在册设备数(不含软删除),一次查完避免 N+1。"""
    rows = db.execute(
        select(Asset.company_id, func.count())
        .where(Asset.deleted_at.is_(None), Asset.company_id.is_not(None))
        .group_by(Asset.company_id)
    ).all()
    return {company_id: count for company_id, count in rows}


def _out(company: Company, counts: dict) -> CompanyOut:
    data = CompanyOut.model_validate(company)
    data.asset_count = counts.get(company.id, 0)
    return data


@router.get("", response_model=List[CompanyOut])
def list_companies(db: Session = Depends(get_db), _: User = Depends(active_user)):
    counts = _asset_counts(db)
    rows = db.execute(select(Company).order_by(Company.name)).scalars().all()
    return [_out(c, counts) for c in rows]


@router.post("", response_model=CompanyOut, status_code=status.HTTP_201_CREATED)
def create_company(
    payload: CompanyCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_user),
):
    company = Company(
        name=payload.name.strip(),
        contact=payload.contact,
        phone=payload.phone,
        note=payload.note,
    )
    db.add(company)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该公司已存在")
    log(db, admin.id, "company_create", "company", company.id, company.name)
    db.commit()
    return _out(company, {})


@router.put("/{company_id}", response_model=CompanyOut)
def update_company(
    company_id: int,
    payload: CompanyUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_user),
):
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="采购公司不存在")
    data = payload.model_dump(exclude_unset=True)
    if "name" in data:
        data["name"] = data["name"].strip()
    for key, value in data.items():
        setattr(company, key, value)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该公司名称已存在")
    log(db, admin.id, "company_update", "company", company.id, ",".join(data.keys()))
    db.commit()
    return _out(company, _asset_counts(db))


@router.delete("/{company_id}")
def delete_company(
    company_id: int, db: Session = Depends(get_db), admin: User = Depends(admin_user)
):
    """名下还有设备时不允许删除。

    与分类一致:设备上的采购公司是历史事实,不能因为删掉公司就凭空消失。
    真要删,先把这些设备的采购公司改掉或清空。
    """
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="采购公司不存在")

    # 软删除的设备行还在,外键也还指向这家公司,所以计数必须把它们算上 ——
    # 只数在册设备的话,这里会放行,然后在 DELETE 时撞上 FOREIGN KEY 约束。
    live, archived = db.execute(
        select(
            func.count().filter(Asset.deleted_at.is_(None)),
            func.count().filter(Asset.deleted_at.is_not(None)),
        ).where(Asset.company_id == company_id)
    ).one()
    if live or archived:
        detail = f"该公司名下还有 {live} 台设备,请先调整这些设备的采购公司"
        if archived and not live:
            detail = f"该公司名下有 {archived} 台已删除的设备仍保留着采购记录,不能删除公司"
        elif archived:
            detail += f"(另有 {archived} 台已删除的设备仍保留着采购记录)"
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    log(db, admin.id, "company_delete", "company", company.id, company.name)
    db.delete(company)
    db.commit()
    return {"ok": True}
