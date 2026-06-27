from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.apps.identity.dependencies import get_current_user
from src.apps.identity.models import User
from src.apps.tenancy.models import Tenant
from src.apps.projects.dependencies import get_current_tenant
from src.apps.compliance.service import ComplianceService
from src.apps.compliance.schemas import (
    CreateComplianceDocRequest, UpdateComplianceDocRequest,
    ComplianceDocResponse, ComplianceDocSummary,
)
from src.apps.compliance.models import ComplianceDocCategory, ComplianceDocStatus
from src.shared.response import APIResponse, PaginatedResponse, success_response, paginated_response
from src.core.dependencies import require_module

router = APIRouter(tags=["Subcontractor Compliance"])


async def get_svc(
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_module("subcontractors")),
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> ComplianceService:
    return ComplianceService(db=db, tenant_id=tenant.id, user_id=current_user.id)


@router.post(
    "/projects/{project_id}/compliance-docs",
    response_model=APIResponse[ComplianceDocResponse],
    status_code=201,
)
async def create_compliance_doc(
    project_id: str,
    data: CreateComplianceDocRequest,
    svc: ComplianceService = Depends(get_svc),
):
    doc = await svc.create_doc(project_id, data)
    return success_response(
        data=ComplianceDocResponse.model_validate(doc),
        message="Compliance document created",
    )


@router.get(
    "/projects/{project_id}/compliance-docs",
    response_model=PaginatedResponse[ComplianceDocSummary],
)
async def list_compliance_docs(
    project_id: str,
    subcontractor_id: str | None = Query(None),
    category: ComplianceDocCategory | None = Query(None),
    status: ComplianceDocStatus | None = Query(None),
    expiring_within_days: int | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    svc: ComplianceService = Depends(get_svc),
):
    skip = (page - 1) * page_size
    docs, total = await svc.list_docs(
        project_id,
        subcontractor_id=subcontractor_id,
        category=category,
        status=status,
        expiring_within_days=expiring_within_days,
        skip=skip, limit=page_size,
    )
    return paginated_response(
        data=[ComplianceDocSummary.model_validate(d) for d in docs],
        total=total, page=page, page_size=page_size,
    )


@router.get(
    "/compliance-docs/{doc_id}",
    response_model=APIResponse[ComplianceDocResponse],
)
async def get_compliance_doc(doc_id: str, svc: ComplianceService = Depends(get_svc)):
    doc = await svc.get_doc(doc_id)
    return success_response(data=ComplianceDocResponse.model_validate(doc))


@router.patch(
    "/compliance-docs/{doc_id}",
    response_model=APIResponse[ComplianceDocResponse],
)
async def update_compliance_doc(
    doc_id: str,
    data: UpdateComplianceDocRequest,
    svc: ComplianceService = Depends(get_svc),
):
    doc = await svc.update_doc(doc_id, data)
    return success_response(
        data=ComplianceDocResponse.model_validate(doc),
        message="Compliance document updated",
    )


@router.delete(
    "/compliance-docs/{doc_id}",
    response_model=APIResponse[None],
)
async def delete_compliance_doc(doc_id: str, svc: ComplianceService = Depends(get_svc)):
    await svc.delete_doc(doc_id)
    return success_response(message="Compliance document deleted")


@router.post(
    "/compliance-docs/{doc_id}/verify",
    response_model=APIResponse[ComplianceDocResponse],
)
async def verify_compliance_doc(doc_id: str, svc: ComplianceService = Depends(get_svc)):
    doc = await svc.verify_doc(doc_id)
    return success_response(
        data=ComplianceDocResponse.model_validate(doc),
        message="Compliance document verified",
    )


@router.post(
    "/projects/{project_id}/compliance-docs/refresh-expiry",
    response_model=APIResponse[dict],
)
async def refresh_expiry_statuses(
    project_id: str,
    svc: ComplianceService = Depends(get_svc),
):
    count = await svc.refresh_expiry_statuses(project_id)
    return success_response(
        data={"updated": count},
        message=f"{count} documents updated",
    )


@router.get(
    "/projects/{project_id}/compliance-docs/expiring",
    response_model=APIResponse[list],
)
async def get_expiring_docs(
    project_id: str,
    within_days: int = Query(30, ge=1, le=365),
    svc: ComplianceService = Depends(get_svc),
):
    docs = await svc.get_expiring_docs(project_id, within_days)
    return success_response(
        data=[ComplianceDocSummary.model_validate(d) for d in docs],
    )


@router.post(
    "/projects/{project_id}/compliance-docs/notify-expiring",
    response_model=APIResponse[dict],
)
async def notify_expiring_docs(
    project_id: str,
    within_days: int = Query(30, ge=1, le=365),
    svc: ComplianceService = Depends(get_svc),
):
    count = await svc.notify_expiring_docs(project_id, within_days)
    return success_response(
        data={"notified": count},
        message=f"Expiry notifications sent for {count} document(s)",
    )
