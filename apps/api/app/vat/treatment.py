"""Transaction geography → VAT treatment assessment.

From the two assessed parties (supplier = vendor, recipient = customer) and the
document, classify the transaction (local / export / import / GCC / out-of-scope) and
identify what must be reviewed before a treatment can be relied upon.

Guiding rule (section 14 of the spec — "do not assume"): an overseas party does NOT
automatically mean 0%. Cross-border cases return **review reasons** so the verdict is
REVIEW (place of supply / evidence required), never a fabricated rate.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .parties import is_gcc
from .schemas import Invoice, InvoiceType, TransactionType, VatTreatment


@dataclass
class TransactionAssessment:
    transaction_type: TransactionType
    place_of_supply: str | None = None
    direction: str = ""                       # human-readable direction
    review_reasons: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# Keywords that hint the supply is a service (place-of-supply rules differ from goods).
_SERVICE_HINTS = (
    "service", "consult", "advis", "legal", "audit", "design", "engineering",
    "management", "marketing", "software", "license", "subscription", "rent", "lease",
    "professional", "training", "maintenance", "supervision",
)


def _looks_like_service(inv: Invoice) -> bool:
    blob = " ".join(
        (li.description or "") for li in inv.line_items
    ).lower() + " " + (inv.notes or "").lower()
    return any(h in blob for h in _SERVICE_HINTS)


def assess_transaction(inv: Invoice) -> TransactionAssessment:
    """Classify the transaction from the parties' geography and flag what needs review.

    supplier = vendor/issuer of a sales invoice; recipient = customer.
    """
    sup_uae = inv.supplier.is_uae
    rec_uae = inv.recipient.is_uae
    sup_country = inv.supplier.country or "unknown"
    rec_country = inv.recipient.country or "unknown"
    is_credit_debit = inv.invoice_type in (InvoiceType.CREDIT_NOTE, InvoiceType.DEBIT_NOTE)

    a = TransactionAssessment(transaction_type=TransactionType.UNKNOWN)

    # Both sides UAE → domestic supply.
    if sup_uae is True and rec_uae is True:
        a.transaction_type = TransactionType.LOCAL
        a.place_of_supply = "UAE (domestic supply)"
        a.direction = "UAE supplier → UAE customer"
        return a

    # UAE supplier → overseas customer: potential export / international service.
    if sup_uae is True and rec_uae is False:
        service = _looks_like_service(inv)
        if is_gcc(rec_country):
            a.transaction_type = TransactionType.GCC
            a.direction = f"UAE supplier → GCC customer ({rec_country})"
            a.review_reasons.append(
                f"Cross-border GCC supply to {rec_country}: confirm place of supply and whether "
                "zero-rating or the destination-state treatment applies (GCC VAT framework)."
            )
        else:
            a.transaction_type = TransactionType.EXPORT
            a.direction = f"UAE supplier → overseas customer ({rec_country})"
            if service:
                a.place_of_supply = "Assess — international service (place-of-supply rules apply)"
                a.review_reasons.append(
                    f"Export of services to {rec_country}: zero-rating depends on place of supply "
                    "and the recipient having no UAE presence — confirm and retain evidence."
                )
            else:
                a.place_of_supply = "Assess — export of goods"
                a.review_reasons.append(
                    f"Export of goods to {rec_country}: zero-rating requires official + commercial "
                    "export evidence within 90 days — do not assume 0% without it."
                )
        return a

    # Overseas supplier → UAE customer: import / reverse charge.
    if sup_uae is False and rec_uae is True:
        service = _looks_like_service(inv)
        a.transaction_type = TransactionType.IMPORT
        a.direction = f"Overseas supplier ({sup_country}) → UAE customer"
        a.place_of_supply = "UAE (import — recipient accounts for VAT)"
        a.review_reasons.append(
            "Import from an overseas supplier: the UAE recipient likely self-accounts under the "
            "reverse-charge mechanism (output + recoverable input VAT). "
            + ("Confirm import VAT / customs treatment for goods." if not service
               else "Confirm reverse charge on imported services.")
        )
        return a

    # Both sides overseas → no UAE nexus on the face of it.
    if sup_uae is False and rec_uae is False:
        a.transaction_type = TransactionType.UNKNOWN
        a.direction = f"Overseas ({sup_country}) → overseas ({rec_country})"
        a.review_reasons.append(
            "No UAE party detected: likely outside the scope of UAE VAT, but confirm neither party "
            "has a UAE establishment and the supply has no UAE place of supply."
        )
        return a

    # Anything undetermined (a side's country unknown) → must be reviewed, not guessed.
    if sup_uae is None or rec_uae is None:
        a.transaction_type = TransactionType.UNKNOWN
        a.direction = f"{sup_country} → {rec_country}"
        unknown_side = "supplier/vendor" if sup_uae is None else "customer"
        if sup_uae is None and rec_uae is None:
            unknown_side = "both parties"
        a.review_reasons.append(
            f"Location of {unknown_side} could not be determined — establish country and UAE "
            "presence before concluding the VAT treatment."
        )
    return a


def expected_rate_note(treatment: VatTreatment | None) -> str:
    return {
        VatTreatment.STANDARD: "5% standard-rated",
        VatTreatment.ZERO_RATED: "0% zero-rated (evidence required)",
        VatTreatment.EXEMPT: "Exempt (no input recovery)",
        VatTreatment.OUT_OF_SCOPE: "Out of scope of UAE VAT",
        VatTreatment.REVERSE_CHARGE: "Reverse charge (recipient self-accounts)",
    }.get(treatment, "Treatment not determined")
