from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from sqlalchemy import select

from app import schemas
from app.deps import DbDep, OrgDep
from app.imports import ImportError_, parse_po_csv
from app.models import Container, ContainerPurchaseOrder, PurchaseOrder

router = APIRouter(prefix="/api/purchase-orders", tags=["purchase-orders"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


@router.post("/upload", response_model=schemas.ImportResponse)
async def upload_po_csv(db: DbDep, org: OrgDep, file: UploadFile = File(...)) -> schemas.ImportResponse:
    """Legacy one-row-per-PO import.

    Columns: po_number, supplier_name, total_value, container_number, allocation_percentage.

    One transaction. Rows with errors are skipped and reported; zero imported rows is a 422, not a success.
    """
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "File larger than 10 MB")
    try:
        rows, row_errors, columns = parse_po_csv(content)
    except ImportError_ as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"{e.code}: {e.message}") from e

    skipped = [schemas.ImportRowError(row=e.row_no, code=e.code, message=e.message) for e in row_errors]
    if not rows:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            {
                "code": "NO_VALID_ROWS",
                "message": "No row could be imported.",
                "rows_skipped": [s.model_dump() for s in skipped],
            },
        )

    pos_created = containers_created = links_created = 0
    try:
        for row in rows:
            po = db.scalar(
                select(PurchaseOrder).where(
                    PurchaseOrder.org_id == org.id, PurchaseOrder.po_number == row.po_number
                )
            )
            if po is None:
                po = PurchaseOrder(
                    org_id=org.id,
                    po_number=row.po_number,
                    supplier_name=row.supplier_name,
                    total_value=row.total_value,
                )
                db.add(po)
                db.flush()
                pos_created += 1
            else:
                po.supplier_name = row.supplier_name or po.supplier_name
                po.total_value = row.total_value

            if row.container_number is None:
                continue
            container = db.scalar(
                select(Container).where(
                    Container.org_id == org.id, Container.container_number == row.container_number
                )
            )
            if container is None:
                container = Container(org_id=org.id, container_number=row.container_number)
                db.add(container)
                db.flush()
                containers_created += 1
            link = db.get(ContainerPurchaseOrder, (container.id, po.id))
            if link is None:
                db.add(
                    ContainerPurchaseOrder(
                        container_id=container.id,
                        po_id=po.id,
                        allocation_percentage=row.allocation_percentage,
                    )
                )
                links_created += 1
            else:
                link.allocation_percentage = row.allocation_percentage
        db.commit()
    except Exception:
        db.rollback()
        raise

    return schemas.ImportResponse(
        status="success",
        rows_processed=len(rows),
        rows_skipped=skipped,
        purchase_orders_created=pos_created,
        containers_created=containers_created,
        containers_linked=links_created,
        detected_columns=columns,
    )
