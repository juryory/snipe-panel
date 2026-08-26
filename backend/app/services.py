"""业务逻辑:资产编号生成、借出/归还、序列化。"""
from typing import Dict, Iterable, List, Optional, Sequence

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import settings
from .models import (
    STATUS_LABELS,
    ActivityLog,
    Asset,
    AssetStatus,
    Category,
    CheckoutRecord,
    User,
    utcnow,
)
from .schemas import AssetOut, CheckoutBrief, CheckoutRecordOut, CompanyBrief, UserBrief


# ---------- 操作日志 ----------
def log(db: Session, actor_id: Optional[int], action: str, target_type: str = "",
        target_id: Optional[int] = None, detail: str = "") -> None:
    db.add(ActivityLog(actor_id=actor_id, action=action, target_type=target_type,
                       target_id=target_id, detail=detail))


# ---------- 资产编号 ----------
def next_asset_tag(db: Session, category: Category) -> str:
    """取该分类的下一个编号。

    PRD 3.2:流水号自增依赖数据库唯一约束 + 冲突重试,不在应用层做「读-加-写」。
    这里用一条 UPDATE seq = seq + 1 原子推进,再读回结果。
    """
    db.execute(
        update(Category).where(Category.id == category.id).values(seq=Category.seq + 1)
    )
    db.flush()
    seq = db.execute(select(Category.seq).where(Category.id == category.id)).scalar_one()
    return f"{category.tag_prefix}-{seq:0{settings.tag_seq_width}d}"


def create_asset_with_tag(db: Session, category: Category, explicit_tag: Optional[str],
                          **fields) -> Asset:
    """创建设备。explicit_tag 为空则自动生成编号,冲突则推进流水号重试。

    插入包在 SAVEPOINT 里:失败时只回滚这次插入,next_asset_tag 已推进的 seq 得以保留,
    否则重试会拿到同一个编号、撞同一个约束,直到耗尽次数。
    """
    attempts = 10 if not explicit_tag else 1
    for _ in range(attempts):
        tag = explicit_tag or next_asset_tag(db, category)
        savepoint = db.begin_nested()
        asset = Asset(asset_tag=tag, category_id=category.id, **fields)
        db.add(asset)
        try:
            db.flush()
            savepoint.commit()
            return asset
        except IntegrityError:
            savepoint.rollback()
            if explicit_tag:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"资产编号 {explicit_tag} 已存在",
                )
            # 自动编号撞车(历史数据占用了该号段),继续推进流水号
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="生成资产编号失败,请重试",
    )


# ---------- 借还 ----------
def open_checkouts_for(db: Session, asset_ids: Sequence[int]) -> Dict[int, CheckoutRecord]:
    """批量取「未归还」记录,避免列表页 N+1。"""
    if not asset_ids:
        return {}
    rows = db.execute(
        select(CheckoutRecord)
        .where(CheckoutRecord.asset_id.in_(asset_ids))
        .where(CheckoutRecord.checked_in_at.is_(None))
    ).scalars().all()
    return {r.asset_id: r for r in rows}


def is_overdue(record: CheckoutRecord) -> bool:
    return (
        record.checked_in_at is None
        and record.due_at is not None
        and record.due_at < utcnow()
    )


def checkout(db: Session, asset: Asset, borrower: User, operator: User,
             due_at=None, note: str = "") -> CheckoutRecord:
    """借出。

    PRD 3.5 并发控制:不做「先查后写」,直接插入并依赖
    uq_active_checkout_per_asset 唯一部分索引拦截重复借出。
    """
    if asset.status != AssetStatus.IN_STOCK:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"设备当前状态为「{STATUS_LABELS[asset.status]}」,不可借出",
        )
    record = CheckoutRecord(
        asset_id=asset.id,
        user_id=borrower.id,
        operator_id=operator.id,
        due_at=due_at,
        note=note,
    )
    db.add(record)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该设备已被借出,请刷新后重试",
        )
    log(db, operator.id, "checkout", "asset", asset.id,
        f"{asset.asset_tag} 借给 {borrower.real_name or borrower.username}")
    return record


def checkin(db: Session, asset: Asset, operator: User, note: str = "") -> CheckoutRecord:
    """归还。PRD 3.5:任何登录用户均可代为归还,但记录经办人。"""
    record = db.execute(
        select(CheckoutRecord)
        .where(CheckoutRecord.asset_id == asset.id)
        .where(CheckoutRecord.checked_in_at.is_(None))
    ).scalars().first()
    if record is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该设备当前不在借出状态")
    record.checked_in_at = utcnow()
    record.checkin_operator_id = operator.id
    if note:
        record.note = f"{record.note}\n归还备注:{note}".strip()
    db.flush()
    log(db, operator.id, "checkin", "asset", asset.id, f"{asset.asset_tag} 归还")
    return record


# ---------- 序列化 ----------
def _brief(user: Optional[User]) -> Optional[UserBrief]:
    return UserBrief.model_validate(user) if user else None


def asset_out(asset: Asset, open_record: Optional[CheckoutRecord]) -> AssetOut:
    current = None
    if open_record is not None:
        current = CheckoutBrief(
            record_id=open_record.id,
            user=_brief(open_record.user),
            checked_out_at=open_record.checked_out_at,
            due_at=open_record.due_at,
            is_overdue=is_overdue(open_record),
        )
    return AssetOut(
        id=asset.id,
        asset_tag=asset.asset_tag,
        name=asset.name,
        category_id=asset.category_id,
        category_name=asset.category.name if asset.category else "",
        brand=asset.brand,
        model=asset.model,
        serial_no=asset.serial_no,
        status=asset.status,
        status_label=STATUS_LABELS[asset.status],
        location=asset.location,
        owner=_brief(asset.owner),
        purchased_at=asset.purchased_at,
        company=CompanyBrief.model_validate(asset.company) if asset.company else None,
        note=asset.note,
        photo_url=asset.photo_url,
        is_checked_out=open_record is not None,
        current_checkout=current,
        created_at=asset.created_at,
        updated_at=asset.updated_at,
    )


def assets_out(db: Session, assets: Iterable[Asset]) -> List[AssetOut]:
    assets = list(assets)
    open_map = open_checkouts_for(db, [a.id for a in assets])
    return [asset_out(a, open_map.get(a.id)) for a in assets]


def record_out(record: CheckoutRecord) -> CheckoutRecordOut:
    return CheckoutRecordOut(
        id=record.id,
        asset_id=record.asset_id,
        asset_tag=record.asset.asset_tag,
        asset_name=record.asset.name,
        user=_brief(record.user),
        operator=_brief(record.operator),
        checkin_operator=_brief(record.checkin_operator) if record.checkin_operator_id else None,
        checked_out_at=record.checked_out_at,
        due_at=record.due_at,
        checked_in_at=record.checked_in_at,
        is_overdue=is_overdue(record),
        note=record.note,
    )
