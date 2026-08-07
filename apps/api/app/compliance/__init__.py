"""Regime-agnostic compliance primitives.

Shared building blocks used by every tax regime the platform reviews (VAT today,
Corporate Tax next). Nothing in here is VAT-specific — regime-specific domain models
(e.g. `vat.schemas.Invoice`, `ct.schemas.CorporateTaxReturn`) build on top of these.
"""

from __future__ import annotations

from .domain import (
    ComplianceStatus,
    Finding,
    Party,
    Regime,
    ReviewResultBase,
    RiskLevel,
    Severity,
    ValidationCheck,
    VerificationItem,
    status_and_risk,
)

__all__ = [
    "ComplianceStatus",
    "Finding",
    "Party",
    "Regime",
    "ReviewResultBase",
    "RiskLevel",
    "Severity",
    "ValidationCheck",
    "VerificationItem",
    "status_and_risk",
]
