"""用户管理。对应 PRD 3.7:不开放自助注册,账号一律由管理员创建。"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import active_user, admin_user
from ..models import Role, User
from ..schemas import ResetPasswordIn, UserBrief, UserCreate, UserOut, UserUpdate
from ..security import hash_password
from ..services import log

router = APIRouter(prefix="/api/users", tags=["用户"])


@router.get("", response_model=List[UserBrief])
def list_users(
    q: str = Query("", description="按用户名 / 姓名搜索"),
    db: Session = Depends(get_db),
    _: User = Depends(active_user),
):
    """供借出时选择领用人。普通用户也需要,故只返回简要字段。"""
    stmt = select(User).where(User.is_active.is_(True))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(User.username.ilike(like), User.real_name.ilike(like)))
    rows = db.execute(stmt.order_by(User.real_name, User.username).limit(200)).scalars().all()
    return [UserBrief.model_validate(u) for u in rows]


@router.get("/detail", response_model=List[UserOut])
def list_users_detail(db: Session = Depends(get_db), _: User = Depends(admin_user)):
    rows = db.execute(select(User).order_by(User.id)).scalars().all()
    return [UserOut.model_validate(u) for u in rows]


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate, db: Session = Depends(get_db), admin: User = Depends(admin_user)
):
    user = User(
        username=payload.username.strip(),
        password_hash=hash_password(payload.password),
        real_name=payload.real_name,
        department=payload.department,
        role=payload.role,
        must_change_password=True,  # PRD 3.7:首次登录强制改密
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已存在")
    log(db, admin.id, "user_create", "user", user.id, user.username)
    db.commit()
    return UserOut.model_validate(user)


@router.put("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_user),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    data = payload.model_dump(exclude_unset=True)
    # 不允许把自己降级或停用,避免管理员把自己锁在系统外
    if user.id == admin.id:
        if data.get("role") == Role.USER or data.get("is_active") is False:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="不能降级或停用当前登录的管理员账号"
            )
    for key, value in data.items():
        setattr(user, key, value)
    log(db, admin.id, "user_update", "user", user.id, ",".join(data.keys()))
    db.commit()
    return UserOut.model_validate(user)


@router.post("/{user_id}/reset-password", response_model=UserOut)
def reset_password(
    user_id: int,
    payload: ResetPasswordIn,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_user),
):
    """PRD 3.7:忘记密码 = 找管理员重置,MVP 不做邮件找回流程。"""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = True
    user.failed_attempts = 0
    user.locked_until = None  # 重置密码同时解锁
    log(db, admin.id, "user_reset_password", "user", user.id, user.username)
    db.commit()
    return UserOut.model_validate(user)
