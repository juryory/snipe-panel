"""Excel 批量导入 / 导出。对应 PRD 3.1。

导入分两步:先 preview 看判定结果,确认无误再 commit。几百台设备盲导进去,
出了错谁也说不清哪些进了哪些没进。
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..db import get_db
from ..deps import active_user, admin_user
from ..importer import build_template, export_workbook, parse, validate
from ..models import Asset, AssetStatus, Company, User
from ..schemas import ImportPreview, ImportRowOut
from ..services import create_asset_with_tag, log, open_checkouts_for

router = APIRouter(prefix="/api/assets", tags=["导入导出"])

XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_UPLOAD = 5 * 1024 * 1024  # 5MB,几千行的表也远用不到
MAX_ROWS = 2000


def _attachment(name: str) -> dict:
    # 中文文件名要用 RFC 5987 编码,否则部分浏览器会存成乱码
    from urllib.parse import quote

    return {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"}


@router.get("/import/template")
def download_template(_: User = Depends(admin_user)):
    return Response(
        content=build_template(),
        media_type=XLSX_MEDIA,
        headers=_attachment("设备导入模板.xlsx"),
    )


async def _read_and_check(db: Session, file: UploadFile, create_missing_companies: bool):
    content = await file.read()
    if len(content) > MAX_UPLOAD:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="文件太大,请控制在 5MB 以内"
        )
    rows, fatal = parse(content)
    if fatal:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=fatal[0])
    if not rows:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="表格里没有数据行")
    if len(rows) > MAX_ROWS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"一次最多导入 {MAX_ROWS} 行,当前 {len(rows)} 行,请分批",
        )
    return validate(db, rows, create_missing_companies)


def _to_preview(results, committed: bool) -> ImportPreview:
    rows = [
        ImportRowOut(
            row=r["row"],
            name=str(r["data"].get("name") or ""),
            asset_tag=r["data"].get("asset_tag"),
            category=(r["data"]["category"].name if r["data"].get("category") else ""),
            ok=not r["errors"],
            errors=r["errors"],
            warnings=r["warnings"],
        )
        for r in results
    ]
    error_count = sum(1 for r in rows if not r.ok)
    return ImportPreview(
        total=len(rows),
        ok_count=len(rows) - error_count,
        error_count=error_count,
        committed=committed,
        rows=rows,
    )


@router.post("/import/preview", response_model=ImportPreview)
async def preview_import(
    file: UploadFile = File(...),
    create_missing_companies: bool = Form(False),
    db: Session = Depends(get_db),
    _: User = Depends(admin_user),
):
    """预演:只判定不写库。"""
    results = await _read_and_check(db, file, create_missing_companies)
    return _to_preview(results, committed=False)


@router.post("/import", response_model=ImportPreview)
async def commit_import(
    file: UploadFile = File(...),
    create_missing_companies: bool = Form(False),
    db: Session = Depends(get_db),
    admin: User = Depends(admin_user),
):
    """真正导入。只要有一行报错就整批拒绝。

    部分导入会让人搞不清到底进了哪些、还差哪些,补录时更容易出乱子 ——
    宁可让人改完表格重传一次。
    """
    results = await _read_and_check(db, file, create_missing_companies)
    preview = _to_preview(results, committed=False)
    if preview.error_count:
        preview.committed = False
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"有 {preview.error_count} 行有问题,已全部取消。请修正后重新上传",
        )

    new_companies: dict = {}
    created = 0
    for r in results:
        data = r["data"]
        company = data.get("company")
        wanted = data.get("new_company")
        if company is None and wanted:
            company = new_companies.get(wanted)
            if company is None:
                company = Company(name=wanted)
                db.add(company)
                db.flush()
                new_companies[wanted] = company

        asset = create_asset_with_tag(
            db,
            data["category"],
            data.get("asset_tag"),
            name=data["name"],
            brand=data["brand"],
            model=data["model"],
            serial_no=data["serial_no"],
            status=data["status"],
            location=data["location"],
            owner_user_id=data["owner"].id if data.get("owner") else None,
            company_id=company.id if company else None,
            purchased_at=data.get("purchased_at"),
            note=data["note"],
        )
        r["data"]["asset_tag"] = asset.asset_tag
        created += 1

    log(db, admin.id, "asset_import", "asset", None,
        f"导入 {created} 台" + (f",新建采购公司 {len(new_companies)} 家" if new_companies else ""))
    db.commit()

    final = _to_preview(results, committed=True)
    return final


@router.get("/export")
def export_assets(
    q: Optional[str] = None,
    category_id: Optional[int] = None,
    company_id: Optional[int] = None,
    status_: Optional[AssetStatus] = Query(None, alias="status"),
    db: Session = Depends(get_db),
    _: User = Depends(active_user),
):
    """导出台账为 xlsx。表头与导入模板一致,可以改完再导回来。"""
    from sqlalchemy import or_

    stmt = (
        select(Asset)
        .where(Asset.deleted_at.is_(None))
        .options(
            joinedload(Asset.category), joinedload(Asset.owner), joinedload(Asset.company)
        )
    )
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(Asset.asset_tag.ilike(like), Asset.name.ilike(like), Asset.serial_no.ilike(like))
        )
    if category_id is not None:
        stmt = stmt.where(Asset.category_id == category_id)
    if company_id is not None:
        stmt = stmt.where(Asset.company_id == company_id)
    if status_ is not None:
        stmt = stmt.where(Asset.status == status_)

    rows: List[Asset] = (
        db.execute(stmt.order_by(Asset.asset_tag)).unique().scalars().all()
    )
    open_map = open_checkouts_for(db, [a.id for a in rows])
    return Response(
        content=export_workbook(rows, open_map),
        media_type=XLSX_MEDIA,
        headers=_attachment("设备台账.xlsx"),
    )
