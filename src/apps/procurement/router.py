from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.apps.identity.dependencies import get_current_user
from src.apps.identity.models import User
from src.apps.tenancy.models import Tenant
from src.apps.projects.dependencies import get_current_tenant
from src.apps.procurement.service import ProcurementService
from src.apps.procurement.schemas import (
    CreateVendorRequest, UpdateVendorRequest, VendorResponse,
    CreateRFQRequest, RFQResponse,
    CreateQuotationRequest, QuotationResponse,
    CreatePORequest, POResponse,
    CreateGRNRequest, GRNResponse,
)
from src.shared.response import APIResponse, success_response

router = APIRouter(tags=["Procurement"])


async def get_svc(
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> ProcurementService:
    return ProcurementService(db=db, tenant_id=tenant.id, user_id=current_user.id)


# ── Vendors ───────────────────────────────────────────────────────

@router.post("/vendors", response_model=APIResponse[VendorResponse], status_code=201)
async def create_vendor(data: CreateVendorRequest, svc: ProcurementService = Depends(get_svc)):
    v = await svc.create_vendor(data)
    return success_response(data=VendorResponse.model_validate(v), message="Vendor created")


@router.get("/vendors", response_model=APIResponse[list[VendorResponse]])
async def list_vendors(search: str | None = Query(None), svc: ProcurementService = Depends(get_svc)):
    vendors = await svc.list_vendors(search=search)
    return success_response(data=[VendorResponse.model_validate(v) for v in vendors])


@router.get("/vendors/{vendor_id}", response_model=APIResponse[VendorResponse])
async def get_vendor(vendor_id: str, svc: ProcurementService = Depends(get_svc)):
    v = await svc.get_vendor(vendor_id)
    return success_response(data=VendorResponse.model_validate(v))


@router.patch("/vendors/{vendor_id}", response_model=APIResponse[VendorResponse])
async def update_vendor(vendor_id: str, data: UpdateVendorRequest, svc: ProcurementService = Depends(get_svc)):
    v = await svc.update_vendor(vendor_id, data)
    return success_response(data=VendorResponse.model_validate(v))


# ── RFQ ───────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/rfqs", response_model=APIResponse[RFQResponse], status_code=201)
async def create_rfq(project_id: str, data: CreateRFQRequest, svc: ProcurementService = Depends(get_svc)):
    rfq = await svc.create_rfq(project_id, data)
    return success_response(data=RFQResponse.model_validate(rfq), message="RFQ created")


@router.get("/projects/{project_id}/rfqs", response_model=APIResponse[list[RFQResponse]])
async def list_rfqs(project_id: str, svc: ProcurementService = Depends(get_svc)):
    rfqs = await svc.list_rfqs(project_id)
    return success_response(data=[RFQResponse.model_validate(r) for r in rfqs])


@router.post("/rfqs/{rfq_id}/send", response_model=APIResponse[RFQResponse])
async def send_rfq(rfq_id: str, svc: ProcurementService = Depends(get_svc)):
    rfq = await svc.send_rfq(rfq_id)
    return success_response(data=RFQResponse.model_validate(rfq), message="RFQ sent to vendors")


# ── Quotations ────────────────────────────────────────────────────

@router.post("/quotations", response_model=APIResponse[QuotationResponse], status_code=201)
async def create_quotation(data: CreateQuotationRequest, svc: ProcurementService = Depends(get_svc)):
    q = await svc.create_quotation(data)
    return success_response(data=QuotationResponse.model_validate(q), message="Quotation recorded")


@router.get("/rfqs/{rfq_id}/quotations", response_model=APIResponse[list[QuotationResponse]])
async def list_quotations(rfq_id: str, svc: ProcurementService = Depends(get_svc)):
    qs = await svc.list_quotations(rfq_id)
    return success_response(data=[QuotationResponse.model_validate(q) for q in qs])


@router.post("/quotations/{quotation_id}/accept", response_model=APIResponse[QuotationResponse])
async def accept_quotation(quotation_id: str, svc: ProcurementService = Depends(get_svc)):
    q = await svc.accept_quotation(quotation_id)
    return success_response(data=QuotationResponse.model_validate(q), message="Quotation accepted")


# ── Purchase Orders ───────────────────────────────────────────────

@router.post("/projects/{project_id}/purchase-orders", response_model=APIResponse[POResponse], status_code=201)
async def create_po(project_id: str, data: CreatePORequest, svc: ProcurementService = Depends(get_svc)):
    po = await svc.create_po(project_id, data)
    return success_response(data=POResponse.model_validate(po), message="Purchase order created")


@router.get("/projects/{project_id}/purchase-orders", response_model=APIResponse[list[POResponse]])
async def list_pos(project_id: str, svc: ProcurementService = Depends(get_svc)):
    pos = await svc.list_pos(project_id)
    return success_response(data=[POResponse.model_validate(p) for p in pos])


@router.get("/purchase-orders/{po_id}", response_model=APIResponse[POResponse])
async def get_po(po_id: str, svc: ProcurementService = Depends(get_svc)):
    po = await svc.get_po(po_id)
    return success_response(data=POResponse.model_validate(po))


@router.post("/purchase-orders/{po_id}/submit", response_model=APIResponse[POResponse])
async def submit_po(po_id: str, svc: ProcurementService = Depends(get_svc)):
    po = await svc.submit_po(po_id)
    return success_response(data=POResponse.model_validate(po), message="PO submitted for approval")


@router.post("/purchase-orders/{po_id}/approve", response_model=APIResponse[POResponse])
async def approve_po(po_id: str, svc: ProcurementService = Depends(get_svc)):
    po = await svc.approve_po(po_id)
    return success_response(data=POResponse.model_validate(po), message="PO approved")


@router.get("/projects/{project_id}/procurement-stats", response_model=APIResponse[dict])
async def procurement_stats(project_id: str, svc: ProcurementService = Depends(get_svc)):
    stats = await svc.get_procurement_stats(project_id)
    return success_response(data=stats)


# ── GRN ───────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/grns", response_model=APIResponse[GRNResponse], status_code=201)
async def create_grn(project_id: str, data: CreateGRNRequest, svc: ProcurementService = Depends(get_svc)):
    grn = await svc.create_grn(project_id, data)
    return success_response(data=GRNResponse.model_validate(grn), message="GRN created")


@router.get("/projects/{project_id}/grns", response_model=APIResponse[list[GRNResponse]])
async def list_grns(project_id: str, svc: ProcurementService = Depends(get_svc)):
    grns = await svc.list_grns(project_id)
    return success_response(data=[GRNResponse.model_validate(g) for g in grns])


@router.post("/grns/{grn_id}/confirm", response_model=APIResponse[GRNResponse])
async def confirm_grn(grn_id: str, svc: ProcurementService = Depends(get_svc)):
    grn = await svc.confirm_grn(grn_id)
    return success_response(data=GRNResponse.model_validate(grn), message="GRN confirmed")