"""设备分类。对应 PRD 3.1 / 3.2。"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import active_user, admin_user
from ..models import Asset, Category, User
from ..schemas import CategoryCreate, CategoryOut, CategoryUpdate
from ..services import log

router = APIRouter(prefix="/api/categories", tags=["分类"])


@router.get("", response_model=List[CategoryOut])
def list_categories(db: Session = Depends(get_db), _: User = Depends(active_user)):
    rows = db.execute(select(Category).order_by(Category.name)).scalars().all()
    return [CategoryOut.model_validate(c) for c in rows]


@router.post("", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(
    payload: CategoryCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_user),
):
    category = Category(name=payload.name, tag_prefix=payload.tag_prefix.upper())
    db.add(category)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="分类名称或编号前缀已存在"
        )
    log(db, admin.id, "category_create", "category", category.id, category.name)
    db.commit()
    return CategoryOut.model_validate(category)


@router.put("/{category_id}", response_model=CategoryOut)
def update_category(
    category_id: int,
    payload: CategoryUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_user),
):
    """只允许改名称。

    PRD 3.2:tag_prefix 不可修改 —— 改了会让同一分类下新旧设备的编号规则不一致,
    而已生成的编号又永不变更(标签已贴在实物上)。
    """
    category = db.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分类不存在")
    if payload.name is not None:
        category.name = payload.name
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="分类名称已存在")
    log(db, admin.id, "category_update", "category", category.id, category.name)
    db.commit()
    return CategoryOut.model_validate(category)


@router.delete("/{category_id}")
def delete_category(
    category_id: int, db: Session = Depends(get_db), admin: User = Depends(admin_user)
):
    category = db.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分类不存在")
    in_use = db.execute(
        select(func.count())
        .select_from(Asset)
        .where(Asset.category_id == category_id, Asset.deleted_at.is_(None))
    ).scalar_one()
    if in_use:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"该分类下还有 {in_use} 台设备,不可删除"
        )
    log(db, admin.id, "category_delete", "category", category.id, category.name)
    db.delete(category)
    db.commit()
    return {"ok": True}
