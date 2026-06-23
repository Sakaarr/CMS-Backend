from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.apps.identity.dependencies import get_current_user
from src.apps.identity.models import User
from src.apps.tenancy.models import Tenant
from src.apps.projects.dependencies import get_current_tenant
from src.apps.reports.service import ReportService
from src.core.dependencies import require_module

router = APIRouter(tags=["Reports"])


async def get_svc(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> ReportService:
    return ReportService(db=db, tenant=tenant)


@router.get("/invoices/{invoice_id}/pdf")
async def download_invoice_pdf(
    invoice_id: str,
    _: User = Depends(require_module("finance")),
    svc: ReportService = Depends(get_svc),
):
    pdf = await svc.invoice_pdf(invoice_id)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="invoice-{invoice_id[:8]}.pdf"'},
    )


@router.get("/purchase-orders/{po_id}/pdf")
async def download_po_pdf(
    po_id: str,
    _: User = Depends(require_module("procurement")),
    svc: ReportService = Depends(get_svc),
):
    pdf = await svc.po_pdf(po_id)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="po-{po_id[:8]}.pdf"'},
    )


@router.get("/projects/{project_id}/budget-versions/{version_id}/pdf")
async def download_boq_pdf(
    project_id: str,
    version_id: str,
    _: User = Depends(require_module("boq")),
    svc: ReportService = Depends(get_svc),
):
    pdf = await svc.boq_pdf(version_id, project_id)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="boq-{version_id[:8]}.pdf"'},
    )


@router.get("/projects/{project_id}/budget-versions/{version_id}/xlsx")
async def download_boq_excel(
    project_id: str,
    version_id: str,
    _: User = Depends(require_module("boq")),
    svc: ReportService = Depends(get_svc),
):
    xlsx = await svc.boq_excel(version_id, project_id)
    return Response(
        content=xlsx,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="boq-{version_id[:8]}.xlsx"'},
    )
