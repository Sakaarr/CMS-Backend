from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, case, text, String
from sqlalchemy.types import DateTime
from src.apps.identity.models import User, OrganizationMember
from src.apps.projects.models import Project, ProjectStatus
from src.apps.procurement.models import PurchaseOrder, POStatus
from src.apps.finance.models import Invoice, InvoiceStatus, Expense
from src.apps.inventory.models import StockItem, MaterialRequest, MaterialRequestStatus
from src.apps.site_ops.models import DailyProgressReport
from src.apps.quality.models import Inspection, NCR, SafetyIncident
from src.apps.documents.models import Document, DocumentApproval, ApprovalStatus
from src.apps.boq.models import BudgetVersion, BudgetVersionStatus, BOQItem
from src.apps.tenancy.models import Tenant
from src.core.config import settings


class DashboardService:
    def __init__(self, db: AsyncSession, tenant_id: str, user_id: str):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

    def _scope(self, model):
        return and_(
            model.tenant_id == self.tenant_id,
            model.deleted_at.is_(None),
        )

    async def get_overview(self) -> dict:
        project_stats = await self._project_stats()
        procurement_pipeline = await self._procurement_pipeline()
        monthly_cashflow = await self._monthly_cashflow()
        pending_approvals = await self._pending_approvals_count()
        recent_projects = await self._recent_projects()
        low_stock_count = await self._low_stock_count()
        module_activity = await self._module_activity()
        recent_activity = await self._recent_activity()

        return {
            "project_stats": project_stats,
            "procurement_pipeline": procurement_pipeline,
            "monthly_cashflow": monthly_cashflow,
            "pending_approvals": pending_approvals,
            "recent_projects": recent_projects,
            "low_stock_count": low_stock_count,
            "module_activity": module_activity,
            "recent_activity": recent_activity,
        }

    async def get_project_dashboard(self, project_id: str) -> dict:
        from src.apps.finance.service import FinanceService
        from src.apps.procurement.service import ProcurementService
        from src.apps.site_ops.service import SiteOpsService
        from src.apps.quality.service import QualityService
        from src.apps.documents.service import DocumentService
        from src.apps.boq.service import BOQService

        finance_svc = FinanceService(self.db, self.tenant_id, self.user_id)
        procurement_svc = ProcurementService(self.db, self.tenant_id, self.user_id)
        site_ops_svc = SiteOpsService(self.db, self.tenant_id, self.user_id)
        quality_svc = QualityService(self.db, self.tenant_id, self.user_id)
        docs_svc = DocumentService(self.db, self.tenant_id, self.user_id)
        boq_svc = BOQService(self.db, self.tenant_id, self.user_id)

        finance = await finance_svc.get_finance_summary(project_id)
        procurement = await procurement_svc.get_procurement_stats(project_id)
        site_ops = await site_ops_svc.get_site_ops_summary(project_id)
        quality = await quality_svc.get_quality_summary(project_id)
        docs = await docs_svc.get_document_summary(project_id)

        boq = await self._latest_boq_summary(project_id)
        project = await self._get_project(project_id)
        burn_rate = await self._burn_rate(project_id, project)
        budget_vs_actual = await self._budget_vs_actual(project_id)
        health_score = self._health_score(finance, procurement, quality, site_ops, boq, project)

        return {
            "finance": finance,
            "procurement": procurement,
            "site_ops": site_ops,
            "quality": quality,
            "documents": docs,
            "boq": boq,
            "project": {
                "id": project.id,
                "name": project.name,
                "code": project.code,
                "status": project.status.value if hasattr(project.status, "value") else str(project.status),
                "progress_percentage": project.progress_percentage,
                "estimated_budget": project.estimated_budget or 0.0,
                "approved_budget": project.approved_budget or 0.0,
                "planned_start_date": str(project.planned_start_date) if project.planned_start_date else None,
                "planned_end_date": str(project.planned_end_date) if project.planned_end_date else None,
            },
            "health_score": health_score,
            "burn_rate": burn_rate,
            "budget_vs_actual": budget_vs_actual,
        }

    # ── Overview helpers ──────────────────────────────────────────

    async def _project_stats(self) -> dict:
        result = await self.db.execute(
            select(
                Project.status,
                func.count(Project.id).label("count"),
            )
            .where(self._scope(Project))
            .group_by(Project.status)
        )
        rows = result.all()
        by_status = {str(r.status): r.count for r in rows}
        total = sum(by_status.values())

        budget_result = await self.db.execute(
            select(func.sum(Project.estimated_budget))
            .where(and_(
                self._scope(Project),
                Project.status == ProjectStatus.ACTIVE,
            ))
        )
        active_budget = budget_result.scalar_one_or_none() or 0.0

        approved_result = await self.db.execute(
            select(func.sum(Project.approved_budget))
            .where(and_(
                self._scope(Project),
                Project.status == ProjectStatus.ACTIVE,
            ))
        )
        approved_budget = approved_result.scalar_one_or_none() or 0.0

        return {
            "total": total,
            "by_status": by_status,
            "active_budget_total": round(active_budget, 2),
            "approved_budget_total": round(approved_budget, 2),
        }

    async def _procurement_pipeline(self) -> dict:
        result = await self.db.execute(
            select(
                PurchaseOrder.status,
                func.count(PurchaseOrder.id).label("count"),
                func.sum(PurchaseOrder.grand_total).label("total_value"),
            )
            .where(self._scope(PurchaseOrder))
            .group_by(PurchaseOrder.status)
        )
        rows = result.all()
        by_status = {}
        for r in rows:
            key = str(r.status) if r.status else "unknown"
            by_status[key] = {
                "count": r.count,
                "value": round(r.total_value or 0, 2),
            }
        return {
            "by_status": by_status,
            "total_po_value": round(sum(r.total_value or 0 for r in rows), 2),
            "total_pos": sum(r.count for r in rows),
        }

    async def _monthly_cashflow(self) -> list[dict]:
        month_col = func.date_trunc("month", Invoice.invoice_date)
        inv_result = await self.db.execute(
            select(
                month_col.label("month"),
                func.sum(Invoice.grand_total).label("invoiced"),
                func.sum(Invoice.paid_amount).label("received"),
            )
            .where(self._scope(Invoice))
            .group_by(month_col)
            .order_by(month_col)
            .limit(12)
        )
        inv_rows = inv_result.all()

        exp_month = func.date_trunc("month", Expense.expense_date)
        exp_result = await self.db.execute(
            select(
                exp_month.label("month"),
                func.sum(Expense.total_amount).label("expenses"),
            )
            .where(self._scope(Expense))
            .group_by(exp_month)
        )
        exp_map = {str(r.month)[:7]: round(r.expenses or 0, 2) for r in exp_result.all()}

        dpr_month = func.date_trunc("month", DailyProgressReport.report_date)
        dpr_result = await self.db.execute(
            select(
                dpr_month.label("month"),
                func.sum(DailyProgressReport.total_labour_cost).label("labour_cost"),
            )
            .where(self._scope(DailyProgressReport))
            .group_by(dpr_month)
        )
        dpr_map = {}
        for r in dpr_result.all():
            key = str(r.month)[:7]
            dpr_map[key] = round(r.labour_cost or 0, 2)

        return [
            {
                "month": str(r.month)[:7],
                "invoiced": round(r.invoiced or 0, 2),
                "received": round(r.received or 0, 2),
                "expenses": exp_map.get(str(r.month)[:7], 0),
                "labour_cost": dpr_map.get(str(r.month)[:7], 0),
            }
            for r in inv_rows
        ]

    async def _pending_approvals_count(self) -> int:
        count = 0

        po_count = await self.db.execute(
            select(func.count(PurchaseOrder.id)).where(and_(
                self._scope(PurchaseOrder),
                PurchaseOrder.status == POStatus.PENDING_APPROVAL,
            ))
        )
        count += po_count.scalar_one() or 0

        inv_count = await self.db.execute(
            select(func.count(Invoice.id)).where(and_(
                self._scope(Invoice),
                Invoice.status == InvoiceStatus.SUBMITTED,
            ))
        )
        count += inv_count.scalar_one() or 0

        mr_count = await self.db.execute(
            select(func.count(MaterialRequest.id)).where(and_(
                self._scope(MaterialRequest),
                MaterialRequest.status == MaterialRequestStatus.SUBMITTED,
            ))
        )
        count += mr_count.scalar_one() or 0

        bv_count = await self.db.execute(
            select(func.count(BudgetVersion.id)).where(and_(
                self._scope(BudgetVersion),
                BudgetVersion.status == BudgetVersionStatus.SUBMITTED,
            ))
        )
        count += bv_count.scalar_one() or 0

        doc_count = await self.db.execute(
            select(func.count(DocumentApproval.id))
            .join(Document, Document.id == DocumentApproval.document_id)
            .where(and_(
                DocumentApproval.status == ApprovalStatus.PENDING,
                Document.tenant_id == self.tenant_id,
                Document.deleted_at.is_(None),
            ))
        )
        count += doc_count.scalar_one() or 0

        return count

    async def _recent_projects(self) -> list[dict]:
        result = await self.db.execute(
            select(Project)
            .where(self._scope(Project))
            .order_by(Project.created_at.desc())
            .limit(6)
        )
        projects = result.scalars().all()
        return [
            {
                "id": p.id,
                "name": p.name,
                "code": p.code,
                "status": p.status.value if hasattr(p.status, "value") else str(p.status),
                "progress_percentage": p.progress_percentage,
                "estimated_budget": p.estimated_budget or 0.0,
                "approved_budget": p.approved_budget or 0.0,
                "planned_end_date": str(p.planned_end_date) if p.planned_end_date else None,
                "city": p.city or "",
            }
            for p in projects
        ]

    async def _low_stock_count(self) -> int:
        result = await self.db.execute(
            select(func.count(StockItem.id)).where(and_(
                self._scope(StockItem),
                StockItem.reorder_level > 0,
                StockItem.quantity_on_hand <= StockItem.reorder_level,
            ))
        )
        return result.scalar_one() or 0

    async def _module_activity(self) -> dict:
        proj_count = await self.db.execute(
            select(func.count(Project.id)).where(self._scope(Project))
        )
        po_count = await self.db.execute(
            select(func.count(PurchaseOrder.id)).where(self._scope(PurchaseOrder))
        )
        inv_count = await self.db.execute(
            select(func.count(Invoice.id)).where(self._scope(Invoice))
        )
        dpr_count = await self.db.execute(
            select(func.count(DailyProgressReport.id)).where(self._scope(DailyProgressReport))
        )
        mr_count = await self.db.execute(
            select(func.count(MaterialRequest.id)).where(self._scope(MaterialRequest))
        )
        insp_count = await self.db.execute(
            select(func.count(Inspection.id)).where(self._scope(Inspection))
        )

        return {
            "projects": proj_count.scalar_one() or 0,
            "procurement": po_count.scalar_one() or 0,
            "finance": inv_count.scalar_one() or 0,
            "site_ops": dpr_count.scalar_one() or 0,
            "inventory": mr_count.scalar_one() or 0,
            "quality": insp_count.scalar_one() or 0,
        }

    async def _recent_activity(self) -> list[dict]:
        activities = []

        inv_result = await self.db.execute(
            select(Invoice.id, Invoice.invoice_number, Invoice.created_at)
            .where(self._scope(Invoice))
            .order_by(Invoice.created_at.desc())
            .limit(5)
        )
        for r in inv_result.all():
            activities.append({
                "id": r[0], "type": "invoice", "label": f"Invoice {r[1]}",
                "created_at": str(r[2]),
            })

        po_result = await self.db.execute(
            select(PurchaseOrder.id, PurchaseOrder.po_number, PurchaseOrder.created_at)
            .where(self._scope(PurchaseOrder))
            .order_by(PurchaseOrder.created_at.desc())
            .limit(5)
        )
        for r in po_result.all():
            activities.append({
                "id": r[0], "type": "purchase_order", "label": f"PO {r[1]}",
                "created_at": str(r[2]),
            })

        mr_result = await self.db.execute(
            select(MaterialRequest.id, MaterialRequest.mr_number, MaterialRequest.created_at)
            .where(self._scope(MaterialRequest))
            .order_by(MaterialRequest.created_at.desc())
            .limit(5)
        )
        for r in mr_result.all():
            activities.append({
                "id": r[0], "type": "material_request", "label": f"MR {r[1]}",
                "created_at": str(r[2]),
            })

        dpr_result = await self.db.execute(
            select(DailyProgressReport.id, DailyProgressReport.report_date, DailyProgressReport.created_at)
            .where(self._scope(DailyProgressReport))
            .order_by(DailyProgressReport.created_at.desc())
            .limit(5)
        )
        for r in dpr_result.all():
            activities.append({
                "id": r[0], "type": "dpr", "label": f"DPR {r[1]}",
                "created_at": str(r[2]),
            })

        activities.sort(key=lambda a: a["created_at"], reverse=True)
        return activities[:10]

    # ── Project dashboard helpers ─────────────────────────────────

    async def _get_project(self, project_id: str) -> Project:
        result = await self.db.execute(
            select(Project).where(and_(
                Project.id == project_id,
                self._scope(Project),
            ))
        )
        return result.scalar_one()

    async def _latest_boq_summary(self, project_id: str) -> dict | None:
        bv_result = await self.db.execute(
            select(BudgetVersion)
            .where(and_(
                BudgetVersion.project_id == project_id,
                self._scope(BudgetVersion),
                BudgetVersion.status == BudgetVersionStatus.APPROVED,
            ))
            .order_by(BudgetVersion.version_number.desc())
            .limit(1)
        )
        bv = bv_result.scalar_one_or_none()
        if not bv:
            return None

        items_result = await self.db.execute(
            select(
                func.sum(BOQItem.amount).label("planned"),
                func.sum(BOQItem.actual_amount).label("actual"),
            )
            .where(and_(
                BOQItem.budget_version_id == bv.id,
                BOQItem.deleted_at.is_(None),
                BOQItem.is_section_header.is_(False),
            ))
        )
        row = items_result.one()

        return {
            "version_id": bv.id,
            "version_number": bv.version_number,
            "name": bv.name,
            "status": bv.status.value if hasattr(bv.status, "value") else str(bv.status),
            "grand_total": bv.grand_total or 0.0,
            "total_material_cost": bv.total_material_cost or 0.0,
            "total_labour_cost": bv.total_labour_cost or 0.0,
            "total_equipment_cost": bv.total_equipment_cost or 0.0,
            "total_overhead": bv.total_overhead or 0.0,
            "contingency_amount": bv.contingency_amount or 0.0,
            "planned_total": round(row.planned or 0, 2),
            "actual_total": round(row.actual or 0, 2),
        }

    async def _burn_rate(
        self, project_id: str, project: Project
    ) -> dict | None:
        from datetime import date, datetime

        if not project.approved_budget or project.approved_budget <= 0:
            return None

        if not project.planned_start_date:
            return None

        start = project.planned_start_date
        if isinstance(start, str):
            start = datetime.strptime(start, "%Y-%m-%d").date()

        end = project.planned_end_date
        if isinstance(end, str):
            end = datetime.strptime(end, "%Y-%m-%d").date() if end else None

        today = date.today()
        total_days = (end - start).days if end else 365
        elapsed_days = (today - start).days
        if elapsed_days <= 0 or total_days <= 0:
            return None

        planned_pct = min(elapsed_days / total_days * 100, 100)
        expected_spend = round(project.approved_budget * (elapsed_days / total_days), 2)

        # Actual spend: expenses + invoiced amounts
        exp_result = await self.db.execute(
            select(func.sum(Expense.total_amount)).where(and_(
                Expense.project_id == project_id,
                self._scope(Expense),
            ))
        )
        actual_expenses = exp_result.scalar_one_or_none() or 0.0

        inv_result = await self.db.execute(
            select(func.sum(Invoice.grand_total)).where(and_(
                Invoice.project_id == project_id,
                self._scope(Invoice),
            ))
        )
        actual_invoiced = inv_result.scalar_one_or_none() or 0.0

        total_spent = round(actual_expenses + actual_invoiced, 2)
        daily_burn = round(total_spent / elapsed_days, 2) if elapsed_days > 0 else 0
        remaining_budget = round(project.approved_budget - total_spent, 2)

        return {
            "approved_budget": round(project.approved_budget, 2),
            "total_spent": total_spent,
            "remaining_budget": max(remaining_budget, 0),
            "over_budget": remaining_budget < 0,
            "daily_burn": daily_burn,
            "expected_spend": expected_spend,
            "planned_progress_pct": round(planned_pct, 1),
            "elapsed_days": elapsed_days,
            "total_days": total_days,
            "variance": round(total_spent - expected_spend, 2),
        }

    async def _budget_vs_actual(self, project_id: str) -> dict | None:
        bv_result = await self.db.execute(
            select(BudgetVersion)
            .where(and_(
                BudgetVersion.project_id == project_id,
                self._scope(BudgetVersion),
            ))
            .order_by(BudgetVersion.version_number.desc())
            .limit(1)
        )
        bv = bv_result.scalar_one_or_none()
        if not bv:
            return None

        actual_expenses = await self.db.execute(
            select(func.sum(Expense.total_amount)).where(and_(
                Expense.project_id == project_id,
                self._scope(Expense),
                Expense.status.in_(["approved", "reimbursed"]),
            ))
        )
        total_expenses = actual_expenses.scalar_one_or_none() or 0.0

        invoiced_result = await self.db.execute(
            select(func.sum(Invoice.grand_total)).where(and_(
                Invoice.project_id == project_id,
                self._scope(Invoice),
            ))
        )
        total_invoiced = invoiced_result.scalar_one_or_none() or 0.0

        total_actual = round(total_expenses + total_invoiced, 2)
        budget = bv.grand_total or 0.0

        return {
            "budget": round(budget, 2),
            "actual": total_actual,
            "variance": round(budget - total_actual, 2),
            "utilization_pct": round(total_actual / budget * 100, 1) if budget > 0 else 0,
            "budget_version_name": bv.name,
            "budget_version_number": bv.version_number,
        }

    def _health_score(
        self,
        finance: dict,
        procurement: dict,
        quality: dict,
        site_ops: dict,
        boq: dict | None,
        project: Project,
    ) -> dict:
        scores: list[float] = []

        # Schedule: based on progress vs planned timeline
        schedule_score = 100.0
        if project.planned_start_date and project.planned_end_date:
            from datetime import date
            start = project.planned_start_date
            if isinstance(start, str):
                from datetime import datetime
                start = datetime.strptime(start, "%Y-%m-%d").date()
            end = project.planned_end_date
            if isinstance(end, str):
                from datetime import datetime
                end = datetime.strptime(end, "%Y-%m-%d").date() if end else None
            if end:
                today = date.today()
                total = (end - start).days
                elapsed = (today - start).days
                if total > 0 and elapsed > 0:
                    expected_progress = elapsed / total * 100
                    actual_progress = project.progress_percentage
                    if expected_progress > 0:
                        ratio = actual_progress / expected_progress
                        schedule_score = min(ratio * 100, 100)
        scores.append(max(0, min(schedule_score, 100)))

        # Financial: based on over/under budget
        finance_score = 100.0
        if boq and boq.get("grand_total", 0) > 0:
            variance = boq.get("variance", 0)
            budget = boq.get("grand_total", 1)
            var_pct = abs(variance) / budget * 100
            finance_score = max(0, 100 - var_pct * 2)
        scores.append(finance_score)

        # Quality: based on inspection pass rate
        quality_score = 100.0
        total_inspections = quality.get("total_inspections", 0)
        if total_inspections > 0:
            pass_pct = quality.get("passed_inspections", 0) / total_inspections * 100
            quality_score = pass_pct
        scores.append(max(0, min(quality_score, 100)))

        # Procurement: fewer pending approvals = better
        proc_score = 100.0
        pending = procurement.get("pending_approval", 0)
        if pending > 5:
            proc_score = max(0, 100 - pending * 5)
        scores.append(proc_score)

        # Safety: fewer open NCRs/incidents = better
        safety_score = 100.0
        open_ncrs = quality.get("open_ncrs", 0)
        open_incidents = quality.get("open_incidents", 0)
        issues = open_ncrs + open_incidents
        if issues > 0:
            safety_score = max(0, 100 - issues * 10)
        scores.append(safety_score)

        overall = round(sum(scores) / len(scores), 1) if scores else 0

        label = "Healthy"
        if overall < 40:
            label = "Critical"
        elif overall < 60:
            label = "At Risk"
        elif overall < 80:
            label = "Fair"

        return {
            "overall": overall,
            "label": label,
            "schedule": round(scores[0], 1) if len(scores) > 0 else 0,
            "financial": round(scores[1], 1) if len(scores) > 1 else 0,
            "quality": round(scores[2], 1) if len(scores) > 2 else 0,
            "procurement": round(scores[3], 1) if len(scores) > 3 else 0,
            "safety": round(scores[4], 1) if len(scores) > 4 else 0,
        }


class SuperAdminDashboardService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_overview(self) -> dict:
        tenant_stats = await self._tenant_stats()
        plan_distribution = await self._plan_distribution()
        monthly_signups = await self._monthly_tenant_signups()
        tenant_user_counts = await self._tenant_user_counts()
        tenant_project_counts = await self._tenant_project_counts()
        total_users = await self._total_users()
        total_projects = await self._total_projects()
        total_revenue = await self._total_revenue()
        recent_tenants = await self._recent_tenants()
        top_tenants_by_revenue = await self._top_tenants_by_revenue()

        return {
            "tenant_stats": tenant_stats,
            "plan_distribution": plan_distribution,
            "monthly_signups": monthly_signups,
            "tenant_user_counts": tenant_user_counts,
            "tenant_project_counts": tenant_project_counts,
            "total_users": total_users,
            "total_projects": total_projects,
            "total_revenue": total_revenue,
            "recent_tenants": recent_tenants,
            "top_tenants_by_revenue": top_tenants_by_revenue,
        }

    async def get_tenant_detail(self, tenant_id: str) -> dict:
        from src.apps.tenancy.service import TenantService
        ts = TenantService(self.db)
        tenant = await ts.get_by_id(tenant_id)
        if not tenant:
            return {}

        user_count = await self.db.execute(
            select(func.count(OrganizationMember.id))
            .where(and_(
                OrganizationMember.tenant_id == tenant_id,
                OrganizationMember.deleted_at.is_(None),
            ))
        )

        project_count = await self.db.execute(
            select(func.count(Project.id))
            .where(and_(
                Project.tenant_id == tenant_id,
                Project.deleted_at.is_(None),
            ))
        )

        total_invoiced = await self.db.execute(
            select(func.coalesce(func.sum(Invoice.grand_total), 0))
            .where(and_(
                Invoice.tenant_id == tenant_id,
                Invoice.deleted_at.is_(None),
            ))
        )

        total_paid = await self.db.execute(
            select(func.coalesce(func.sum(Invoice.paid_amount), 0))
            .where(and_(
                Invoice.tenant_id == tenant_id,
                Invoice.deleted_at.is_(None),
            ))
        )

        projects_result = await self.db.execute(
            select(
                Project.status,
                func.count(Project.id).label("count"),
            )
            .where(and_(
                Project.tenant_id == tenant_id,
                Project.deleted_at.is_(None),
            ))
            .group_by(Project.status)
        )

        users_result = await self.db.execute(
            select(User.full_name, User.email, User.is_active, OrganizationMember.role)
            .join(OrganizationMember, OrganizationMember.user_id == User.id)
            .where(and_(
                OrganizationMember.tenant_id == tenant_id,
                OrganizationMember.deleted_at.is_(None),
                User.deleted_at.is_(None),
            ))
            .order_by(User.created_at.desc())
        )

        return {
            "tenant": {
                "id": tenant.id,
                "name": tenant.name,
                "slug": tenant.slug,
                "status": tenant.status.value if hasattr(tenant.status, "value") else str(tenant.status),
                "plan": tenant.plan.value if hasattr(tenant.plan, "value") else str(tenant.plan),
                "email": tenant.email,
                "phone": tenant.phone,
                "address": tenant.address,
                "country": tenant.country,
                "currency": tenant.currency,
                "pan_number": tenant.pan_number,
                "vat_number": tenant.vat_number,
                "logo_url": tenant.logo_url,
                "is_active": tenant.is_active,
                "max_projects": tenant.max_projects,
                "max_users": tenant.max_users,
                "created_at": str(tenant.created_at) if tenant.created_at else None,
            },
            "user_count": user_count.scalar_one() or 0,
            "project_count": project_count.scalar_one() or 0,
            "total_invoiced": round(total_invoiced.scalar_one() or 0, 2),
            "total_paid": round(total_paid.scalar_one() or 0, 2),
            "projects_by_status": {
                str(r.status): r.count for r in projects_result.all()
            },
            "users": [
                {
                    "full_name": r.full_name,
                    "email": r.email,
                    "is_active": r.is_active,
                    "role": r.role.value if hasattr(r.role, "value") else str(r.role),
                }
                for r in users_result.all()
            ],
        }

    async def _tenant_stats(self) -> dict:
        result = await self.db.execute(
            select(
                Tenant.status,
                func.count(Tenant.id).label("count"),
            )
            .where(Tenant.deleted_at.is_(None))
            .group_by(Tenant.status)
        )
        rows = result.all()
        by_status = {str(r.status): r.count for r in rows}
        total = sum(by_status.values())
        return {
            "total": total,
            "by_status": by_status,
        }

    async def _plan_distribution(self) -> list[dict]:
        result = await self.db.execute(
            select(
                Tenant.plan,
                func.count(Tenant.id).label("count"),
            )
            .where(Tenant.deleted_at.is_(None))
            .group_by(Tenant.plan)
            .order_by(func.count(Tenant.id).desc())
        )
        return [
            {
                "plan": str(r.plan),
                "count": r.count,
            }
            for r in result.all()
        ]

    async def _monthly_tenant_signups(self) -> list[dict]:
        month_col = func.date_trunc("month", Tenant.created_at)
        result = await self.db.execute(
            select(
                month_col.label("month"),
                func.count(Tenant.id).label("count"),
            )
            .where(Tenant.deleted_at.is_(None))
            .group_by(month_col)
            .order_by(month_col)
            .limit(12)
        )
        return [
            {
                "month": str(r.month)[:7],
                "count": r.count,
            }
            for r in result.all()
        ]

    async def _total_users(self) -> int:
        result = await self.db.execute(
            select(func.count(OrganizationMember.id))
            .where(OrganizationMember.deleted_at.is_(None))
        )
        return result.scalar_one() or 0

    async def _total_projects(self) -> int:
        result = await self.db.execute(
            select(func.count(Project.id))
            .where(Project.deleted_at.is_(None))
        )
        return result.scalar_one() or 0

    async def _total_revenue(self) -> float:
        result = await self.db.execute(
            select(func.coalesce(func.sum(Invoice.grand_total), 0))
            .where(Invoice.deleted_at.is_(None))
        )
        return round(result.scalar_one() or 0, 2)

    async def _tenant_user_counts(self) -> list[dict]:
        result = await self.db.execute(
            select(
                Tenant.id.label("tenant_id"),
                Tenant.name.label("tenant_name"),
                func.count(OrganizationMember.id).label("user_count"),
            )
            .join(OrganizationMember, OrganizationMember.tenant_id == Tenant.id, isouter=True)
            .where(Tenant.deleted_at.is_(None))
            .group_by(Tenant.id, Tenant.name)
            .order_by(func.count(OrganizationMember.id).desc())
        )
        return [
            {
                "tenant_id": r.tenant_id,
                "tenant_name": r.tenant_name,
                "user_count": r.user_count,
            }
            for r in result.all()
        ]

    async def _tenant_project_counts(self) -> list[dict]:
        result = await self.db.execute(
            select(
                Tenant.id.label("tenant_id"),
                Tenant.name.label("tenant_name"),
                func.count(Project.id).label("project_count"),
            )
            .join(Project, Project.tenant_id == Tenant.id, isouter=True)
            .where(Tenant.deleted_at.is_(None))
            .group_by(Tenant.id, Tenant.name)
            .order_by(func.count(Project.id).desc())
        )
        return [
            {
                "tenant_id": r.tenant_id,
                "tenant_name": r.tenant_name,
                "project_count": r.project_count,
            }
            for r in result.all()
        ]

    async def _recent_tenants(self) -> list[dict]:
        result = await self.db.execute(
            select(Tenant)
            .where(Tenant.deleted_at.is_(None))
            .order_by(Tenant.created_at.desc())
            .limit(10)
        )
        tenants = result.scalars().all()
        return [
            {
                "id": t.id,
                "name": t.name,
                "slug": t.slug,
                "status": t.status.value if hasattr(t.status, "value") else str(t.status),
                "plan": t.plan.value if hasattr(t.plan, "value") else str(t.plan),
                "created_at": str(t.created_at) if t.created_at else None,
            }
            for t in tenants
        ]

    async def _top_tenants_by_revenue(self) -> list[dict]:
        result = await self.db.execute(
            select(
                Tenant.id.label("tenant_id"),
                Tenant.name.label("tenant_name"),
                func.coalesce(func.sum(Invoice.grand_total), 0).label("revenue"),
            )
            .join(Invoice, Invoice.tenant_id == Tenant.id, isouter=True)
            .where(and_(
                Tenant.deleted_at.is_(None),
                Invoice.deleted_at.is_(None),
            ))
            .group_by(Tenant.id, Tenant.name)
            .order_by(func.coalesce(func.sum(Invoice.grand_total), 0).desc())
            .limit(10)
        )
        return [
            {
                "tenant_id": r.tenant_id,
                "tenant_name": r.tenant_name,
                "revenue": round(r.revenue, 2),
            }
            for r in result.all()
        ]
