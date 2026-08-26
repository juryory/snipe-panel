"""请求 / 响应模型。"""
from datetime import date, datetime, timezone
from typing import Annotated, Generic, List, Literal, Optional, TypeVar

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from .models import AssetStatus, RepairResult, Role

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


# ---------- 采购公司 ----------
class CompanyBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    contact: str
    phone: str
    note: str
    asset_count: int = 0


class CompanyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    contact: str = ""
    phone: str = Field(default="", max_length=32)
    note: str = ""


class CompanyUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    contact: Optional[str] = None
    phone: Optional[str] = Field(default=None, max_length=32)
    note: Optional[str] = None


# ---------- 盘库 ----------
class InventoryCheckIn(BaseModel):
    """提交盘库。

    位置和状态留空 = 与台账一致(即「确认无误」)。连续扫码盘库时整个 body
    可以是空的,一次调用完成一台。
    """

    observed_location: Optional[str] = Field(default=None, max_length=128)
    observed_status: Optional[AssetStatus] = None
    note: str = ""


class InventoryCheckBrief(BaseModel):
    """设备上的「最后一次盘库」摘要。"""

    id: int
    checked_at: UtcDatetime
    checked_by: UserBrief
    has_discrepancy: bool


class InventoryCheckOut(BaseModel):
    id: int
    asset_id: int
    asset_tag: str
    asset_name: str
    checked_by: UserBrief
    checked_at: UtcDatetime
    observed_location: str
    observed_status: AssetStatus
    observed_status_label: str
    location_at_check: str
    status_at_check: AssetStatus
    status_at_check_label: str
    borrower: Optional[UserBrief]
    note: str
    has_discrepancy: bool
    applied: bool
    pending: bool  # 有差异且尚未处理
    resolved_at: Optional[UtcDatetime]
    resolved_by: Optional[UserBrief]


class ResolveCheckIn(BaseModel):
    # apply = 采纳盘库看到的值写回台账;dismiss = 维持台账,仅留档
    action: Literal["apply", "dismiss"]


# ---------- 报修 ----------
class RepairOpenIn(BaseModel):
    symptom: str = Field(min_length=1, max_length=2000)
    vendor_id: Optional[int] = None
    note: str = ""


class RepairUpdateIn(BaseModel):
    symptom: Optional[str] = Field(default=None, min_length=1, max_length=2000)
    vendor_id: Optional[int] = None
    cost_yuan: Optional[float] = Field(default=None, ge=0)
    under_warranty: Optional[bool] = None
    note: Optional[str] = None


class RepairCloseIn(BaseModel):
    result: RepairResult
    cost_yuan: Optional[float] = Field(default=None, ge=0)
    under_warranty: Optional[bool] = None
    note: str = ""


class RepairOut(BaseModel):
    id: int
    asset_id: int
    asset_tag: str
    asset_name: str
    reported_by: UserBrief
    reported_at: UtcDatetime
    symptom: str
    vendor: Optional[CompanyBrief]
    # 出口用「元」,库里存「分」—— 用浮点存钱迟早出现 0.1+0.2 这种账
    cost_yuan: Optional[float]
    under_warranty: bool
    note: str
    is_open: bool
    days_open: int
    resolved_at: Optional[UtcDatetime]
    resolved_by: Optional[UserBrief]
    result: Optional[RepairResult]
    result_label: str


# ---------- 设备 ----------
class AssetBase(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    brand: str = ""
    model: str = ""
    serial_no: str = ""
    location: str = ""
    owner_user_id: Optional[int] = None
    purchased_at: Optional[date] = None
    warranty_until: Optional[date] = None
    company_id: Optional[int] = None
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
    warranty_until: Optional[date] = None
    company_id: Optional[int] = None
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
    warranty_until: Optional[date]
    warranty_valid: Optional[bool]  # 保修是否还在有效期内;没填到期日则为 None
    company: Optional[CompanyBrief]
    note: str
    photo_url: Optional[str]
    # PRD 3.5:借出为派生状态
    is_checked_out: bool
    current_checkout: Optional[CheckoutBrief]
    # 滚动盘点:最后一次盘库,同样派生自 inventory_checks,不存字段
    last_check: Optional[InventoryCheckBrief]
    # 在修中同样是派生的:存在未完结的报修记录
    open_repair_id: Optional[int]
    created_at: UtcDatetime
    updated_at: UtcDatetime


# ---------- 批量导入 ----------
class ImportRowOut(BaseModel):
    row: int  # Excel 里的行号,方便对着改
    name: str
    asset_tag: Optional[str]
    category: str
    ok: bool
    errors: List[str]
    warnings: List[str]


class ImportPreview(BaseModel):
    total: int
    ok_count: int
    error_count: int
    committed: bool  # False = 只是预演,没写库
    rows: List[ImportRowOut]


# ---------- 借还 ----------
class CheckoutIn(BaseModel):
    user_id: Optional[int] = None  # 省略则为当前登录用户(PRD 3.5)
    due_at: Optional[datetime] = None
    note: str = ""


class KitCheckoutIn(BaseModel):
    asset_ids: List[int] = Field(min_length=1, max_length=50)
    user_id: Optional[int] = None  # 省略则为当前登录用户
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
    kit_id: Optional[str]  # 同一次成套借出的记录共用
    note: str
