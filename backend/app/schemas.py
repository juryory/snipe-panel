"""请求 / 响应模型。"""
from datetime import date, datetime, timezone
from typing import Annotated, Generic, List, Optional, TypeVar

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from .models import AssetStatus, Role

T = TypeVar("T")


def _attach_utc(v):
    """库里存的是朴素 UTC,出口补上时区,使 JSON 序列化带 +00:00。

    否则前端 new Date("2026-08-26T10:00:00") 会按浏览器本地时区解析,时间全错。
    """
    if isinstance(v, datetime) and v.tzinfo is None:
        return v.replace(tzinfo=timezone.utc)
    return v


UtcDatetime = Annotated[datetime, BeforeValidator(_attach_utc)]


# ---------- 通用 ----------
class Page(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    page_size: int


# ---------- 认证 ----------
class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class ChangePasswordIn(BaseModel):
    old_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


# ---------- 用户 ----------
class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    real_name: str
    department: str
    role: Role
    is_active: bool
    must_change_password: bool


class UserBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    real_name: str


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8, max_length=128)
    real_name: str = ""
    department: str = ""
    role: Role = Role.USER


class UserUpdate(BaseModel):
    real_name: Optional[str] = None
    department: Optional[str] = None
    role: Optional[Role] = None
    is_active: Optional[bool] = None


class ResetPasswordIn(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)


# ---------- 分类 ----------
class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    tag_prefix: str
    seq: int


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    # 前缀最长 5:前缀 + 连字符 + 4 位流水 = 10 个字符,正好是 QR version 1 在
    # 最高纠错等级 H 下的容量上限。再长一个字符就跳到 version 2(25x25),
    # 模块变小,12mm 标签会明显更难扫(见 routers/assets.py 的 _make_qr)。
    tag_prefix: str = Field(min_length=1, max_length=5, pattern=r"^[A-Za-z0-9]+$")


class CategoryUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=64)


# ---------- 设备 ----------
class AssetBase(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    brand: str = ""
    model: str = ""
    serial_no: str = ""
    location: str = ""
    owner_user_id: Optional[int] = None
    purchased_at: Optional[date] = None
    note: str = ""


class AssetCreate(AssetBase):
    category_id: int
    # PRD 3.2:支持导入存量设备时手工指定编号;留空则自动生成
    asset_tag: Optional[str] = Field(default=None, max_length=32)


class AssetUpdate(BaseModel):
    """PRD 3.2:asset_tag 不可变更,故不在此出现。

    PRD 3.5:status 只允许改为 在库/维修/报废,「借出」是派生状态,不可手工设置。
    """

    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    category_id: Optional[int] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    serial_no: Optional[str] = None
    status: Optional[AssetStatus] = None
    location: Optional[str] = None
    owner_user_id: Optional[int] = None
    purchased_at: Optional[date] = None
    note: Optional[str] = None


class CheckoutBrief(BaseModel):
    """当前借出信息(派生)。"""

    record_id: int
    user: UserBrief
    checked_out_at: UtcDatetime
    due_at: Optional[UtcDatetime]
    is_overdue: bool


class AssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_tag: str
    name: str
    category_id: int
    category_name: str
    brand: str
    model: str
    serial_no: str
    status: AssetStatus
    status_label: str
    location: str
    owner: Optional[UserBrief]
    purchased_at: Optional[date]
    note: str
    photo_url: Optional[str]
    # PRD 3.5:借出为派生状态
    is_checked_out: bool
    current_checkout: Optional[CheckoutBrief]
    created_at: UtcDatetime
    updated_at: UtcDatetime


# ---------- 借还 ----------
class CheckoutIn(BaseModel):
    user_id: Optional[int] = None  # 省略则为当前登录用户(PRD 3.5)
    due_at: Optional[datetime] = None
    note: str = ""


class CheckinIn(BaseModel):
    note: str = ""


class CheckoutRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_id: int
    asset_tag: str
    asset_name: str
    user: UserBrief
    operator: UserBrief
    checkin_operator: Optional[UserBrief]
    checked_out_at: UtcDatetime
    due_at: Optional[UtcDatetime]
    checked_in_at: Optional[UtcDatetime]
    is_overdue: bool
    note: str
