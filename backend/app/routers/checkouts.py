"""借还记录查询:逾期列表、我名下的设备。对应 PRD 3.5 / 第 6 节。"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..db import get_db
from ..deps import active_user
from ..models import Asset, CheckoutRecord, Role, User, utcnow
from ..schemas import AssetOut, CheckoutRecordOut
from ..services import assets_out, record_out

router = APIRouter(prefix="/api", tags=["借还"])


@router.get("/checkouts", response_model=List[CheckoutRecordOut])
def list_checkouts(
    overdue: bool = Query(False, description="只看逾期未还"),
    open_only: bool = Query(True, description="只看未归还"),
    user_id: Optional[int] = Query(None, description="按领用人过滤"),
    db: Session = Depends(get_db),
    user: User = Depends(active_user),
):
    stmt = select(CheckoutRecord).options(
        joinedload(CheckoutRecord.asset),
        joinedload(CheckoutRecord.user),
        joinedload(CheckoutRecord.operator),
        joinedload(CheckoutRecord.checkin_operator),
    )
    if open_only or overdue:
        stmt = stmt.where(CheckoutRecord.checked_in_at.is_(None))
    if overdue:
        stmt = stmt.where(
            CheckoutRecord.due_at.is_not(None), CheckoutRecord.due_at < utcnow()
        )
    # 普通用户只能看自己的记录
    if user.role != Role.ADMIN:
        stmt = stmt.where(CheckoutRecord.user_id == user.id)
    elif user_id is not None:
        stmt = stmt.where(CheckoutRecord.user_id == user_id)

    rows = (
        db.execute(stmt.order_by(CheckoutRecord.checked_out_at.desc()).limit(500))
        .unique()
        .scalars()
        .all()
    )
    return [record_out(r) for r in rows]


@router.get("/me/assets", response_model=List[AssetOut])
def my_assets(db: Session = Depends(get_db), user: User = Depends(active_user)):
    """我名下的设备 = 我借出未还的 + 我是长期责任人的(PRD 3.1 两种流转模式)。"""
    borrowed_ids = (
        db.execute(
            select(CheckoutRecord.asset_id)
            .where(CheckoutRecord.user_id == user.id)
            .where(CheckoutRecord.checked_in_at.is_(None))
        )
        .scalars()
        .all()
    )
    stmt = (
        select(Asset)
        .where(Asset.deleted_at.is_(None))
        .where((Asset.owner_user_id == user.id) | (Asset.id.in_(borrowed_ids)))
        .options(joinedload(Asset.category), joinedload(Asset.owner))
        .order_by(Asset.asset_tag)
    )
    rows = db.execute(stmt).unique().scalars().all()
    return assets_out(db, rows)
