import pytest
from datetime import date
from httpx import AsyncClient
from sqlalchemy import select

from src.apps.documents.models import (
    ApprovalStatus,
    Document,
    DocumentApproval,
    DocumentCategory,
    DocumentStatus,
)
from src.apps.finance.models import Invoice, InvoiceStatus, InvoiceType
from src.apps.identity.models import OrganizationMember, User, UserPermission, UserRole
from src.apps.projects.models import Project, ProjectType

BASE_AUTH = "/api/v1/auth"
BASE = "/api/v1/approvals/inbox"
TENANT_SLUG = "approval-inbox-co"


async def _get_token(client: AsyncClient, email: str, password: str) -> str:
    response = await client.post(
        f"{BASE_AUTH}/login",
        json={"email": email, "password": password},
    )
    return response.json()["data"]["access_token"]


@pytest.mark.asyncio
async def test_approvals_inbox_combines_modules_and_filters_document_approvals(
    client: AsyncClient,
    db,
):
    await client.post(
        f"{BASE_AUTH}/register",
        json={
            "email": "approver@example.com",
            "password": "Test@1234",
            "full_name": "Approval User",
        },
    )

    admin_token = await _get_token(client, "admin@cms.com", "Admin@123456")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    tenant_response = await client.post(
        "/api/v1/tenants",
        json={
            "name": "Approval Inbox Co",
            "slug": TENANT_SLUG,
            "email": "info@approval-inbox.example",
            "admin_full_name": "Tenant Admin",
            "admin_email": "tenant-admin@example.com",
        },
        headers=admin_headers,
    )
    assert tenant_response.status_code == 201
    tenant_id = tenant_response.json()["data"]["id"]

    user_result = await db.execute(
        select(User).where(User.email == "approver@example.com")
    )
    approver = user_result.scalar_one()

    db.add(
        OrganizationMember(
            user_id=approver.id,
            tenant_id=tenant_id,
            role=UserRole.PROJECT_MANAGER,
            is_owner=False,
        )
    )
    db.add(
        UserPermission(
            user_id=approver.id,
            tenant_id=tenant_id,
            can_projects=True,
            can_boq=False,
            can_procurement=False,
            can_inventory=False,
            can_site_ops=False,
            can_finance=True,
            can_quality=False,
            can_documents=True,
        )
    )

    project = Project(
        tenant_id=tenant_id,
        created_by=approver.id,
        name="Approvals Project",
        code="APR-001",
        project_type=ProjectType.COMMERCIAL,
        currency="NPR",
    )
    db.add(project)
    await db.flush()

    invoice = Invoice(
        tenant_id=tenant_id,
        created_by=approver.id,
        project_id=project.id,
        invoice_number="INV-001",
        invoice_type=InvoiceType.CLIENT,
        status=InvoiceStatus.SUBMITTED,
        invoice_date=date(2026, 6, 1),
        subtotal=1000,
        discount_amount=0,
        taxable_amount=1000,
        vat_rate=13,
        vat_amount=130,
        retention_rate=0,
        retention_amount=0,
        grand_total=1130,
        paid_amount=0,
        balance_due=1130,
        currency="NPR",
    )
    db.add(invoice)

    document = Document(
        tenant_id=tenant_id,
        created_by=approver.id,
        project_id=project.id,
        document_number="DOC-001",
        title="Foundation Drawing",
        category=DocumentCategory.DRAWING,
        status=DocumentStatus.UNDER_REVIEW,
        file_name="foundation-drawing.pdf",
        file_url="https://example.com/foundation-drawing.pdf",
        version="1.0",
    )
    db.add(document)
    await db.flush()

    db.add(
        DocumentApproval(
            tenant_id=tenant_id,
            created_by=approver.id,
            document_id=document.id,
            approver_id=approver.id,
            approver_name=approver.full_name,
            status=ApprovalStatus.PENDING,
            sequence=1,
        )
    )
    db.add(
        DocumentApproval(
            tenant_id=tenant_id,
            created_by=approver.id,
            document_id=document.id,
            approver_id="someone-else",
            approver_name="Someone Else",
            status=ApprovalStatus.PENDING,
            sequence=2,
        )
    )
    await db.flush()

    approver_token = await _get_token(client, "approver@example.com", "Test@1234")
    headers = {
        "Authorization": f"Bearer {approver_token}",
        "X-Tenant-Slug": TENANT_SLUG,
    }

    response = await client.get(BASE, headers=headers)
    assert response.status_code == 200
    payload = response.json()["data"]

    assert payload["total"] == 2
    assert payload["counts"]["finance"] == 1
    assert payload["counts"]["documents"] == 1

    modules = {item["module"] for item in payload["items"]}
    assert modules == {"finance", "documents"}

    document_items = [item for item in payload["items"] if item["module"] == "documents"]
    assert len(document_items) == 1
    assert document_items[0]["meta"]["approver_name"] == "Approval User"
    assert document_items[0]["meta"]["document_number"] == "DOC-001"

