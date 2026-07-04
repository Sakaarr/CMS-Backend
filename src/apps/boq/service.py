from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, update
from sqlalchemy.orm import selectinload
from src.apps.boq.models import (
    CostCode, BudgetVersion, BOQItem, RateAnalysis, RateAnalysisComponent,
    BudgetVersionStatus, BOQItemStatus
)
from src.apps.boq.schemas import (
    CreateCostCodeRequest, UpdateCostCodeRequest,
    CreateBudgetVersionRequest, UpdateBudgetVersionRequest,
    CreateBOQItemRequest, UpdateBOQItemRequest,
    CreateRateAnalysisRequest,
)
from src.core.exceptions import NotFoundError, ConflictError, ValidationError

from src.core.notifications import NotificationService

from src.apps.projects.models import Project
from src.apps.identity.models import User
from src.core.email_templates import (
    item_approved_html, notify_user_by_id,
)
from src.apps.boq.models import UnitOfMeasure
import logging
import openpyxl
import io

logger = logging.getLogger(__name__)



class BOQService:
    def __init__(self, db: AsyncSession, tenant_id: str, user_id: str):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

    # ── Cost Codes ────────────────────────────────────────────────

    async def create_cost_code(self, data: CreateCostCodeRequest) -> CostCode:
        existing = await self.db.execute(
            select(CostCode).where(
                and_(
                    CostCode.tenant_id == self.tenant_id,
                    CostCode.code == data.code,
                    CostCode.deleted_at.is_(None),
                )
            )
        )
        if existing.scalar_one_or_none():
            raise ConflictError(f"Cost code '{data.code}' already exists")

        cost_code = CostCode(
            **data.model_dump(),
            tenant_id=self.tenant_id,
            created_by=self.user_id,
        )
        self.db.add(cost_code)
        await self.db.flush()
        return cost_code

    async def list_cost_codes(
        self, category=None, search: str | None = None
    ) -> list[CostCode]:
        conditions = [
            CostCode.tenant_id == self.tenant_id,
            CostCode.deleted_at.is_(None),
            CostCode.is_active.is_(True),
        ]
        if category:
            conditions.append(CostCode.category == category)
        if search:
            conditions.append(
                CostCode.name.ilike(f"%{search}%") | CostCode.code.ilike(f"%{search}%")
            )
        result = await self.db.execute(
            select(CostCode).where(and_(*conditions)).order_by(CostCode.code)
        )
        return list(result.scalars().all())

    async def get_cost_code(self, cost_code_id: str) -> CostCode:
        result = await self.db.execute(
            select(CostCode).where(
                and_(
                    CostCode.id == cost_code_id,
                    CostCode.tenant_id == self.tenant_id,
                    CostCode.deleted_at.is_(None),
                )
            )
        )
        cc = result.scalar_one_or_none()
        if not cc:
            raise NotFoundError("Cost code")
        return cc

    async def update_cost_code(self, cost_code_id: str, data: UpdateCostCodeRequest) -> CostCode:
        cc = await self.get_cost_code(cost_code_id)
        for k, v in data.model_dump(exclude_none=True).items():
            setattr(cc, k, v)
        cc.updated_by = self.user_id
        await self.db.flush()
        return cc

    # ── Budget Versions ───────────────────────────────────────────

    async def create_budget_version(
        self, project_id: str, data: CreateBudgetVersionRequest
    ) -> BudgetVersion:
        # Get next version number
        result = await self.db.execute(
            select(func.max(BudgetVersion.version_number)).where(
                and_(
                    BudgetVersion.project_id == project_id,
                    BudgetVersion.tenant_id == self.tenant_id,
                    BudgetVersion.deleted_at.is_(None),
                )
            )
        )
        last = result.scalar_one_or_none() or 0

        bv = BudgetVersion(
            **data.model_dump(),
            project_id=project_id,
            tenant_id=self.tenant_id,
            version_number=last + 1,
            created_by=self.user_id,
        )
        self.db.add(bv)
        await self.db.flush()
        return bv

    async def copy_budget_version(
        self, version_id: str, name: str | None = None,
        contingency_percentage: float | None = None,
    ) -> BudgetVersion:
        source = await self.get_budget_version(version_id)
        items_result = await self.db.execute(
            select(BOQItem).where(and_(
                BOQItem.budget_version_id == version_id,
                BOQItem.tenant_id == self.tenant_id,
                BOQItem.deleted_at.is_(None),
            ))
        )
        source_items = list(items_result.scalars().all())

        last_result = await self.db.execute(
            select(func.max(BudgetVersion.version_number)).where(
                and_(
                    BudgetVersion.project_id == source.project_id,
                    BudgetVersion.tenant_id == self.tenant_id,
                    BudgetVersion.deleted_at.is_(None),
                )
            )
        )
        last = last_result.scalar_one_or_none() or 0

        new_bv = BudgetVersion(
            project_id=source.project_id,
            version_number=last + 1,
            name=name or f"Copy of {source.name}",
            description=source.description,
            status=BudgetVersionStatus.DRAFT,
            contingency_percentage=contingency_percentage or source.contingency_percentage,
            currency=source.currency,
            tenant_id=self.tenant_id,
            created_by=self.user_id,
        )
        self.db.add(new_bv)
        await self.db.flush()

        for item in source_items:
            new_item = BOQItem(
                budget_version_id=new_bv.id,
                project_id=item.project_id,
                cost_code_id=item.cost_code_id,
                parent_id=None,
                item_number=item.item_number,
                description=item.description,
                specification=item.specification,
                unit=item.unit,
                quantity=item.quantity,
                unit_rate=item.unit_rate,
                amount=item.amount,
                material_rate=item.material_rate,
                labour_rate=item.labour_rate,
                equipment_rate=item.equipment_rate,
                overhead_rate=item.overhead_rate,
                status=BOQItemStatus.DRAFT,
                is_section_header=item.is_section_header,
                sort_order=item.sort_order,
                tenant_id=self.tenant_id,
                created_by=self.user_id,
                actual_quantity=0.0,
                actual_amount=0.0,
            )
            self.db.add(new_item)

        await self.db.flush()
        await self._recalculate_version_totals(new_bv.id)
        return new_bv

    async def get_budget_version(self, version_id: str) -> BudgetVersion:
        result = await self.db.execute(
            select(BudgetVersion).where(
                and_(
                    BudgetVersion.id == version_id,
                    BudgetVersion.tenant_id == self.tenant_id,
                    BudgetVersion.deleted_at.is_(None),
                )
            )
        )
        bv = result.scalar_one_or_none()
        if not bv:
            raise NotFoundError("Budget version")
        return bv

    async def list_budget_versions(self, project_id: str) -> list[BudgetVersion]:
        result = await self.db.execute(
            select(BudgetVersion).where(
                and_(
                    BudgetVersion.project_id == project_id,
                    BudgetVersion.tenant_id == self.tenant_id,
                    BudgetVersion.deleted_at.is_(None),
                )
            ).order_by(BudgetVersion.version_number.desc())
        )
        return list(result.scalars().all())

    async def approve_budget_version(self, version_id: str) -> BudgetVersion:
        bv = await self.get_budget_version(version_id)
        if bv.status == BudgetVersionStatus.APPROVED:
            raise ValidationError("Budget version is already approved")

        # Supersede any previously approved version for this project
        await self.db.execute(
            update(BudgetVersion)
            .where(
                and_(
                    BudgetVersion.project_id == bv.project_id,
                    BudgetVersion.tenant_id == self.tenant_id,
                    BudgetVersion.status == BudgetVersionStatus.APPROVED,
                    BudgetVersion.id != version_id,
                )
            )
            .values(status=BudgetVersionStatus.SUPERSEDED)
        )

        bv.status = BudgetVersionStatus.APPROVED
        bv.approved_by = self.user_id
        await self.db.flush()

        if bv.created_by:
            notif = NotificationService(self.db, self.tenant_id)
            await notif.notify_approved(
                module="boq",
                item_type="budget_version",
                item_id=bv.id,
                item_number=f"{bv.name} v{bv.version_number}",
                created_by=bv.created_by,
                approved_by=self.user_id,
                project_id=bv.project_id,
                extra_meta={
                    "Version": str(bv.version_number),
                    "Grand Total": f"{bv.grand_total:,.2f}" if bv.grand_total else "N/A",
                    "Currency": bv.currency or "NPR",
                },
            )
        try:
            proj = (await self.db.execute(
                select(Project.name, Project.code)
                .where(Project.id == bv.project_id)
            )).one_or_none()
            proj_name = f"{proj[0]} ({proj[1]})" if proj else "—"
            approver_name = (await self.db.execute(
                select(User.full_name).where(User.id == self.user_id)
            )).scalar_one_or_none() or "An approver"
            html = item_approved_html("Budget Version", bv.name or bv.id, proj_name, approver_name)
            await notify_user_by_id(self.db, bv.created_by, f"Budget Version {bv.name} Approved", html)
        except Exception as e:
            logger.warning(f"Failed to send budget version approval email: {e}")

        return bv

    # ── BOQ Items ─────────────────────────────────────────────────

    async def create_boq_item(
        self, project_id: str, version_id: str, data: CreateBOQItemRequest
    ) -> BOQItem:
        bv = await self.get_budget_version(version_id)
        if bv.status == BudgetVersionStatus.APPROVED:
            raise ValidationError("Cannot modify an approved budget version")

        amount = round(data.quantity * data.unit_rate, 2)
        item = BOQItem(
            **data.model_dump(),
            project_id=project_id,
            budget_version_id=version_id,
            tenant_id=self.tenant_id,
            amount=amount,
            created_by=self.user_id,
            actual_quantity=0.0,
            actual_amount=0.0,
            status=BOQItemStatus.DRAFT,
        )
        self.db.add(item)
        await self.db.flush()
        await self._recalculate_version_totals(version_id)
        return item

    async def list_boq_items(
        self, version_id: str, parent_id: str | None = None
    ) -> list[BOQItem]:
        conditions = [
            BOQItem.budget_version_id == version_id,
            BOQItem.tenant_id == self.tenant_id,
            BOQItem.deleted_at.is_(None),
        ]
        if parent_id is not None:
            conditions.append(BOQItem.parent_id == parent_id)
        else:
            conditions.append(BOQItem.parent_id.is_(None))

        result = await self.db.execute(
            select(BOQItem)
            .where(and_(*conditions))
            .order_by(BOQItem.sort_order, BOQItem.item_number)
        )
        return list(result.scalars().all())

    async def get_boq_item(self, item_id: str) -> BOQItem:
        result = await self.db.execute(
            select(BOQItem).where(
                and_(
                    BOQItem.id == item_id,
                    BOQItem.tenant_id == self.tenant_id,
                    BOQItem.deleted_at.is_(None),
                )
            )
        )
        item = result.scalar_one_or_none()
        if not item:
            raise NotFoundError("BOQ item")
        return item

    async def update_boq_item(self, item_id: str, data: UpdateBOQItemRequest) -> BOQItem:
        item = await self.get_boq_item(item_id)
        bv = await self.get_budget_version(item.budget_version_id)
        if bv.status == BudgetVersionStatus.APPROVED:
            raise ValidationError("Cannot modify items in an approved budget version")

        updates = data.model_dump(exclude_none=True)
        for k, v in updates.items():
            setattr(item, k, v)

        # Recalculate amount
        item.amount = round(item.quantity * item.unit_rate, 2)
        item.actual_amount = round(item.actual_quantity * item.unit_rate, 2)
        item.updated_by = self.user_id
        await self.db.flush()
        await self._recalculate_version_totals(item.budget_version_id)
        return item

    async def delete_boq_item(self, item_id: str) -> None:
        item = await self.get_boq_item(item_id)
        bv = await self.get_budget_version(item.budget_version_id)
        if bv.status == BudgetVersionStatus.APPROVED:
            raise ValidationError("Cannot delete items from an approved budget version")
        from datetime import datetime, timezone
        item.deleted_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self._recalculate_version_totals(item.budget_version_id)

    async def import_boq_items_from_excel(
        self, project_id: str, version_id: str, file_content: bytes
    ) -> dict:
        bv = await self.get_budget_version(version_id)
        if bv.status == BudgetVersionStatus.APPROVED:
            raise ValidationError("Cannot modify an approved budget version")

        try:
            wb = openpyxl.load_workbook(io.BytesIO(file_content), read_only=True, data_only=True)
        except Exception as e:
            raise ValidationError(f"Could not read the Excel file: {e}")
        ws = wb.active
        if ws is None:
            raise ValidationError("Spreadsheet has no active sheet")
        rows = list(ws.iter_rows(values_only=True))
        if not rows or len(rows) < 2:
            raise ValidationError("Spreadsheet must have a header row and at least one data row")

        headers = [str(h).strip().lower().replace(" ", "_") if h else "" for h in rows[0]]
        col_map = {}
        aliases = {
            "item_number": ["item_number", "item no", "item no.", "item_no", "no", "number", "sno", "s.no", "sn"],
            "description": ["description", "desc", "description of work", "work description", "item description", "particulars", "particular"],
            "unit": ["unit", "uom", "measure", "measurement", "unit_of_measure"],
            "quantity": ["quantity", "qty", "qty.", "quantities", "total qty"],
            "unit_rate": ["unit_rate", "unit rate", "rate", "price", "unit price", "rate per unit"],
            "material_rate": ["material_rate", "material rate", "material", "mat rate"],
            "labour_rate": ["labour_rate", "labour rate", "labor_rate", "labor rate", "labour", "labor"],
            "equipment_rate": ["equipment_rate", "equipment rate", "equipment", "plant rate"],
            "overhead_rate": ["overhead_rate", "overhead rate", "overhead", "oh rate"],
            "specification": ["specification", "spec", "specs", "technical spec"],
            "is_section_header": ["is_section_header", "section header", "section_header", "header", "section"],
            "sort_order": ["sort_order", "sort order", "order", "row order", "sequence"],
        }
        for i, h in enumerate(headers):
            cleaned = h.replace("-", "_").replace(".", "").strip().lower()
            for field, alternatives in aliases.items():
                if cleaned in alternatives:
                    col_map[field] = i
                    break

        if "item_number" not in col_map:
            raise ValidationError("Spreadsheet must have an 'item_number' column")
        if "description" not in col_map:
            raise ValidationError("Spreadsheet must have a 'description' column")

        unit_map = {e.value.lower(): e for e in UnitOfMeasure}
        imported = 0
        skipped = 0
        errors = []
        items_to_create = []

        for row_idx, row in enumerate(rows[1:], start=2):
            try:
                item_number = str(row[col_map["item_number"]] or "").strip()
                description = str(row[col_map["description"]] or "").strip()
                if not item_number or not description:
                    skipped += 1
                    continue

                raw_unit = str(row[col_map.get("unit", -1)] or "").strip().lower() if "unit" in col_map else ""
                unit = unit_map.get(raw_unit, UnitOfMeasure.NOS)

                quantity = float(row[col_map.get("quantity", -1)] or 0) if "quantity" in col_map else 0.0
                unit_rate = float(row[col_map.get("unit_rate", -1)] or 0) if "unit_rate" in col_map else 0.0
                material_rate = float(row[col_map.get("material_rate", -1)] or 0) if "material_rate" in col_map else 0.0
                labour_rate = float(row[col_map.get("labour_rate", -1)] or 0) if "labour_rate" in col_map else 0.0
                equipment_rate = float(row[col_map.get("equipment_rate", -1)] or 0) if "equipment_rate" in col_map else 0.0
                overhead_rate = float(row[col_map.get("overhead_rate", -1)] or 0) if "overhead_rate" in col_map else 0.0
                specification = str(row[col_map.get("specification", -1)] or "").strip() if "specification" in col_map else None
                raw_header = str(row[col_map.get("is_section_header", -1)] or "").strip().lower() if "is_section_header" in col_map else ""
                is_section_header = raw_header in ("yes", "true", "1", "y")
                sort_order = int(row[col_map.get("sort_order", -1)] or 0) if "sort_order" in col_map else 0

                if unit_rate == 0.0:
                    unit_rate = material_rate + labour_rate + equipment_rate + overhead_rate

                amount = round(quantity * unit_rate, 2)
                item = BOQItem(
                    item_number=item_number,
                    description=description,
                    specification=specification or None,
                    unit=unit,
                    quantity=quantity,
                    unit_rate=unit_rate,
                    amount=amount,
                    material_rate=material_rate,
                    labour_rate=labour_rate,
                    equipment_rate=equipment_rate,
                    overhead_rate=overhead_rate,
                    is_section_header=is_section_header,
                    sort_order=sort_order,
                    project_id=project_id,
                    budget_version_id=version_id,
                    tenant_id=self.tenant_id,
                    created_by=self.user_id,
                    actual_quantity=0.0,
                    actual_amount=0.0,
                    status=BOQItemStatus.DRAFT,
                )
                items_to_create.append(item)
                imported += 1
            except Exception as e:
                errors.append(f"Row {row_idx}: {e}")
                skipped += 1

        if items_to_create:
            self.db.add_all(items_to_create)
            await self.db.flush()
            await self._recalculate_version_totals(version_id)

        return {
            "imported": imported,
            "skipped": skipped,
            "errors": errors,
            "items": items_to_create,
        }

    async def _recalculate_version_totals(self, version_id: str) -> None:
        result = await self.db.execute(
            select(
                func.sum(BOQItem.material_rate * BOQItem.quantity).label("material"),
                func.sum(BOQItem.labour_rate * BOQItem.quantity).label("labour"),
                func.sum(BOQItem.equipment_rate * BOQItem.quantity).label("equipment"),
                func.sum(BOQItem.overhead_rate * BOQItem.quantity).label("overhead"),
                func.sum(BOQItem.amount).label("total"),
            ).where(
                and_(
                    BOQItem.budget_version_id == version_id,
                    BOQItem.deleted_at.is_(None),
                    BOQItem.is_section_header.is_(False),
                )
            )
        )
        row = result.one()
        mat = row.material or 0.0
        lab = row.labour or 0.0
        eqp = row.equipment or 0.0
        ovh = row.overhead or 0.0
        total = row.total or 0.0

        bv_result = await self.db.execute(
            select(BudgetVersion).where(BudgetVersion.id == version_id)
        )
        bv = bv_result.scalar_one()
        contingency = round(total * bv.contingency_percentage / 100, 2)

        await self.db.execute(
            update(BudgetVersion)
            .where(BudgetVersion.id == version_id)
            .values(
                total_material_cost=round(mat, 2),
                total_labour_cost=round(lab, 2),
                total_equipment_cost=round(eqp, 2),
                total_overhead=round(ovh, 2),
                total_amount=round(total, 2),
                contingency_amount=contingency,
                grand_total=round(total + contingency, 2),
            )
        )

    # ── Rate Analysis ─────────────────────────────────────────────

    async def create_rate_analysis(self, data: CreateRateAnalysisRequest) -> RateAnalysis:
        await self.get_cost_code(data.cost_code_id)

        components_data = data.components
        ra_data = data.model_dump(exclude={"components"})

        ra = RateAnalysis(
            **ra_data,
            tenant_id=self.tenant_id,
            created_by=self.user_id,
        )
        self.db.add(ra)
        await self.db.flush()

        total_mat = total_lab = total_eqp = 0.0
        for comp_data in components_data:
            amount = round(
                comp_data.quantity * comp_data.rate * (1 + comp_data.wastage_percentage / 100),
                2
            )
            comp = RateAnalysisComponent(
                **comp_data.model_dump(),
                rate_analysis_id=ra.id,
                tenant_id=self.tenant_id,
                amount=amount,
                created_by=self.user_id,
            )
            self.db.add(comp)
            if comp_data.component_type.value == "material":
                total_mat += amount
            elif comp_data.component_type.value == "labour":
                total_lab += amount
            else:
                total_eqp += amount

        subtotal = total_mat + total_lab + total_eqp
        overhead = round(subtotal * ra.overhead_percentage / 100, 2)
        unit_rate = round((subtotal + overhead) / max(ra.output_quantity, 1), 2)

        ra.total_material = round(total_mat, 2)
        ra.total_labour = round(total_lab, 2)
        ra.total_equipment = round(total_eqp, 2)
        ra.overhead_amount = overhead
        ra.unit_rate = unit_rate
        await self.db.flush()
        result = await self.db.execute(
            select(RateAnalysis)
            .options(selectinload(RateAnalysis.components))
            .where(and_(
                RateAnalysis.id == ra.id,
                RateAnalysis.tenant_id == self.tenant_id,
                RateAnalysis.deleted_at.is_(None),
            ))
        )
        return result.scalar_one()

    async def list_rate_analyses(self, cost_code_id: str) -> list[RateAnalysis]:
        result = await self.db.execute(
            select(RateAnalysis)
            .options(selectinload(RateAnalysis.components))
            .where(
                and_(
                    RateAnalysis.cost_code_id == cost_code_id,
                    RateAnalysis.tenant_id == self.tenant_id,
                    RateAnalysis.deleted_at.is_(None),
                )
            )
        )
        return list(result.scalars().all())

    async def get_boq_summary(self, version_id: str) -> dict:
        bv = await self.get_budget_version(version_id)
        items_count_result = await self.db.execute(
            select(func.count(BOQItem.id)).where(
                and_(
                    BOQItem.budget_version_id == version_id,
                    BOQItem.deleted_at.is_(None),
                    BOQItem.is_section_header.is_(False),
                )
            )
        )
        items_count = items_count_result.scalar_one() or 0

        # Actual vs planned for each item
        variance_result = await self.db.execute(
            select(
                func.sum(BOQItem.amount).label("planned"),
                func.sum(BOQItem.actual_amount).label("actual"),
            ).where(
                and_(
                    BOQItem.budget_version_id == version_id,
                    BOQItem.deleted_at.is_(None),
                    BOQItem.is_section_header.is_(False),
                )
            )
        )
        v = variance_result.one()
        return {
            "version_id": version_id,
            "version_number": bv.version_number,
            "status": bv.status,
            "grand_total": bv.grand_total,
            "total_amount": bv.total_amount,
            "contingency_amount": bv.contingency_amount,
            "total_material_cost": bv.total_material_cost,
            "total_labour_cost": bv.total_labour_cost,
            "total_equipment_cost": bv.total_equipment_cost,
            "items_count": items_count,
            "planned_total": v.planned or 0.0,
            "actual_total": v.actual or 0.0,
            "variance": round((v.planned or 0.0) - (v.actual or 0.0), 2),
        }
