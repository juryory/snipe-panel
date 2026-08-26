"""请求依赖:当前用户、角色校验。"""
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import Role, User
from .security import decode_token


def _unauthorized() -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token: Optional[str] = request.cookies.get(settings.cookie_name)
    if not token:
        raise _unauthorized()
    user_id = decode_token(token)
    if user_id is None:
        raise _unauthorized()
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _unauthorized()
    return user


def active_user(user: User = Depends(current_user)) -> User:
    """已登录且已完成首次改密的用户。

    PRD 3.7:首次登录强制改密——未改密前除改密接口外一律拒绝。
    """
    if user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="首次登录请先修改密码",
        )
    return user


def admin_user(user: User = Depends(active_user)) -> User:
    if user.role != Role.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return user
