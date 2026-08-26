"""盘库记录汇总与差异处理。

滚动盘点(PRD 阶段二):不建盘点任务实体,靠「最后盘库时间」+ 超期筛选驱动。
本路由提供两件事:全量盘库流水,以及需要管理员拍板的差异清单。
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from ..db import get_db
from ..deps import active_user, admin_user
from ..models import Asset, InventoryCheck, Role, User
from ..schemas import InventoryCheckOut, ResolveCheckIn
from ..services import check_out, resolve_inventory_check

router = APIRouter(prefix="/api/inventory", tags=["盘库"])


def _discrepancy_clause():
    """有差异 = 观察值与当时台账快照对不上。派生,不存字段。"""
    return or_(
        InventoryCheck.observed_location != InventoryCheck.location_at_check,
        InventoryCheck.observed_status != InventoryCheck.status_at_check,
    )


@router.get("/checks", response_model=List[InventoryCheckOut])
def list_checks(
    pending: bool = Query(False, description="只看待处理的差异"),
    asset_id: Optional[int] = None,
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
    user: User = Depends(active_user),
):
    stmt = select(InventoryCheck).options(
        joinedload(InventoryCheck.asset),
        joinedload(InventoryCheck.checked_by),
        joinedload(InventoryCheck.borrower),
        joinedload(InventoryCheck.resolved_by),
    )
    if pending:
        stmt = stmt.where(_discrepancy_clause(), InventoryCheck.resolved_at.is_(None))
    if asset_id is not None:
        stmt = stmt.where(InventoryCheck.asset_id == asset_id)
    # 普通用户只看自己盘的,避免把全公司台账流水摊开
    if user.role != Role.ADMIN:
        stmt = stmt.where(InventoryCheck.checked_by_id == user.id)

    rows = (
        db.execute(stmt.order_by(InventoryCheck.checked_at.desc()).limit(limit))
        .unique()
        .scalars()
        .all()
    )
    return [check_out(r) for r in rows]


@router.get("/summary")
def summary(
    unchecked_days: int = Query(90, ge=1, description="多久没盘算超期"),
    db: Session = Depends(get_db),
    _: User = Depends(active_user),
):
    """盘库概览:总台数、超期未盘、待处理差异。"""
    from datetime import timedelta

    from sqlalchemy import func

    from ..models import utcnow

    cutoff = utcnow() - timedelta(days=unchecked_days)
    recent = select(InventoryCheck.asset_id).where(InventoryCheck.checked_at >= cutoff)

    total = db.execute(
        select(func.count()).select_from(Asset).where(Asset.deleted_at.is_(None))
    ).scalar_one()
    overdue = db.execute(
        select(func.count())
        .select_from(Asset)
        .where(Asset.deleted_at.is_(None), Asset.id.not_in(recent))
    ).scalar_one()
    pending = db.execute(
        select(func.count())
        .select_from(InventoryCheck)
        .where(_discrepancy_clause(), InventoryCheck.resolved_at.is_(None))
    ).scalar_one()

    return {
        "total": total,
        "unchecked_days": unchecked_days,
        "overdue": overdue,
        "checked": total - overdue,
        "pending_discrepancies": pending,
    }


@router.post("/checks/{check_id}/resolve", response_model=InventoryCheckOut)
def resolve_check(
    check_id: int,
    payload: ResolveCheckIn,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_user),
):
    """处理一条挂起的差异。

    apply = 采纳盘库看到的值写回台账;dismiss = 维持台账,仅留档。
    """
    check = db.get(InventoryCheck, check_id)
    if check is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="盘库记录不存在")
    if not check.has_discrepancy:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该记录没有差异")
    if check.resolved_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该差异已处理过")

    resolve_inventory_check(db, check, admin, payload.action)
    db.commit()
    return check_out(check)
