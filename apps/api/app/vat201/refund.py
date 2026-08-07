"""VAT311 — FTA VAT Refund application, prepared from a VAT201 return.

VAT311 is filed when a VAT201 return leaves the taxpayer in a net refundable
position (excess recoverable input tax). It declares the total excess, how much of
it to reclaim now, what remains to carry forward, and offsets any unpaid late-
registration penalty.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from pydantic import BaseModel


def _q(v: Decimal) -> str:
    return str(v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


class Vat311Application(BaseModel):
    trn: str | None = None
    legal_name: str | None = None
    period_label: str | None = None
    total_excess_refundable: str = "0"
    amount_requested: str = "0"
    remaining_excess: str = "0"
    late_registration_penalty: str = "0"
    net_refund_expected: str = "0"
    authorized_signatory: str | None = None
    declaration_date: str | None = None
    generated_at: str | None = None


def _dec(v, default: str = "0") -> Decimal:
    try:
        return Decimal(str(v)) if v not in (None, "") else Decimal(default)
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(default)


def prepare_refund311(
    *,
    is_refund: bool,
    net_vat_due: str,
    trn: str | None,
    company_name: str | None,
    period_label: str | None,
    amount_requested=None,
    late_registration_penalty="0",
    legal_name: str | None = None,
    authorized_signatory: str | None = None,
    declaration_date: str | None = None,
) -> Vat311Application:
    if not is_refund:
        raise ValueError("This return is not in a refund position — VAT311 does not apply.")
    total = _dec(net_vat_due)
    if total <= 0:
        raise ValueError("No excess refundable tax on this return.")
    requested = _dec(amount_requested, str(total)) if amount_requested is not None else total
    if requested <= 0 or requested > total:
        raise ValueError(f"Amount requested must be between 0 and {total}.")
    penalty = max(Decimal(0), _dec(late_registration_penalty))
    remaining = total - requested
    net_refund = max(Decimal(0), requested - penalty)

    return Vat311Application(
        trn=trn,
        legal_name=legal_name or company_name,
        period_label=period_label,
        total_excess_refundable=_q(total),
        amount_requested=_q(requested),
        remaining_excess=_q(remaining),
        late_registration_penalty=_q(penalty),
        net_refund_expected=_q(net_refund),
        authorized_signatory=authorized_signatory,
        declaration_date=declaration_date,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )
