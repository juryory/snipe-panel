"""设备台账、扫码查询、二维码、借还。对应 PRD 3.1 / 3.2 / 3.5 / 3.6。"""
import csv
import io
import zipfile
from datetime import timedelta
from typing import List, Optional

import segno
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from .. import ratelimit
from ..config import settings
from ..db import get_db
from ..deps import active_user, admin_user
from ..models import (
    Asset,
    AssetStatus,
    Category,
    CheckoutRecord,
    Company,
    InventoryCheck,
    Role,
    User,
    to_naive_utc,
    utcnow,
)
from ..schemas import (
    AssetCreate,
    AssetOut,
    AssetUpdate,
    CheckinIn,
    CheckoutIn,
    CheckoutRecordOut,
    InventoryCheckIn,
    InventoryCheckOut,
    Page,
)
from ..services import (
    asset_out,
    assets_out,
    check_out,
    checkin,
    checkout,
    create_asset_with_tag,
    last_checks_for,
    log,
    open_checkouts_for,
    open_repairs_for,
    record_inventory_check,
    record_out,
)

router = APIRouter(prefix="/api/assets", tags=["设备"])


def _base_query():
    return (
        select(Asset)
        .where(Asset.deleted_at.is_(None))
        .options(
            joinedload(Asset.category),
            joinedload(Asset.owner),
            joinedload(Asset.company),
        )
    )


def _get_asset(db: Session, asset_id: int) -> Asset:
    asset = db.execute(_base_query().where(Asset.id == asset_id)).scalars().first()
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="设备不存在")
    return asset


def _one(db: Session, asset: Asset) -> AssetOut:
    """单台设备的完整输出:借出、最后盘库、在修都是派生的,统一在这里补齐。"""
    return asset_out(
        asset,
        open_checkouts_for(db, [asset.id]).get(asset.id),
        last_checks_for(db, [asset.id]).get(asset.id),
        open_repairs_for(db, [asset.id]).get(asset.id),
    )


def _open_checkout_subquery():
    """「借出中」的设备 id 子查询(PRD 3.5:借出为派生状态,不存字段)。"""
    return select(CheckoutRecord.asset_id).where(CheckoutRecord.checked_in_at.is_(None))


def _make_qr(tag: str):
    """PRD 3.2:二维码内容 = 纯资产编号字符串,绝不放 URL。

    目的是让标签在本系统之外被扫到时读不出任何信息:任意扫码器扫这张标签只会得到
    一串 PC-0001,无法跳转、无法查询、看不出是什么设备。
    micro=False 不能去掉:编号只有 7 个字符,segno 默认会挑 Micro QR(M3,15x15),
    而 ZXing 与浏览器 BarcodeDetector 都不支持 Micro QR —— 标签打出来我们自己的
    扫码页反而读不出。强制标准 QR version 1(21x21)。

    error="h"(30% 纠错)是免费的:version 1 在 H 级下仍能装 10 个字母数字字符,
    而编号最长就是 10 个字符(前缀 5 + 连字符 + 4 位流水,见 CategoryCreate)。
    也就是说码的尺寸一格没变,抗磨损能力却从 15% 提到 30%。设备标签会蹭脏、
    磨损、被手指盖住一角,这个余量很值。
    超过 10 个字符会跳到 version 2(25x25),模块变小、12mm 标签更难扫。

    border=4 是 QR 规范要求的静默区,不能省。码四周留白不够时扫码器会找不到
    定位图形 —— 在已经接近打印极限的 12mm 标签上,这是最不该省的地方。
    """
    return segno.make(tag, error="h", micro=False)


@router.get("", response_model=Page[AssetOut])
def list_assets(
    q: Optional[str] = Query(None, description="搜索:编号 / 名称 / SN / 责任人"),
    category_id: Optional[int] = None,
    company_id: Optional[int] = Query(None, description="按采购公司筛选"),
    status_: Optional[AssetStatus] = Query(None, alias="status"),
    location: Optional[str] = None,
    checked_out: Optional[bool] = Query(None, description="是否借出中"),
    unchecked_days: Optional[int] = Query(
        None, ge=0, description="只看超过 N 天未盘库的(含从未盘库)"
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(active_user),
):
    stmt = _base_query()
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.outerjoin(User, Asset.owner_user_id == User.id).where(
            or_(
                Asset.asset_tag.ilike(like),
                Asset.name.ilike(like),
                Asset.serial_no.ilike(like),
                User.real_name.ilike(like),
                User.username.ilike(like),
            )
        )
    if category_id is not None:
        stmt = stmt.where(Asset.category_id == category_id)
    if company_id is not None:
        stmt = stmt.where(Asset.company_id == company_id)
    if status_ is not None:
        stmt = stmt.where(Asset.status == status_)
    if location:
        stmt = stmt.where(Asset.location.ilike(f"%{location}%"))
    if checked_out is True:
        stmt = stmt.where(Asset.id.in_(_open_checkout_subquery()))
    elif checked_out is False:
        stmt = stmt.where(Asset.id.not_in(_open_checkout_subquery()))
    if unchecked_days is not None:
        # 滚动盘点的待办清单:N 天内盘过的排除掉,剩下的(含从未盘过的)就是要盘的
        cutoff = utcnow() - timedelta(days=unchecked_days)
        recent = select(InventoryCheck.asset_id).where(InventoryCheck.checked_at >= cutoff)
        stmt = stmt.where(Asset.id.not_in(recent))

    total = db.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ).scalar_one()
    rows = (
        db.execute(
            stmt.order_by(Asset.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .unique()
        .scalars()
        .all()
    )
    return Page[AssetOut](
        items=assets_out(db, rows), total=total, page=page, page_size=page_size
    )


@router.post("", response_model=AssetOut, status_code=status.HTTP_201_CREATED)
def create_asset(
    payload: AssetCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_user),
):
    category = db.get(Category, payload.category_id)
    if category is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="分类不存在")
    if payload.company_id is not None and db.get(Company, payload.company_id) is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="采购公司不存在")
    fields = payload.model_dump(exclude={"category_id", "asset_tag"})
    tag = payload.asset_tag.strip().upper() if payload.asset_tag else None
    asset = create_asset_with_tag(db, category, tag, **fields)
    log(db, admin.id, "asset_create", "asset", asset.id, asset.asset_tag)
    db.commit()
    return _one(db, _get_asset(db, asset.id))


# ★ PRD 3.2:扫码查询。必须鉴权 + 限流,防止按编号规律枚举全量台账。
# 此路由必须注册在 /{asset_id} 之前,否则 "by-tag" 会被当作 asset_id 匹配。
@router.get("/by-tag/{tag}", response_model=AssetOut)
def get_by_tag(tag: str, db: Session = Depends(get_db), user: User = Depends(active_user)):
    if not ratelimit.allow(f"bytag:{user.id}", settings.by_tag_limit_per_minute):
        log(db, user.id, "by_tag_rate_limited", "asset", None, tag)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="查询过于频繁,请稍后再试",
        )
    asset = (
        db.execute(_base_query().where(Asset.asset_tag == tag.strip().upper()))
        .scalars()
        .first()
    )
    if asset is None:
        # PRD 3.2:统一 404,不返回可确认编号空间的提示
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到该设备")
    return _one(db, asset)


@router.post("/qrcodes/export")
def export_qrcodes(
    asset_ids: List[int],
    fmt: str = Query("csv", pattern="^(csv|zip)$"),
    db: Session = Depends(get_db),
    _: User = Depends(admin_user),
):
    """批量导出。

    csv:编号列表,供精臣 NIIMBOT 云打印批量生成 12mm 标签(PRD 3.3 的 MVP 做法)
    zip:二维码 PNG 图片包
    """
    rows = (
        db.execute(_base_query().where(Asset.id.in_(asset_ids)).order_by(Asset.asset_tag))
        .unique()
        .scalars()
        .all()
    )
    if not rows:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="没有可导出的设备")

    if fmt == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["资产编号", "设备名称", "分类"])
        for a in rows:
            writer.writerow([a.asset_tag, a.name, a.category.name if a.category else ""])
        # 前置 BOM,Excel 才会按 UTF-8 解析中文
        data = ("﻿" + buf.getvalue()).encode("utf-8")
        return Response(
            content=data,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="asset_tags.csv"'},
        )

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for a in rows:
            png = io.BytesIO()
            _make_qr(a.asset_tag).save(png, kind="png", scale=8, border=4)
            zf.writestr(f"{a.asset_tag}.png", png.getvalue())
    zip_buf.seek(0)
    return StreamingResponse(
        zip_buf,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="qrcodes.zip"'},
    )


@router.get("/{asset_id}", response_model=AssetOut)
def get_asset(asset_id: int, db: Session = Depends(get_db), _: User = Depends(active_user)):
    return _one(db, _get_asset(db, asset_id))


@router.put("/{asset_id}", response_model=AssetOut)
def update_asset(
    asset_id: int,
    payload: AssetUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_user),
):
    asset = _get_asset(db, asset_id)
    data = payload.model_dump(exclude_unset=True)

    new_status = data.get("status")
    if new_status is not None and new_status != asset.status:
        # PRD 3.5:借出中的设备不允许改状态,否则与未归还记录矛盾
        if open_checkouts_for(db, [asset.id]).get(asset.id) is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="设备借出中,请先办理归还再修改状态",
            )
    if data.get("company_id") is not None and data["company_id"] != asset.company_id:
        if db.get(Company, data["company_id"]) is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="采购公司不存在")
    if "category_id" in data and data["category_id"] != asset.category_id:
        if db.get(Category, data["category_id"]) is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="分类不存在")
        # PRD 3.2:改分类不改编号 —— asset_tag 一经生成永不变更

    for key, value in data.items():
        setattr(asset, key, value)
    log(db, admin.id, "asset_update", "asset", asset.id, ",".join(data.keys()))
    db.commit()
    # Session 是 expire_on_commit=False,提交后对象上已加载的关系不会失效。
    # 改了 category_id / company_id 后若不显式过期,下面的 joinedload 会命中
    # identity map 里的旧对象,返回改动前的分类名和采购公司。
    db.expire(asset)
    return _one(db, _get_asset(db, asset_id))


@router.delete("/{asset_id}")
def delete_asset(asset_id: int, db: Session = Depends(get_db), admin: User = Depends(admin_user)):
    """软删除(PRD 3.1:保留历史)。"""
    asset = _get_asset(db, asset_id)
    if open_checkouts_for(db, [asset.id]).get(asset.id) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="设备借出中,请先办理归还再删除"
        )
    asset.deleted_at = utcnow()
    log(db, admin.id, "asset_delete", "asset", asset.id, asset.asset_tag)
    db.commit()
    return {"ok": True}


@router.get("/{asset_id}/qrcode")
def asset_qrcode(
    asset_id: int,
    format: str = Query("png", pattern="^(png|svg)$"),
    scale: int = Query(8, ge=1, le=40),
    db: Session = Depends(get_db),
    _: User = Depends(active_user),
):
    asset = _get_asset(db, asset_id)
    buf = io.BytesIO()
    _make_qr(asset.asset_tag).save(buf, kind=format, scale=scale, border=4)
    media = "image/png" if format == "png" else "image/svg+xml"
    return Response(content=buf.getvalue(), media_type=media)


@router.post("/{asset_id}/checkout", response_model=CheckoutRecordOut)
def checkout_asset(
    asset_id: int,
    payload: CheckoutIn,
    db: Session = Depends(get_db),
    user: User = Depends(active_user),
):
    """借出。PRD 3.5:领用人默认为当前登录用户;代他人借出需管理员。"""
    asset = _get_asset(db, asset_id)
    borrower = user
    if payload.user_id is not None and payload.user_id != user.id:
        if user.role != Role.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="只有管理员可代他人借出"
            )
        borrower = db.get(User, payload.user_id)
        if borrower is None or not borrower.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="领用人不存在")

    record = checkout(
        db, asset, borrower, user, due_at=to_naive_utc(payload.due_at), note=payload.note
    )
    db.commit()
    return record_out(record)


@router.post("/{asset_id}/checkin", response_model=CheckoutRecordOut)
def checkin_asset(
    asset_id: int,
    payload: CheckinIn,
    db: Session = Depends(get_db),
    user: User = Depends(active_user),
):
    """归还。PRD 3.5:任何登录用户均可代为归还,但记录经办人。"""
    asset = _get_asset(db, asset_id)
    record = checkin(db, asset, user, note=payload.note)
    db.commit()
    return record_out(record)


@router.post("/{asset_id}/check", response_model=InventoryCheckOut)
def check_asset(
    asset_id: int,
    payload: InventoryCheckIn,
    db: Session = Depends(get_db),
    user: User = Depends(active_user),
):
    """盘库。位置 / 状态留空表示与台账一致(确认无误)。

    任何登录用户都能提交;管理员盘出的差异当场写回台账,普通用户盘出的差异
    挂起进「待处理差异」列表等管理员确认。
    """
    asset = _get_asset(db, asset_id)
    check = record_inventory_check(
        db, asset, user, payload.observed_location, payload.observed_status, payload.note
    )
    db.commit()
    return check_out(check)


@router.get("/{asset_id}/checks", response_model=List[InventoryCheckOut])
def asset_checks(asset_id: int, db: Session = Depends(get_db), _: User = Depends(active_user)):
    """该设备的盘库历史。"""
    asset = _get_asset(db, asset_id)
    rows = (
        db.execute(
            select(InventoryCheck)
            .where(InventoryCheck.asset_id == asset.id)
            .order_by(InventoryCheck.checked_at.desc())
            .limit(50)
        )
        .scalars()
        .all()
    )
    return [check_out(r) for r in rows]


@router.get("/{asset_id}/history", response_model=List[CheckoutRecordOut])
def asset_history(asset_id: int, db: Session = Depends(get_db), _: User = Depends(active_user)):
    asset = _get_asset(db, asset_id)
    rows = (
        db.execute(
            select(CheckoutRecord)
            .where(CheckoutRecord.asset_id == asset.id)
            .order_by(CheckoutRecord.checked_out_at.desc())
        )
        .scalars()
        .all()
    )
    return [record_out(r) for r in rows]
