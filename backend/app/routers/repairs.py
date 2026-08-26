"""报修记录。

「状态=维修」只说明设备现在不能用,说不出为什么修、送去哪了、什么时候回来。
实际场景里一台相机送修三周,期间谁都不知道它在哪 —— 这个路由补的就是这段。
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..db import get_db
from ..deps import active_user, admin_user
from ..models import Asset, Company, RepairRecord, Role, User
from ..schemas import RepairCloseIn, RepairOpenIn, RepairOut, RepairUpdateIn
from ..services import close_repair, log, open_repair, repair_out

router = APIRouter(prefix="/api", tags=["报修"])


def _loaded():
    return select(RepairRecord).options(
        joinedload(RepairRecord.asset),
        joinedload(RepairRecord.reported_by),
        joinedload(RepairRecord.resolved_by),
        joinedload(RepairRecord.vendor),
    )


def _get_repair(db: Session, repair_id: int) -> RepairRecord:
    record = db.execute(_loaded().where(RepairRecord.id == repair_id)).scalars().first()
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="报修记录不存在")
    return record


def _get_asset(db: Session, asset_id: int) -> Asset:
    asset = db.execute(
        select(Asset).where(Asset.id == asset_id, Asset.deleted_at.is_(None))
    ).scalars().first()
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="设备不存在")
    return asset


def _yuan_to_cents(yuan: Optional[float]) -> Optional[int]:
    return None if yuan is None else int(round(yuan * 100))


def _check_vendor(db: Session, vendor_id: Optional[int]) -> None:
    if vendor_id is not None and db.get(Company, vendor_id) is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="维修厂商不存在")


@router.post("/assets/{asset_id}/repairs", response_model=RepairOut)
def report_repair(
    asset_id: int,
    payload: RepairOpenIn,
    db: Session = Depends(get_db),
    user: User = Depends(active_user),
):
    """报修。任何登录用户都能报 —— 发现设备坏的往往是借用人,不是管理员。"""
    asset = _get_asset(db, asset_id)
    _check_vendor(db, payload.vendor_id)
    record = open_repair(db, asset, user, payload.symptom, payload.vendor_id, payload.note)
    db.commit()
    return repair_out(_get_repair(db, record.id))


@router.get("/assets/{asset_id}/repairs", response_model=List[RepairOut])
def asset_repairs(
    asset_id: int, db: Session = Depends(get_db), _: User = Depends(active_user)
):
    asset = _get_asset(db, asset_id)
    rows = (
        db.execute(
            _loaded()
            .where(RepairRecord.asset_id == asset.id)
            .order_by(RepairRecord.reported_at.desc())
        )
        .unique()
        .scalars()
        .all()
    )
    return [repair_out(r) for r in rows]


@router.get("/repairs", response_model=List[RepairOut])
def list_repairs(
    open_only: bool = Query(True, description="只看未完结的"),
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
    _: User = Depends(active_user),
):
    stmt = _loaded()
    if open_only:
        stmt = stmt.where(RepairRecord.resolved_at.is_(None))
    rows = (
        db.execute(stmt.order_by(RepairRecord.reported_at.desc()).limit(limit))
        .unique()
        .scalars()
        .all()
    )
    return [repair_out(r) for r in rows]


@router.put("/repairs/{repair_id}", response_model=RepairOut)
def update_repair(
    repair_id: int,
    payload: RepairUpdateIn,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_user),
):
    """补充进度:送去哪了、花多少钱、走不走保修。"""
    record = _get_repair(db, repair_id)
    if record.resolved_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="该报修已结案,不能再改"
        )
    data = payload.model_dump(exclude_unset=True)
    if "vendor_id" in data:
        _check_vendor(db, data["vendor_id"])
        record.vendor_id = data["vendor_id"]
    if "cost_yuan" in data:
        record.cost_cents = _yuan_to_cents(data["cost_yuan"])
    for field in ("symptom", "under_warranty", "note"):
        if field in data and data[field] is not None:
            setattr(record, field, data[field])

    log(db, admin.id, "repair_update", "asset", record.asset_id, record.asset.asset_tag)
    db.commit()
    # Session 是 expire_on_commit=False,提交后对象上已加载的关系不会失效。
    # 改了 vendor_id 之后不显式过期的话,下面的 joinedload 会命中 identity map
    # 里的旧对象,vendor 还是改动前的值(常见表现:刚填的厂商查出来是 null)。
    db.expire(record)
    return repair_out(_get_repair(db, repair_id))


@router.post("/repairs/{repair_id}/close", response_model=RepairOut)
def close(
    repair_id: int,
    payload: RepairCloseIn,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_user),
):
    """结案。修好回在库,判定报废转报废,误报也回在库。"""
    record = _get_repair(db, repair_id)
    if record.resolved_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该报修已结案")
    close_repair(
        db,
        record,
        admin,
        payload.result,
        _yuan_to_cents(payload.cost_yuan),
        payload.under_warranty,
        payload.note,
    )
    db.commit()
    return repair_out(_get_repair(db, repair_id))
