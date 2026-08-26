"""迁移必须和模型对得上。

这是整套测试里唯一一个会真正执行 Alembic 的用例,存在的意义只有一个:
**改了 models.py 却忘了生成迁移,在这里挂掉,而不是等到线上升级时才发现。**

其余用例走 create_all(conftest 里设了 SNIPE_RUN_MIGRATIONS=0),每个用例重建
一次库,跑迁移纯属浪费。
"""
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from app.config import BASE_DIR
from app.models import Base

# 忽略这些差异:SQLite 会为部分索引和约束生成一些 Alembic 认不出来的东西
IGNORED_PREFIXES = ()


@pytest.fixture
def migrated_db():
    """在一个全新的空库上跑完全部迁移,返回它的 engine。"""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "migrated.db"
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=BASE_DIR,
            env={
                **_clean_env(),
                "SNIPE_DB_PATH": str(db_path),
                "SNIPE_SECRET_KEY": "test-secret",
                "SNIPE_INITIAL_ADMIN_PASSWORD": "admin12345",
            },
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"alembic upgrade 失败:\n{result.stderr}"
        engine = create_engine(f"sqlite:///{db_path}")
        try:
            yield engine
        finally:
            engine.dispose()


def _clean_env():
    import os

    # conftest 把 SNIPE_DB_PATH 指到了测试库,子进程不能继承,否则会迁移错库
    return {k: v for k, v in os.environ.items() if not k.startswith("SNIPE_")}


def test_migrations_produce_the_schema_the_models_describe(migrated_db):
    """跑完迁移的库,结构应当与 models.py 完全一致。

    有差异就说明改了模型没生成迁移。修法:
        cd backend && ./.venv/Scripts/python.exe -m alembic revision --autogenerate -m "说明"
    """
    with migrated_db.connect() as conn:
        context = MigrationContext.configure(conn, opts={"compare_type": True})
        diff = compare_metadata(context, Base.metadata)

    # alembic_version 是 Alembic 自己的表,不在模型里,属于预期差异
    diff = [d for d in diff if "alembic_version" not in str(d)]

    assert diff == [], (
        "迁移与模型不一致,多半是改了 models.py 没生成迁移。差异:\n"
        + "\n".join(f"  {d}" for d in diff)
    )


def test_every_table_the_models_define_actually_exists(migrated_db):
    tables = set(inspect(migrated_db).get_table_names())
    expected = set(Base.metadata.tables)
    missing = expected - tables
    assert not missing, f"迁移没建出这些表:{missing}"


def test_the_concurrency_guard_survives_migration(migrated_db):
    """借还并发靠这个部分唯一索引兜底,迁移里丢了 WHERE 条件后果很严重。

    少了 `WHERE checked_in_at IS NULL`,索引就变成「同一台设备只能有一条借还
    记录」—— 借出、归还、再借出会在第二次借出时报冲突。
    """
    with migrated_db.connect() as conn:
        sql = conn.exec_driver_sql(
            "SELECT sql FROM sqlite_master "
            "WHERE type='index' AND name='uq_active_checkout_per_asset'"
        ).scalar_one()

    assert "UNIQUE" in sql.upper()
    assert "checked_in_at IS NULL" in sql, f"部分索引的 WHERE 条件丢了:{sql}"
