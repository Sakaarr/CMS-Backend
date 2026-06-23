from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.apps.identity.dependencies import get_current_user
from src.apps.identity.models import User
from src.apps.tenancy.models import Tenant
from src.apps.projects.dependencies import get_current_tenant
from src.apps.finance.service import FinanceService
from src.apps.finance.models import InvoiceType, InvoiceStatus, ExpenseCategory, ExpenseStatus
from src.apps.finance.schemas import (
    CreateInvoiceRequest, UpdateInvoiceRequest,
    InvoiceResponse, InvoiceSummary,
    RecordPaymentRequest, PaymentResponse,
    CreateExpenseRequest, ExpenseResponse,
    CreateChangeOrderRequest, ChangeOrderResponse,
    CreatePaymentCertRequest, PaymentCertResponse,
    RejectInvoiceRequest, RejectExpenseRequest, RejectChangeOrderRequest,
)
from src.shared.response import APIResponse, PaginatedResponse, success_response, paginated_response
from src.core.dependencies import require_module

router = APIRouter(tags=["Finance"])


async def get_svc(
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_module("finance")), 
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> FinanceService:
    return FinanceService(db=db, tenant_id=tenant.id, user_id=current_user.id)


# ── Invoices ──────────────────────────────────────────────────────

@router.post("/projects/{project_id}/invoices",
    response_model=APIResponse[InvoiceResponse], status_code=201)
async def create_invoice(
    project_id: str, data: CreateInvoiceRequest,
    svc: FinanceService = Depends(get_svc),
):
    inv = await svc.create_invoice(project_id, data)
    return success_response(data=InvoiceResponse.model_validate(inv), message="Invoice created")


@router.get("/projects/{project_id}/invoices",
    response_model=PaginatedResponse[InvoiceSummary])
async def list_invoices(
    project_id: str,
    invoice_type: InvoiceType | None = Query(None),
    status: InvoiceStatus | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    svc: FinanceService = Depends(get_svc),
):
    skip = (page - 1) * page_size
    invoices, total = await svc.list_invoices(
        project_id, invoice_type=invoice_type,
        status=status, skip=skip, limit=page_size,
    )
    return paginated_response(
        data=[InvoiceSummary.model_validate(i) for i in invoices],
        total=total, page=page, page_size=page_size,
    )


@router.get("/invoices/{invoice_id}", response_model=APIResponse[InvoiceResponse])
async def get_invoice(invoice_id: str, svc: FinanceService = Depends(get_svc)):
    inv = await svc.get_invoice(invoice_id)
    return success_response(data=InvoiceResponse.model_validate(inv))


@router.post("/invoices/{invoice_id}/submit", response_model=APIResponse[InvoiceResponse])
async def submit_invoice(invoice_id: str, svc: FinanceService = Depends(get_svc)):
    inv = await svc.submit_invoice(invoice_id)
    return success_response(data=InvoiceResponse.model_validate(inv), message="Invoice submitted")


@router.post("/invoices/{invoice_id}/approve", response_model=APIResponse[InvoiceResponse])
async def approve_invoice(invoice_id: str, svc: FinanceService = Depends(get_svc)):
    inv = await svc.approve_invoice(invoice_id)
    return success_response(data=InvoiceResponse.model_validate(inv), message="Invoice approved")


@router.post("/invoices/{invoice_id}/reject", response_model=APIResponse[InvoiceResponse])
async def reject_invoice(invoice_id: str, data: RejectInvoiceRequest, svc: FinanceService = Depends(get_svc)):
    inv = await svc.reject_invoice(invoice_id, reason=data.reason)
    return success_response(data=InvoiceResponse.model_validate(inv), message="Invoice rejected")


@router.post("/invoices/{invoice_id}/payments",
    response_model=APIResponse[PaymentResponse], status_code=201)
async def record_payment(
    invoice_id: str, data: RecordPaymentRequest,
    svc: FinanceService = Depends(get_svc),
):
    payment = await svc.record_payment(invoice_id, data)
    return success_response(data=PaymentResponse.model_validate(payment), message="Payment recorded")


@router.get("/projects/{project_id}/finance-summary",
    response_model=APIResponse[dict])
async def finance_summary(project_id: str, svc: FinanceService = Depends(get_svc)):
    summary = await svc.get_finance_summary(project_id)
    return success_response(data=summary)


@router.get("/projects/{project_id}/cashflow", response_model=APIResponse[list])
async def cashflow(project_id: str, svc: FinanceService = Depends(get_svc)):
    data = await svc.get_cashflow(project_id)
    return success_response(data=data)


# ── Expenses ──────────────────────────────────────────────────────

@router.post("/projects/{project_id}/expenses",
    response_model=APIResponse[ExpenseResponse], status_code=201)
async def create_expense(
    project_id: str, data: CreateExpenseRequest,
    svc: FinanceService = Depends(get_svc),
):
    exp = await svc.create_expense(project_id, data)
    return success_response(data=ExpenseResponse.model_validate(exp), message="Expense created")


@router.get("/projects/{project_id}/expenses",
    response_model=PaginatedResponse[ExpenseResponse])
async def list_expenses(
    project_id: str,
    category: ExpenseCategory | None = Query(None),
    status: ExpenseStatus | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    svc: FinanceService = Depends(get_svc),
):
    skip = (page - 1) * page_size
    expenses, total = await svc.list_expenses(
        project_id, category=category,
        status=status, skip=skip, limit=page_size,
    )
    return paginated_response(
        data=[ExpenseResponse.model_validate(e) for e in expenses],
        total=total, page=page, page_size=page_size,
    )


@router.post("/expenses/{expense_id}/submit", response_model=APIResponse[ExpenseResponse])
async def submit_expense(expense_id: str, svc: FinanceService = Depends(get_svc)):
    exp = await svc.submit_expense(expense_id)
    return success_response(data=ExpenseResponse.model_validate(exp), message="Expense submitted")


@router.post("/expenses/{expense_id}/approve", response_model=APIResponse[ExpenseResponse])
async def approve_expense(expense_id: str, svc: FinanceService = Depends(get_svc)):
    exp = await svc.approve_expense(expense_id)
    return success_response(data=ExpenseResponse.model_validate(exp), message="Expense approved")


@router.post("/expenses/{expense_id}/reject", response_model=APIResponse[ExpenseResponse])
async def reject_expense(expense_id: str, data: RejectExpenseRequest, svc: FinanceService = Depends(get_svc)):
    exp = await svc.reject_expense(expense_id, reason=data.reason)
    return success_response(data=ExpenseResponse.model_validate(exp), message="Expense rejected")


# ── Change Orders ─────────────────────────────────────────────────

@router.post("/projects/{project_id}/change-orders",
    response_model=APIResponse[ChangeOrderResponse], status_code=201)
async def create_change_order(
    project_id: str, data: CreateChangeOrderRequest,
    svc: FinanceService = Depends(get_svc),
):
    co = await svc.create_change_order(project_id, data)
    return success_response(data=ChangeOrderResponse.model_validate(co), message="Change order created")


@router.get("/projects/{project_id}/change-orders",
    response_model=APIResponse[list[ChangeOrderResponse]])
async def list_change_orders(project_id: str, svc: FinanceService = Depends(get_svc)):
    cos = await svc.list_change_orders(project_id)
    return success_response(data=[ChangeOrderResponse.model_validate(c) for c in cos])


@router.post("/change-orders/{co_id}/submit", response_model=APIResponse[ChangeOrderResponse])
async def submit_change_order(co_id: str, svc: FinanceService = Depends(get_svc)):
    co = await svc.submit_change_order(co_id)
    return success_response(data=ChangeOrderResponse.model_validate(co), message="Change order submitted")


@router.post("/change-orders/{co_id}/approve", response_model=APIResponse[ChangeOrderResponse])
async def approve_change_order(co_id: str, svc: FinanceService = Depends(get_svc)):
    co = await svc.approve_change_order(co_id)
    return success_response(data=ChangeOrderResponse.model_validate(co), message="Change order approved")


@router.post("/change-orders/{co_id}/reject", response_model=APIResponse[ChangeOrderResponse])
async def reject_change_order(co_id: str, data: RejectChangeOrderRequest, svc: FinanceService = Depends(get_svc)):
    co = await svc.reject_change_order(co_id, reason=data.reason)
    return success_response(data=ChangeOrderResponse.model_validate(co), message="Change order rejected")


# ── Payment Certificates ──────────────────────────────────────────

@router.post("/projects/{project_id}/payment-certificates",
    response_model=APIResponse[PaymentCertResponse], status_code=201)
async def create_payment_cert(
    project_id: str, data: CreatePaymentCertRequest,
    svc: FinanceService = Depends(get_svc),
):
    cert = await svc.create_payment_cert(project_id, data)
    return success_response(
        data=PaymentCertResponse.model_validate(cert),
        message="Payment certificate created",
    )


@router.get("/projects/{project_id}/payment-certificates",
    response_model=APIResponse[list[PaymentCertResponse]])
async def list_payment_certs(project_id: str, svc: FinanceService = Depends(get_svc)):
    certs = await svc.list_payment_certs(project_id)
    return success_response(data=[PaymentCertResponse.model_validate(c) for c in certs])