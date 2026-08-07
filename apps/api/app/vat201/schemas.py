"""VAT201 domain types."""

from __future__ import annotations

from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field


class Direction(str, Enum):
    SALE = "sale"          # output / supplies
    PURCHASE = "purchase"  # input / expenses


class Treatment(str, Enum):
    STANDARD = "standard"          # 5%
    ZERO_RATED = "zero_rated"      # 0%
    EXEMPT = "exempt"
    REVERSE_CHARGE = "reverse_charge"
    IMPORT = "import"
    OUT_OF_SCOPE = "out_of_scope"


class Emirate(str, Enum):
    ABU_DHABI = "abu_dhabi"
    DUBAI = "dubai"
    SHARJAH = "sharjah"
    AJMAN = "ajman"
    UMM_AL_QUWAIN = "umm_al_quwain"
    RAS_AL_KHAIMAH = "ras_al_khaimah"
    FUJAIRAH = "fujairah"
    UNALLOCATED = "unallocated"


# Canonical VAT201 boxes, in report order.
BOX_LABELS: dict[str, str] = {
    "1a": "Standard rated supplies — Abu Dhabi",
    "1b": "Standard rated supplies — Dubai",
    "1c": "Standard rated supplies — Sharjah",
    "1d": "Standard rated supplies — Ajman",
    "1e": "Standard rated supplies — Umm Al Quwain",
    "1f": "Standard rated supplies — Ras Al Khaimah",
    "1g": "Standard rated supplies — Fujairah",
    "2": "Tax refunds to tourists",
    "3": "Supplies subject to the reverse charge",
    "4": "Zero rated supplies",
    "5": "Exempt supplies",
    "6": "Goods imported into the UAE",
    "7": "Adjustments to goods imported into the UAE",
    "8": "Totals (supplies / output)",
    "9": "Standard rated expenses",
    "10": "Supplies subject to the reverse charge (recoverable)",
    "11": "Totals (expenses / input)",
    "12": "Total value of due tax for the period",
    "13": "Total value of recoverable tax for the period",
    "14": "Net VAT due (payable / reclaimable)",
}

EMIRATE_BOX: dict[Emirate, str] = {
    Emirate.ABU_DHABI: "1a",
    Emirate.DUBAI: "1b",
    Emirate.SHARJAH: "1c",
    Emirate.AJMAN: "1d",
    Emirate.UMM_AL_QUWAIN: "1e",
    Emirate.RAS_AL_KHAIMAH: "1f",
    Emirate.FUJAIRAH: "1g",
}

SALES_BOXES = ["1a", "1b", "1c", "1d", "1e", "1f", "1g", "2", "3", "4", "5", "6", "7"]
EXPENSE_BOXES = ["9", "10"]


class Transaction(BaseModel):
    row_index: int
    date: str | None = None
    doc_type: str | None = None
    direction: Direction | None = None
    party: str | None = None
    trn: str | None = None
    invoice_number: str | None = None
    emirate: Emirate = Emirate.UNALLOCATED
    treatment: Treatment | None = None
    vat_rate: Decimal | None = None
    taxable_amount: Decimal = Decimal(0)
    vat_amount: Decimal = Decimal(0)
    boxes: list[str] = Field(default_factory=list)  # boxes this txn contributes to
    raw: dict = Field(default_factory=dict)


class BoxValue(BaseModel):
    box: str
    label: str
    amount: Decimal = Decimal(0)   # taxable value
    vat: Decimal = Decimal(0)
    count: int = 0


class ValidationIssue(BaseModel):
    severity: str          # error | warning
    code: str
    message: str
    row_index: int | None = None
    invoice_number: str | None = None


class Vat201Totals(BaseModel):
    total_sales_taxable: Decimal = Decimal(0)
    output_vat: Decimal = Decimal(0)
    reverse_charge_vat: Decimal = Decimal(0)
    total_expenses_taxable: Decimal = Decimal(0)
    recoverable_input_vat: Decimal = Decimal(0)
    net_vat_due: Decimal = Decimal(0)
    is_refund: bool = False


class Vat201Return(BaseModel):
    company_name: str | None = None
    company_trn: str | None = None
    currency: str = "AED"
    period_type: str = "quarter"     # month | quarter
    period_label: str = ""
    period_start: str | None = None
    period_end: str | None = None
    due_date: str | None = None
    boxes: list[BoxValue] = Field(default_factory=list)
    totals: Vat201Totals = Field(default_factory=Vat201Totals)
    validations: list[ValidationIssue] = Field(default_factory=list)
    transaction_count: int = 0
