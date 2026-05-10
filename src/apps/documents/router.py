from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.apps.identity.dependencies import get_current_user
from src.apps.identity.models import User
from src.apps.tenancy.models import Tenant
from src.apps.projects.dependencies import get_current_tenant
from src.apps.documents.service import DocumentService
from src.apps.documents.models import DocumentCategory, DocumentStatus
from src.apps.documents.schemas import (
    CreateDocumentRequest, UpdateDocumentRequest,
    DocumentResponse, DocumentSummary,
    AddRevisionRequest, ApprovalActionRequest, AddApproverRequest,
    DocumentApprovalResponse,
)
from src.shared.response import APIResponse, PaginatedResponse, success_response, paginated_response

router = APIRouter(tags=["Documents"])


async def get_svc(
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> DocumentService:
    return DocumentService(db=db, tenant_id=tenant.id, user_id=current_user.id)


@router.post("/projects/{project_id}/documents",
    response_model=APIResponse[DocumentResponse], status_code=201)
async def upload_document(
    project_id: str, data: CreateDocumentRequest,
    svc: DocumentService = Depends(get_svc),
):
    doc = await svc.create_document(project_id, data)
    return success_response(data=DocumentResponse.model_validate(doc), message="Document uploaded")


@router.get("/projects/{project_id}/documents",
    response_model=PaginatedResponse[DocumentSummary])
async def list_documents(
    project_id: str,
    category: DocumentCategory | None = Query(None),
    status: DocumentStatus | None = Query(None),
    search: str | None = Query(None),
    discipline: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    svc: DocumentService = Depends(get_svc),
):
    skip = (page - 1) * page_size
    docs, total = await svc.list_documents(
        project_id, category=category, status=status,
        search=search, discipline=discipline,
        skip=skip, limit=page_size,
    )
    return paginated_response(
        data=[DocumentSummary.model_validate(d) for d in docs],
        total=total, page=page, page_size=page_size,
    )


@router.get("/documents/{document_id}", response_model=APIResponse[DocumentResponse])
async def get_document(document_id: str, svc: DocumentService = Depends(get_svc)):
    doc = await svc.get_document(document_id)
    return success_response(data=DocumentResponse.model_validate(doc))


@router.patch("/documents/{document_id}", response_model=APIResponse[DocumentResponse])
async def update_document(
    document_id: str, data: UpdateDocumentRequest,
    svc: DocumentService = Depends(get_svc),
):
    doc = await svc.update_document(document_id, data)
    return success_response(data=DocumentResponse.model_validate(doc))


@router.post("/documents/{document_id}/submit", response_model=APIResponse[DocumentResponse])
async def submit_for_review(document_id: str, svc: DocumentService = Depends(get_svc)):
    doc = await svc.submit_for_review(document_id)
    return success_response(data=DocumentResponse.model_validate(doc), message="Submitted for review")


@router.post("/documents/{document_id}/revisions", response_model=APIResponse[DocumentResponse])
async def add_revision(
    document_id: str, data: AddRevisionRequest,
    svc: DocumentService = Depends(get_svc),
):
    doc = await svc.add_revision(document_id, data)
    return success_response(data=DocumentResponse.model_validate(doc), message="Revision added")


@router.delete("/documents/{document_id}", response_model=APIResponse[None])
async def delete_document(document_id: str, svc: DocumentService = Depends(get_svc)):
    await svc.delete_document(document_id)
    return success_response(message="Document deleted")


@router.post("/documents/{document_id}/approvers",
    response_model=APIResponse[DocumentApprovalResponse], status_code=201)
async def add_approver(
    document_id: str, data: AddApproverRequest,
    svc: DocumentService = Depends(get_svc),
):
    approval = await svc.add_approver(document_id, data)
    return success_response(data=DocumentApprovalResponse.model_validate(approval))


@router.patch("/documents/{document_id}/approvals/{approval_id}",
    response_model=APIResponse[DocumentApprovalResponse])
async def action_approval(
    document_id: str, approval_id: str,
    data: ApprovalActionRequest,
    svc: DocumentService = Depends(get_svc),
):
    approval = await svc.action_approval(document_id, approval_id, data)
    return success_response(data=DocumentApprovalResponse.model_validate(approval))


@router.get("/projects/{project_id}/document-summary", response_model=APIResponse[dict])
async def document_summary(project_id: str, svc: DocumentService = Depends(get_svc)):
    summary = await svc.get_document_summary(project_id)
    return success_response(data=summary)