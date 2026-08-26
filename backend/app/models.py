"""数据模型。对应 PRD 第 5 节。"""
import enum
from datetime import date, datetime, timezone
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    """朴素 UTC 时间。

    SQLite 的 DATETIME 列不保存时区偏移,若写入带时区的 datetime,偏移会被静默丢弃,
    读回来是朴素时间,再与带时区的 now() 比较就会抛 TypeError。
    因此全库统一存朴素 UTC,出口处再补上时区(见 schemas.UtcDatetime)。
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """把外部传入的时间(可能带时区)归一化为朴素 UTC。"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


class Role(str, enum.Enum):
    ADMIN = "admin"
    USER = "user"


class AssetStatus(str, enum.Enum):
    """设备自身状态。

    PRD 3.5:不含「借出」——借出是派生状态,由是否存在未归还的借还记录判定,
    避免 status 与 checkout_records 不一致。
    """

    IN_STOCK = "in_stock"   # 在库
    REPAIR = "repair"       # 维修
    RETIRED = "retired"     # 报废


STATUS_LABELS = {
    AssetStatus.IN_STOCK: "在库",
    AssetStatus.REPAIR: "维修",
    AssetStatus.RETIRED: "报废",
}


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    real_name: Mapped[str] = mapped_column(String(64), default="")
    department: Mapped[str] = mapped_column(String(64), default="")
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.USER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # PRD 3.7:首次登录强制改密
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True)
    # PRD 3.7:同一账号连续失败 5 次锁定 15 分钟
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    # PRD 3.2:前缀唯一,仅在生成编号时使用一次
    tag_prefix: Mapped[str] = mapped_column(String(16), unique=True)
    seq: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    assets: Mapped[List["Asset"]] = relationship(back_populates="category")


class Company(Base):
    """采购公司(供应商)。"""

    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    contact: Mapped[str] = mapped_column(String(64), default="")
    phone: Mapped[str] = mapped_column(String(32), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    # PRD 3.2:一经生成永不变更
    asset_tag: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    brand: Mapped[str] = mapped_column(String(64), default="")
    model: Mapped[str] = mapped_column(String(64), default="")
    serial_no: Mapped[str] = mapped_column(String(128), default="", index=True)
    status: Mapped[AssetStatus] = mapped_column(Enum(AssetStatus), default=AssetStatus.IN_STOCK)
    location: Mapped[str] = mapped_column(String(128), default="")
    # PRD 3.1:长期责任人,借还流程不修改此字段
    owner_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    purchased_at: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    # 保修到期日。报修时要一眼看出是走保修还是自费
    warranty_until: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    # 采购公司。设备可能是历史遗留、没有采购记录,故可空
    company_id: Mapped[Optional[int]] = mapped_column(ForeignKey("companies.id"), nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    photo_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)

    category: Mapped[Category] = relationship(back_populates="assets")
    owner: Mapped[Optional[User]] = relationship(foreign_keys=[owner_user_id])
    company: Mapped[Optional[Company]] = relationship()


class CheckoutRecord(Base):
    __tablename__ = "checkout_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)  # 领用人
    checked_out_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    checked_in_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    operator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))  # 经办人
    checkin_operator_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    kit_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # PRD 3.5:成套借用预留
    note: Mapped[str] = mapped_column(Text, default="")

    asset: Mapped[Asset] = relationship()
    user: Mapped[User] = relationship(foreign_keys=[user_id])
    operator: Mapped[User] = relationship(foreign_keys=[operator_id])
    checkin_operator: Mapped[Optional[User]] = relationship(foreign_keys=[checkin_operator_id])


# PRD 3.5 并发控制:同一设备至多一条未归还记录。
# 这是数据库层的硬约束,借出走「插入 + 捕获唯一冲突」而非「先查后写」。
Index(
    "uq_active_checkout_per_asset",
    CheckoutRecord.asset_id,
    unique=True,
    sqlite_where=CheckoutRecord.checked_in_at.is_(None),
)


class InventoryCheck(Base):
    """盘库记录:某人在某时刻核对了某台设备。

    PRD 阶段二「盘点」。采用滚动盘点 —— 不建盘点任务实体,而是让每台设备算出
    「最后盘库时间」,台账按「超过 N 天未盘库」筛选,超期列表即待办清单。

    记录的是**观察值**,永远可以提交成功;是否写回台账另说(见 applied)。
    这样现场盘库的人不会因为权限或状态冲突而卡住。
    """

    __tablename__ = "inventory_checks"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    checked_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    # 盘库时实际看到的
    observed_location: Mapped[str] = mapped_column(String(128), default="")
    observed_status: Mapped[AssetStatus] = mapped_column(Enum(AssetStatus))

    # 盘库当时台账里记的(快照)。存下来才能事后追「位置漂移」的历史,
    # 光比对当前台账是不够的 —— 台账后来又被改过就对不上了。
    location_at_check: Mapped[str] = mapped_column(String(128), default="")
    status_at_check: Mapped[AssetStatus] = mapped_column(Enum(AssetStatus))

    # 盘库当时借给谁(可空)。在同事桌上盘到设备是正常情况,不算异常
    borrower_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)

    note: Mapped[str] = mapped_column(Text, default="")

    # 差异是否已写回台账。管理员盘库时当场写回;普通用户盘出的差异挂起待处理
    applied: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    resolved_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)

    asset: Mapped[Asset] = relationship()
    checked_by: Mapped[User] = relationship(foreign_keys=[checked_by_id])
    borrower: Mapped[Optional[User]] = relationship(foreign_keys=[borrower_id])
    resolved_by: Mapped[Optional[User]] = relationship(foreign_keys=[resolved_by_id])

    @property
    def has_discrepancy(self) -> bool:
        """是否与台账不符。派生,不存字段 —— 与「借出」的处理方式一致。"""
        return (
            self.observed_location != self.location_at_check
            or self.observed_status != self.status_at_check
        )


class RepairResult(str, enum.Enum):
    FIXED = "fixed"          # 已修好
    SCRAPPED = "scrapped"    # 判定报废
    CANCELLED = "cancelled"  # 误报,设备没问题


REPAIR_RESULT_LABELS = {
    RepairResult.FIXED: "已修好",
    RepairResult.SCRAPPED: "判定报废",
    RepairResult.CANCELLED: "误报",
}


class RepairRecord(Base):
    """报修记录。

    「状态=维修」只说明设备现在不能用,说不出**为什么修、送去哪了、什么时候回来**。
    实际场景里一台相机送修三周,期间谁都不知道它在哪 —— 这张表就是补这个。
    """

    __tablename__ = "repair_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    reported_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    reported_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    symptom: Mapped[str] = mapped_column(Text)  # 故障描述
    # 送修给谁。多半就是当初的采购公司,故复用 companies
    vendor_id: Mapped[Optional[int]] = mapped_column(ForeignKey("companies.id"), nullable=True)
    # 费用存「分」:SQLite 没有真正的定点数,用浮点存钱迟早出现 0.1+0.2 这种账
    cost_cents: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    under_warranty: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str] = mapped_column(Text, default="")

    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    resolved_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    result: Mapped[Optional[RepairResult]] = mapped_column(Enum(RepairResult), nullable=True)

    asset: Mapped[Asset] = relationship()
    reported_by: Mapped[User] = relationship(foreign_keys=[reported_by_id])
    resolved_by: Mapped[Optional[User]] = relationship(foreign_keys=[resolved_by_id])
    vendor: Mapped[Optional[Company]] = relationship()


# 同一台设备至多一条未完结的报修。与借还那条约束同理:靠数据库拦,
# 不靠应用层「先查后写」—— 两个人同时报修同一台设备时才不会各建一条。
Index(
    "uq_open_repair_per_asset",
    RepairRecord.asset_id,
    unique=True,
    sqlite_where=RepairRecord.resolved_at.is_(None),
)


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    target_type: Mapped[str] = mapped_column(String(32), default="")
    target_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    __table_args__ = (UniqueConstraint("id"),)
