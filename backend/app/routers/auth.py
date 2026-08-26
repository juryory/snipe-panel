"""登录 / 登出 / 改密。对应 PRD 3.7。"""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import ratelimit
from ..config import settings
from ..db import get_db
from ..deps import current_user
from ..models import User, utcnow
from ..schemas import ChangePasswordIn, LoginIn, UserOut
from ..security import create_token, hash_password, needs_rehash, verify_password
from ..services import log

router = APIRouter(prefix="/api/auth", tags=["认证"])


def _set_cookie(response: Response, token: str) -> None:
    """PRD 3.7:JWT 存 httpOnly + SameSite=Lax Cookie,而非 localStorage。

    同域部署 + SameSite=Lax 已可防御跨站 CSRF,同时 XSS 也窃取不到 token。
    """
    response.set_cookie(
        key=settings.cookie_name,
        value=token,
        max_age=int(timedelta(days=settings.token_days).total_seconds()),
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


@router.post("/login", response_model=UserOut)
def login(payload: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    client_ip = request.client.host if request.client else "unknown"
    # PRD 3.7:同一 IP 独立限流
    if not ratelimit.allow(f"login:ip:{client_ip}", settings.login_ip_limit_per_minute):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="登录尝试过于频繁,请稍后再试",
        )

    user = db.execute(
        select(User).where(User.username == payload.username)
    ).scalars().first()

    # 用户不存在与密码错误返回同一提示,不泄露账号是否存在
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误"
    )
    if user is None:
        raise invalid

    # PRD 3.7:同一账号连续失败 5 次锁定 15 分钟
    if user.locked_until and user.locked_until > utcnow():
        remain = int((user.locked_until - utcnow()).total_seconds() // 60) + 1
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"账号已锁定,请 {remain} 分钟后再试",
        )

    if not user.is_active:
        raise invalid

    if not verify_password(payload.password, user.password_hash):
        user.failed_attempts += 1
        if user.failed_attempts >= settings.max_login_failures:
            user.locked_until = utcnow() + timedelta(minutes=settings.lockout_minutes)
            user.failed_attempts = 0
            log(db, user.id, "login_locked", "user", user.id, f"IP {client_ip}")
        db.commit()
        raise invalid

    # 登录成功:清零失败计数与锁定
    user.failed_attempts = 0
    user.locked_until = None
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(payload.password)
    log(db, user.id, "login", "user", user.id, f"IP {client_ip}")
    db.commit()

    _set_cookie(response, create_token(user.id))
    return UserOut.model_validate(user)


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(settings.cookie_name, path="/")
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return UserOut.model_validate(user)


@router.post("/change-password", response_model=UserOut)
def change_password(
    payload: ChangePasswordIn,
    response: Response,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(payload.old_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="原密码错误")
    if payload.old_password == payload.new_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="新密码不能与原密码相同")
    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    log(db, user.id, "change_password", "user", user.id)
    db.commit()
    # 改密后换发 token
    _set_cookie(response, create_token(user.id))
    return UserOut.model_validate(user)
