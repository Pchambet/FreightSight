from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, UploadFile, status
from sqlalchemy import select

from app.api.v1 import schemas
from app.api.v1.deps import WriterDep
from app.core.errors import Unprocessable
from app.core.tenancy import TenantDep, TenantSession
from app.domain.imports import service
from app.domain.models import ErpSyncRun, ImportJob, ImportKind

router = APIRouter(prefix="/imports", tags=["imports"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def _responses(t: TenantSession, jobs: list[ImportJob]) -> list[schemas.ImportJobResponse]:
    """Where each import came from. An ERP sync writes a file too, and without this the imports
    list shows the nightly Odoo sync as "odoo-sync.csv", as if someone had dropped it by hand.

    The sync run that drove the job is the record of it, so nothing has to be stored on the job.
    """
    if not jobs:
        return []
    synced = set(
        t.db.scalars(
            select(ErpSyncRun.import_job_id)
            .where(ErpSyncRun.org_id == t.org_id)
            .where(ErpSyncRun.import_job_id.in_([j.id for j in jobs]))
        )
    )
    return [
        schemas.ImportJobResponse.model_validate(job).model_copy(
            update={"source": "erp_sync" if job.id in synced else "upload"}
        )
        for job in jobs
    ]


@router.get("", response_model=list[schemas.ImportJobResponse])
def list_imports(t: TenantDep) -> list[schemas.ImportJobResponse]:
    jobs = list(t.db.scalars(t.q(ImportJob).order_by(ImportJob.created_at.desc()).limit(100)))
    return _responses(t, jobs)


@router.post("", response_model=schemas.ImportJobResponse, status_code=status.HTTP_201_CREATED)
async def create_import(
    t: TenantDep,
    _: WriterDep,
    kind: Annotated[ImportKind, Form()] = ImportKind.PURCHASE_ORDERS,
    file: UploadFile = File(...),
) -> ImportJob:
    """Upload a CSV/XLSX. Returns detected columns and a suggested (or remembered) mapping.

    Nothing is written yet.
    """
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise Unprocessable("File larger than 10 MB", code="FILE_TOO_LARGE")
    if not content.strip():
        raise Unprocessable("File is empty", code="EMPTY_FILE")
    job = service.create_job(t, kind, content, file.filename)
    t.db.commit()
    t.db.refresh(job)
    return job


@router.get("/{import_id}", response_model=schemas.ImportJobResponse)
def get_import(import_id: UUID, t: TenantDep) -> schemas.ImportJobResponse:
    return _responses(t, [t.get_or_404(ImportJob, import_id, "Import")])[0]


@router.post("/{import_id}/validate", response_model=schemas.ImportJobResponse)
def validate_import(
    import_id: UUID, payload: schemas.ImportValidateRequest, t: TenantDep, _: WriterDep
) -> ImportJob:
    """Dry run: the commit code path under a SAVEPOINT that is rolled back.

    The report is exactly what commit would do.
    """
    job = t.get_or_404(ImportJob, import_id, "Import")
    service.ensure_not_done(job)
    try:
        service.run_job(t, job, payload.mapping, dry_run=True)
    except Unprocessable as e:
        job.mapping = payload.mapping
        job.report = {"error": e.message, "code": e.code, **e.extra}
        t.db.commit()
        raise
    t.db.commit()
    t.db.refresh(job)
    return job


@router.post("/{import_id}/commit", response_model=schemas.ImportJobResponse)
def commit_import(
    import_id: UUID, payload: schemas.ImportCommitRequest, t: TenantDep, _: WriterDep
) -> ImportJob:
    job = t.get_or_404(ImportJob, import_id, "Import")
    service.ensure_not_done(job)
    mapping = payload.mapping or dict(job.mapping)
    service.run_job(t, job, mapping, dry_run=False, on_error=payload.on_error)
    t.db.commit()
    t.db.refresh(job)
    return job
