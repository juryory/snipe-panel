"""操作日志查询,以及给 n8n 用的逾期清单。

日志一直在写,但此前没有任何界面能看 —— 写了不看等于没写。出「谁把这台设备
状态改了」这种争议时,不该只能去翻数据库。
"""
from datetime import timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from ..config import settings
from ..db import get_db
from ..deps import admin_user
from ..models import ActivityLog, CheckoutRecord, User, utcnow
from ..schemas import ActivityLogOut, Page
from ..services import is_overdue

router = APIRouter(prefix="/api", tags=["日志"])

# 界面上用得到的中文说明。没列到的动作原样显示,不至于漏掉新加的类型
ACTION_LABELS = {
    "login": "登录",
    "login_locked": "账号锁定",
    "change_password": "修改密码",
    "asset_create": "新增设备",
    "asset_update": "编辑设备",
    "asset_delete": "删除设备",
    "asset_import": "批量导入",
    "checkout": "借出",
    "checkout_kit": "成套借出",
    "checkin": "归还",
    "inventory_check": "盘库",
    "inventory_apply": "采纳盘库差异",
    "inventory_dismiss": "忽略盘库差异",
    "by_tag_rate_limited": "扫码查询被限流",
    "repair_open": "报修",
    "repair_update": "维修跟进",
    "repair_fixed": "维修完成",
    "repair_scrapped": "维修判废",
    "repair_cancelled": "报修误报",
    "category_create": "新增分类",
    "category_update": "编辑分类",
    "category_delete": "删除分类",
    "company_create": "新增采购公司",
    "company_update": "编辑采购公司",
    "company_delete": "删除采购公司",
    "user_create": "新增用户",
    "user_update": "编辑用户",
    "user_reset_password": "重置密码",
}


@router.get("/logs", response_model=Page[ActivityLogOut])
def list_logs(
    action: Optional[str] = None,
    actor_id: Optional[int] = None,
    days: int = Query(30, ge=1, le=365, description="只看最近多少天"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(admin_user),
):
    stmt = (
        select(ActivityLog)
        .where(ActivityLog.created_at >= utcnow() - timedelta(days=days))
        .options(joinedload(ActivityLog.actor))
    )
    if action:
        stmt = stmt.where(ActivityLog.action == action)
    if actor_id is not None:
        stmt = stmt.where(ActivityLog.actor_id == actor_id)

    total = db.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ).scalar_one()
    rows = (
        db.execute(
            stmt.order_by(ActivityLog.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .unique()
        .scalars()
        .all()
    )
    items = [
        ActivityLogOut(
            id=r.id,
            actor=(r.actor.real_name or r.actor.username) if r.actor else "系统",
            action=r.action,
            action_label=ACTION_LABELS.get(r.action, r.action),
            target_type=r.target_type,
            target_id=r.target_id,
            detail=r.detail,
            created_at=r.created_at,
        )
        for r in rows
    ]
    return Page[ActivityLogOut](items=items, total=total, page=page, page_size=page_size)


@router.get("/logs/actions", response_model=List[str])
def list_actions(db: Session = Depends(get_db), _: User = Depends(admin_user)):
    """实际出现过的动作类型,给筛选下拉用。"""
    return list(
        db.execute(select(ActivityLog.action).distinct().order_by(ActivityLog.action))
        .scalars()
        .all()
    )


@router.get("/internal/overdue")
def overdue_digest(
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
):
    """逾期清单,给 n8n 定时拉。

    不走登录 Cookie:定时任务没法维持会话。用 SNIPE_WEBHOOK_TOKEN 做 Bearer,
    没配 token 就直接关掉这个入口 —— 不能让它默认裸奔在公网上。
    """
    token = settings.webhook_token
    if not token:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="未启用(需设置 SNIPE_WEBHOOK_TOKEN)"
        )
    if authorization != f"Bearer {token}":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="令牌无效")

    rows = (
        db.execute(
            select(CheckoutRecord)
            .where(CheckoutRecord.checked_in_at.is_(None))
            .where(CheckoutRecord.due_at.is_not(None), CheckoutRecord.due_at < utcnow())
            .options(
                joinedload(CheckoutRecord.asset), joinedload(CheckoutRecord.user)
            )
            .order_by(CheckoutRecord.due_at)
        )
        .unique()
        .scalars()
        .all()
    )
    now = utcnow()
    return {
        "count": len(rows),
        "items": [
            {
                "asset_tag": r.asset.asset_tag,
                "asset_name": r.asset.name,
                "borrower": r.user.real_name or r.user.username,
                "due_at": r.due_at.isoformat() + "Z",
                "days_overdue": max((now - r.due_at).days, 0),
            }
            for r in rows
            if is_overdue(r)
        ],
    }
