"""业务逻辑:资产编号生成、借出/归还、序列化。"""
from typing import Dict, Iterable, List, Optional, Sequence

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from .config import settings
from .models import (
    STATUS_LABELS,
    ActivityLog,
    Asset,
    AssetStatus,
    Category,
    CheckoutRecord,
    InventoryCheck,
    RepairRecord,
    RepairResult,
    REPAIR_RESULT_LABELS,
    Role,
    User,
    utcnow,
)
from .schemas import (
    AssetOut,
    CheckoutBrief,
    CheckoutRecordOut,
    CompanyBrief,
    InventoryCheckBrief,
    InventoryCheckOut,
    RepairOut,
    UserBrief,
)


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


def last_checks_for(db: Session, asset_ids: Sequence[int]) -> Dict[int, InventoryCheck]:
    """批量取每台设备最后一次盘库,避免列表页 N+1。

    滚动盘点:「最后盘库时间」派生自 inventory_checks,不在 assets 上冗余字段 ——
    与「借出」的处理方式一致,避免两处数据打架。
    """
    if not asset_ids:
        return {}
    newest = (
        select(InventoryCheck.asset_id, func.max(InventoryCheck.checked_at).label("t"))
        .where(InventoryCheck.asset_id.in_(asset_ids))
        .group_by(InventoryCheck.asset_id)
        .subquery()
    )
    rows = db.execute(
        select(InventoryCheck)
        .join(
            newest,
            (InventoryCheck.asset_id == newest.c.asset_id)
            & (InventoryCheck.checked_at == newest.c.t),
        )
        .options(joinedload(InventoryCheck.checked_by))
    ).unique().scalars().all()
    return {r.asset_id: r for r in rows}


def record_inventory_check(
    db: Session,
    asset: Asset,
    actor: User,
    observed_location: Optional[str],
    observed_status: Optional[AssetStatus],
    note: str,
) -> InventoryCheck:
    """提交一次盘库。

    记录的是观察值,**永远能提交成功** —— 现场盘库的人不该因为权限或状态冲突
    而卡在半路。是否写回台账分两种情况:

    - 管理员盘出的差异当场写回
    - 普通用户盘出的差异挂起,进「待处理差异」列表由管理员确认

    另有一条既有规则要守住:借出中的设备不允许改状态(PRD 3.5),所以借出时
    即便是管理员,状态差异也只记录不写回,等归还后再处理。
    """
    open_record = open_checkouts_for(db, [asset.id]).get(asset.id)

    check = InventoryCheck(
        asset_id=asset.id,
        checked_by_id=actor.id,
        observed_location=observed_location if observed_location is not None else asset.location,
        observed_status=observed_status if observed_status is not None else asset.status,
        location_at_check=asset.location,
        status_at_check=asset.status,
        borrower_id=open_record.user_id if open_record else None,
        note=note,
    )

    if check.has_discrepancy and actor.role == Role.ADMIN:
        applied_any = False
        if check.observed_location != asset.location:
            asset.location = check.observed_location
            applied_any = True
        if check.observed_status != asset.status and open_record is None:
            asset.status = check.observed_status
            applied_any = True
        # 位置改了但状态因借出没改成 —— 仍算未处理完,留给管理员归还后再看
        still_pending = check.observed_status != asset.status
        if applied_any and not still_pending:
            check.applied = True
            check.resolved_at = utcnow()
            check.resolved_by_id = actor.id

    db.add(check)
    db.flush()
    detail = f"{asset.asset_tag} 盘库" + ("(有差异)" if check.has_discrepancy else "")
    log(db, actor.id, "inventory_check", "asset", asset.id, detail)
    return check


def resolve_inventory_check(
    db: Session, check: InventoryCheck, admin: User, action: str
) -> InventoryCheck:
    """管理员处理一条挂起的差异:采纳盘库值,或维持台账。"""
    if action == "apply":
        asset = check.asset
        if check.observed_status != asset.status:
            if open_checkouts_for(db, [asset.id]).get(asset.id) is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="设备借出中,请先办理归还再采纳状态变更",
                )
            asset.status = check.observed_status
        asset.location = check.observed_location
        check.applied = True
    check.resolved_at = utcnow()
    check.resolved_by_id = admin.id
    db.flush()
    log(db, admin.id, f"inventory_{action}", "asset", check.asset_id, check.asset.asset_tag)
    return check


def open_repairs_for(db: Session, asset_ids: Sequence[int]) -> Dict[int, RepairRecord]:
    """批量取「未完结」的报修记录,避免列表页 N+1。"""
    if not asset_ids:
        return {}
    rows = db.execute(
        select(RepairRecord)
        .where(RepairRecord.asset_id.in_(asset_ids))
        .where(RepairRecord.resolved_at.is_(None))
    ).scalars().all()
    return {r.asset_id: r for r in rows}


def open_repair(db: Session, asset: Asset, actor: User, symptom: str,
                vendor_id: Optional[int], note: str) -> RepairRecord:
    """报修。

    设备可能正借在别人手上坏掉 —— 记录照样建得起来,但状态先不动:
    「借出中不允许改状态」(PRD 3.5)这条要守住,等归还时 checkin 会把它翻成维修。
    """
    if asset.status == AssetStatus.RETIRED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="设备已报废,无需报修"
        )

    record = RepairRecord(
        asset_id=asset.id,
        reported_by_id=actor.id,
        symptom=symptom,
        vendor_id=vendor_id,
        note=note,
        under_warranty=bool(
            asset.warranty_until and asset.warranty_until >= utcnow().date()
        ),
    )
    db.add(record)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="该设备已有未完结的报修记录"
        )

    if open_checkouts_for(db, [asset.id]).get(asset.id) is None:
        asset.status = AssetStatus.REPAIR
    log(db, actor.id, "repair_open", "asset", asset.id, f"{asset.asset_tag} 报修:{symptom[:40]}")
    return record


def close_repair(db: Session, record: RepairRecord, actor: User, result: RepairResult,
                 cost_cents: Optional[int], under_warranty: Optional[bool],
                 note: str) -> RepairRecord:
    """结案。修好回在库,判定报废转报废,误报也回在库。"""
    asset = record.asset
    record.resolved_at = utcnow()
    record.resolved_by_id = actor.id
    record.result = result
    if cost_cents is not None:
        record.cost_cents = cost_cents
    if under_warranty is not None:
        record.under_warranty = under_warranty
    if note:
        record.note = "\n".join(filter(None, [record.note, f"结案:{note}"]))

    if result == RepairResult.SCRAPPED:
        asset.status = AssetStatus.RETIRED
    elif open_checkouts_for(db, [asset.id]).get(asset.id) is None:
        # 借出中的不动状态,由 checkin 负责收尾
        asset.status = AssetStatus.IN_STOCK

    db.flush()
    log(db, actor.id, f"repair_{result.value}", "asset", asset.id, asset.asset_tag)
    return record


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
    if open_repairs_for(db, [asset.id]).get(asset.id) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="设备有未完结的报修,不可借出"
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
    # 设备是在别人手上坏掉的:报修时状态没动过(借出中不允许改状态),
    # 归还这一刻才是把它翻成「维修」的正确时机
    if open_repairs_for(db, [asset.id]).get(asset.id) is not None:
        asset.status = AssetStatus.REPAIR
    if note:
        record.note = f"{record.note}\n归还备注:{note}".strip()
    db.flush()
    log(db, operator.id, "checkin", "asset", asset.id, f"{asset.asset_tag} 归还")
    return record


# ---------- 序列化 ----------
def _brief(user: Optional[User]) -> Optional[UserBrief]:
    return UserBrief.model_validate(user) if user else None


def asset_out(
    asset: Asset,
    open_record: Optional[CheckoutRecord],
    last_check: Optional[InventoryCheck] = None,
    open_repair_record: Optional[RepairRecord] = None,
) -> AssetOut:
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
        warranty_until=asset.warranty_until,
        warranty_valid=(asset.warranty_until >= utcnow().date()) if asset.warranty_until else None,
        company=CompanyBrief.model_validate(asset.company) if asset.company else None,
        note=asset.note,
        photo_url=asset.photo_url,
        is_checked_out=open_record is not None,
        current_checkout=current,
        last_check=check_brief(last_check),
        open_repair_id=open_repair_record.id if open_repair_record else None,
        created_at=asset.created_at,
        updated_at=asset.updated_at,
    )


def assets_out(db: Session, assets: Iterable[Asset]) -> List[AssetOut]:
    assets = list(assets)
    ids = [a.id for a in assets]
    open_map = open_checkouts_for(db, ids)
    check_map = last_checks_for(db, ids)
    repair_map = open_repairs_for(db, ids)
    return [
        asset_out(a, open_map.get(a.id), check_map.get(a.id), repair_map.get(a.id))
        for a in assets
    ]


def check_brief(check: Optional[InventoryCheck]) -> Optional[InventoryCheckBrief]:
    if check is None:
        return None
    return InventoryCheckBrief(
        id=check.id,
        checked_at=check.checked_at,
        checked_by=_brief(check.checked_by),
        has_discrepancy=check.has_discrepancy,
    )


def check_out(check: InventoryCheck) -> InventoryCheckOut:
    return InventoryCheckOut(
        id=check.id,
        asset_id=check.asset_id,
        asset_tag=check.asset.asset_tag,
        asset_name=check.asset.name,
        checked_by=_brief(check.checked_by),
        checked_at=check.checked_at,
        observed_location=check.observed_location,
        observed_status=check.observed_status,
        observed_status_label=STATUS_LABELS[check.observed_status],
        location_at_check=check.location_at_check,
        status_at_check=check.status_at_check,
        status_at_check_label=STATUS_LABELS[check.status_at_check],
        borrower=_brief(check.borrower),
        note=check.note,
        has_discrepancy=check.has_discrepancy,
        applied=check.applied,
        pending=check.has_discrepancy and check.resolved_at is None,
        resolved_at=check.resolved_at,
        resolved_by=_brief(check.resolved_by),
    )


def repair_out(record: RepairRecord) -> RepairOut:
    now = utcnow()
    end = record.resolved_at or now
    return RepairOut(
        id=record.id,
        asset_id=record.asset_id,
        asset_tag=record.asset.asset_tag,
        asset_name=record.asset.name,
        reported_by=_brief(record.reported_by),
        reported_at=record.reported_at,
        symptom=record.symptom,
        vendor=CompanyBrief.model_validate(record.vendor) if record.vendor else None,
        cost_yuan=round(record.cost_cents / 100, 2) if record.cost_cents is not None else None,
        under_warranty=record.under_warranty,
        note=record.note,
        is_open=record.resolved_at is None,
        days_open=max((end - record.reported_at).days, 0),
        resolved_at=record.resolved_at,
        resolved_by=_brief(record.resolved_by),
        result=record.result,
        result_label=REPAIR_RESULT_LABELS.get(record.result, "") if record.result else "",
    )


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
