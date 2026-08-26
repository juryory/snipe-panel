"""借还记录查询:逾期列表、我名下的设备。对应 PRD 3.5 / 第 6 节。"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..db import get_db
from ..deps import active_user
from ..models import Asset, CheckoutRecord, Role, User, to_naive_utc, utcnow
from ..schemas import AssetOut, CheckoutRecordOut, KitCheckoutIn
from ..services import assets_out, checkout_kit, record_out

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


@router.post("/checkouts/kit", response_model=List[CheckoutRecordOut])
def checkout_as_kit(
    payload: KitCheckoutIn,
    db: Session = Depends(get_db),
    user: User = Depends(active_user),
):
    """成套借出:相机 + 镜头 + 电池一起借。

    全有或全无 —— 中间某台不可借就整批取消。借走三件、第四件失败的话,
    人已经抱着东西走了,台账却只记了三条,对不上。
    """
    borrower = user
    if payload.user_id is not None and payload.user_id != user.id:
        if user.role != Role.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="只有管理员可代他人借出"
            )
        borrower = db.get(User, payload.user_id)
        if borrower is None or not borrower.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="领用人不存在")

    # 保持请求里的顺序,报错时人能对上是第几件出的问题
    found = {
        a.id: a
        for a in db.execute(
            select(Asset).where(Asset.id.in_(payload.asset_ids), Asset.deleted_at.is_(None))
        ).scalars().all()
    }
    missing = [i for i in payload.asset_ids if i not in found]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"有 {len(missing)} 台设备不存在"
        )
    assets = [found[i] for i in payload.asset_ids]

    records = checkout_kit(
        db, assets, borrower, user, due_at=to_naive_utc(payload.due_at), note=payload.note
    )
    db.commit()
    return [record_out(r) for r in records]


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
