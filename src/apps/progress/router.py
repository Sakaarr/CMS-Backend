from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.apps.identity.dependencies import get_current_user
from src.apps.identity.models import User
from src.apps.tenancy.models import Tenant
from src.apps.projects.dependencies import get_current_tenant
from src.apps.progress.service import ProgressService
from src.apps.progress.schemas import (
    CreateProgressEntryRequest, UpdateProgressEntryRequest,
    ProgressEntryResponse, ProgressEntrySummary,
    CreateCertificateRequest, UpdateCertificateRequest,
    SubcontractorCertificateResponse, SubcontractorCertificateSummary,
    ProgressDashboard,
)
from src.apps.progress.models import ProgressStatus, CertificateStatus
from src.shared.response import APIResponse, PaginatedResponse, success_response, paginated_response
from src.core.dependencies import require_module

router = APIRouter(tags=["Subcontractor Progress & Certification"])


async def get_svc(
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_module("subcontractors")),
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> ProgressService:
    return ProgressService(db=db, tenant_id=tenant.id, user_id=current_user.id)


# ── Progress Entries ───────────────────────────────────────────

@router.post(
    "/projects/{project_id}/progress",
    response_model=APIResponse[ProgressEntryResponse],
    status_code=201,
)
async def create_progress(
    project_id: str,
    data: CreateProgressEntryRequest,
    svc: ProgressService = Depends(get_svc),
):
    entry = await svc.create_progress(project_id, data)
    return success_response(
        data=ProgressEntryResponse.model_validate(entry),
        message="Progress entry created",
    )


@router.get(
    "/projects/{project_id}/progress",
    response_model=PaginatedResponse[ProgressEntrySummary],
)
async def list_progress(
    project_id: str,
    contract_id: str | None = Query(None),
    boq_item_id: str | None = Query(None),
    status: ProgressStatus | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    svc: ProgressService = Depends(get_svc),
):
    skip = (page - 1) * page_size
    entries, total = await svc.list_progress(
        project_id, contract_id=contract_id, boq_item_id=boq_item_id,
        status=status, skip=skip, limit=page_size,
    )
    return paginated_response(
        data=[ProgressEntrySummary.model_validate(e) for e in entries],
        total=total, page=page, page_size=page_size,
    )


@router.get(
    "/progress/{entry_id}",
    response_model=APIResponse[ProgressEntryResponse],
)
async def get_progress(entry_id: str, svc: ProgressService = Depends(get_svc)):
    entry = await svc.get_progress(entry_id)
    return success_response(data=ProgressEntryResponse.model_validate(entry))


@router.patch(
    "/progress/{entry_id}",
    response_model=APIResponse[ProgressEntryResponse],
)
async def update_progress(
    entry_id: str,
    data: UpdateProgressEntryRequest,
    svc: ProgressService = Depends(get_svc),
):
    entry = await svc.update_progress(entry_id, data)
    return success_response(
        data=ProgressEntryResponse.model_validate(entry),
        message="Progress entry updated",
    )


@router.delete(
    "/progress/{entry_id}",
    response_model=APIResponse[None],
)
async def delete_progress(entry_id: str, svc: ProgressService = Depends(get_svc)):
    await svc.delete_progress(entry_id)
    return success_response(message="Progress entry deleted")


# ── Progress Workflow ─────────────────────────────────────────

@router.post(
    "/progress/{entry_id}/submit",
    response_model=APIResponse[ProgressEntryResponse],
)
async def submit_progress(entry_id: str, svc: ProgressService = Depends(get_svc)):
    entry = await svc.submit_progress(entry_id)
    return success_response(
        data=ProgressEntryResponse.model_validate(entry),
        message="Progress entry submitted for approval",
    )


@router.post(
    "/progress/{entry_id}/approve",
    response_model=APIResponse[ProgressEntryResponse],
)
async def approve_progress(
    entry_id: str,
    rejection_reason: str | None = Query(None),
    svc: ProgressService = Depends(get_svc),
):
    entry = await svc.approve_progress(entry_id, rejection_reason)
    action = "approved" if entry.status == ProgressStatus.APPROVED else "rejected"
    return success_response(
        data=ProgressEntryResponse.model_validate(entry),
        message=f"Progress entry {action}",
    )


# ── BOQ Progress Summary ──────────────────────────────────────

@router.get(
    "/contracts/{contract_id}/progress-summary",
    response_model=APIResponse[list],
)
async def boq_progress_summary(
    contract_id: str,
    svc: ProgressService = Depends(get_svc),
):
    summary = await svc.get_boq_progress_summary(contract_id)
    return success_response(data=summary)


# ── Payment Certificates ──────────────────────────────────────

@router.post(
    "/projects/{project_id}/certificates",
    response_model=APIResponse[SubcontractorCertificateResponse],
    status_code=201,
)
async def create_certificate(
    project_id: str,
    data: CreateCertificateRequest,
    svc: ProgressService = Depends(get_svc),
):
    cert = await svc.create_certificate(project_id, data)
    return success_response(
        data=SubcontractorCertificateResponse.model_validate(cert),
        message="Payment certificate created",
    )


@router.get(
    "/projects/{project_id}/certificates",
    response_model=PaginatedResponse[SubcontractorCertificateSummary],
)
async def list_certificates(
    project_id: str,
    contract_id: str | None = Query(None),
    status: CertificateStatus | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    svc: ProgressService = Depends(get_svc),
):
    skip = (page - 1) * page_size
    certs, total = await svc.list_certificates(
        project_id, contract_id=contract_id, status=status,
        skip=skip, limit=page_size,
    )
    return paginated_response(
        data=[SubcontractorCertificateSummary.model_validate(c) for c in certs],
        total=total, page=page, page_size=page_size,
    )


@router.get(
    "/certificates/{cert_id}",
    response_model=APIResponse[SubcontractorCertificateResponse],
)
async def get_certificate(cert_id: str, svc: ProgressService = Depends(get_svc)):
    cert = await svc.get_certificate(cert_id)
    return success_response(data=SubcontractorCertificateResponse.model_validate(cert))


@router.patch(
    "/certificates/{cert_id}",
    response_model=APIResponse[SubcontractorCertificateResponse],
)
async def update_certificate(
    cert_id: str,
    data: UpdateCertificateRequest,
    svc: ProgressService = Depends(get_svc),
):
    cert = await svc.update_certificate(cert_id, data)
    return success_response(
        data=SubcontractorCertificateResponse.model_validate(cert),
        message="Certificate updated",
    )


@router.delete(
    "/certificates/{cert_id}",
    response_model=APIResponse[None],
)
async def delete_certificate(cert_id: str, svc: ProgressService = Depends(get_svc)):
    await svc.delete_certificate(cert_id)
    return success_response(message="Certificate deleted")


# ── Certificate Workflow ──────────────────────────────────────

@router.post(
    "/certificates/{cert_id}/submit",
    response_model=APIResponse[SubcontractorCertificateResponse],
)
async def submit_certificate(cert_id: str, svc: ProgressService = Depends(get_svc)):
    cert = await svc.submit_certificate(cert_id)
    return success_response(
        data=SubcontractorCertificateResponse.model_validate(cert),
        message="Certificate submitted for approval",
    )


@router.post(
    "/certificates/{cert_id}/approve",
    response_model=APIResponse[SubcontractorCertificateResponse],
)
async def approve_certificate(cert_id: str, svc: ProgressService = Depends(get_svc)):
    cert = await svc.approve_certificate(cert_id)
    return success_response(
        data=SubcontractorCertificateResponse.model_validate(cert),
        message="Certificate approved",
    )


@router.post(
    "/certificates/{cert_id}/pay",
    response_model=APIResponse[SubcontractorCertificateResponse],
)
async def mark_paid(cert_id: str, svc: ProgressService = Depends(get_svc)):
    cert = await svc.mark_paid(cert_id)
    return success_response(
        data=SubcontractorCertificateResponse.model_validate(cert),
        message="Certificate marked as paid",
    )


@router.post(
    "/certificates/{cert_id}/revise",
    response_model=APIResponse[SubcontractorCertificateResponse],
)
async def revise_certificate(cert_id: str, svc: ProgressService = Depends(get_svc)):
    cert = await svc.revise_certificate(cert_id)
    return success_response(
        data=SubcontractorCertificateResponse.model_validate(cert),
        message=f"Revision {cert.revision_number} created",
    )


# ── Dashboard / Summary ───────────────────────────────────────

@router.get(
    "/projects/{project_id}/progress/dashboard",
    response_model=APIResponse[ProgressDashboard],
)
async def progress_dashboard(project_id: str, svc: ProgressService = Depends(get_svc)):
    dashboard = await svc.get_progress_dashboard(project_id)
    return success_response(data=dashboard)


@router.get(
    "/projects/{project_id}/progress/contract-summary",
    response_model=APIResponse[list],
)
async def contract_progress_summary(
    project_id: str,
    svc: ProgressService = Depends(get_svc),
):
    summary = await svc.get_contract_progress_summary(project_id)
    return success_response(
        data=[c.model_dump() for c in summary],
    )
