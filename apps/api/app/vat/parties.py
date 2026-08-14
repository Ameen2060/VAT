"""Party (customer/vendor) geography & VAT-registration assessment.

Given an extracted :class:`PartyDetails`, determine the party's country, whether it
is inside or outside the UAE, and its UAE-VAT-registration status — with the crucial
rule that an **overseas** party legitimately has no UAE TRN, so a missing TRN there is
"Not applicable", never a compliance failure. A **UAE** party with no TRN is flagged
for review.

Detection is heuristic and evidence-based (address text, explicit country labels, the
presence of a UAE 15-digit TRN); when the country cannot be determined it says so
("Unknown — review required") rather than guessing, per the "do not assume" rule.
"""

from __future__ import annotations

import re

# UAE indicators: the federation, its emirates, and common variants/free zones.
_UAE_TOKENS = (
    "united arab emirates", "u.a.e", "uae", "abu dhabi", "dubai", "sharjah",
    "ajman", "umm al quwain", "umm al-quwain", "ras al khaimah", "ras al-khaimah",
    "fujairah", "al ain", "jebel ali", "jafza", "difc", "adgm", "dmcc",
)

# Other countries we can name from address/label text. GCC members are marked so the
# treatment engine can reason about GCC vs. rest-of-world. Order matters only for
# display; matching is whole-word/substring on a normalised string.
_GCC = {
    "saudi arabia": ("Saudi Arabia", True), "ksa": ("Saudi Arabia", True),
    "kingdom of saudi": ("Saudi Arabia", True),
    "kuwait": ("Kuwait", True), "bahrain": ("Bahrain", True),
    "oman": ("Oman", True), "sultanate of oman": ("Oman", True),
    "qatar": ("Qatar", True),
}
_WORLD = {
    "united kingdom": "United Kingdom", "england": "United Kingdom", "scotland": "United Kingdom",
    "u.k": "United Kingdom", "uk": "United Kingdom", "london": "United Kingdom",
    "united states": "United States", "usa": "United States", "u.s.a": "United States",
    "america": "United States", "new york": "United States",
    "india": "India", "mumbai": "India", "delhi": "India", "bangalore": "India",
    "china": "China", "hong kong": "Hong Kong", "singapore": "Singapore",
    "germany": "Germany", "france": "France", "italy": "Italy", "spain": "Spain",
    "netherlands": "Netherlands", "switzerland": "Switzerland", "ireland": "Ireland",
    "canada": "Canada", "australia": "Australia", "japan": "Japan",
    "pakistan": "Pakistan", "bangladesh": "Bangladesh", "egypt": "Egypt",
    "jordan": "Jordan", "lebanon": "Lebanon", "turkey": "Turkey", "turkiye": "Turkey",
    "philippines": "Philippines", "south africa": "South Africa", "nigeria": "Nigeria",
    "syria": "Syria", "rif dimashq": "Syria", "damascus": "Syria", "aleppo": "Syria",
    "iraq": "Iraq", "baghdad": "Iraq", "yemen": "Yemen", "sudan": "Sudan",
    "iran": "Iran", "tehran": "Iran", "morocco": "Morocco", "algeria": "Algeria",
    "tunisia": "Tunisia", "libya": "Libya", "russia": "Russia", "ukraine": "Ukraine",
    "brazil": "Brazil", "indonesia": "Indonesia", "malaysia": "Malaysia",
    "kuala lumpur": "Malaysia", "thailand": "Thailand", "vietnam": "Vietnam",
    "south korea": "South Korea", "korea": "South Korea", "sri lanka": "Sri Lanka",
    "nepal": "Nepal", "kenya": "Kenya", "ghana": "Ghana", "greece": "Greece",
    "belgium": "Belgium", "sweden": "Sweden", "norway": "Norway", "denmark": "Denmark",
    "poland": "Poland", "portugal": "Portugal", "austria": "Austria",
    "new zealand": "New Zealand", "mexico": "Mexico",
}

_TRN_RE = re.compile(r"\b\d{15}\b")


def _norm(s: str | None) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower())


def detect_country(address: str | None, trn: str | None, name: str | None = None) -> tuple[str | None, bool | None]:
    """Return ``(country, is_uae)``.

    ``is_uae`` is True (inside UAE), False (outside UAE), or None (undetermined).
    A UAE 15-digit TRN is treated as evidence of UAE establishment **only** when no
    foreign country is named (an overseas party may quote a UAE TRN of its customer).
    """
    hay = _norm(f"{address or ''} {name or ''}")

    # 1. Explicit foreign country wins over a UAE token if both somehow appear in the
    #    party's own block (rare) — but UAE emirates are strong local signals, so check
    #    a *named foreign country* first only when no UAE emirate token is present.
    uae_hit = any(f" {t} " in f" {hay} " for t in _UAE_TOKENS)

    for key, (country, _gcc) in _GCC.items():
        if re.search(rf"\b{re.escape(key)}\b", hay):
            return country, False
    for key, country in _WORLD.items():
        if re.search(rf"\b{re.escape(key)}\b", hay):
            return country, False

    if uae_hit:
        return "United Arab Emirates", True

    # 2. A valid UAE TRN with no foreign signal → treat as UAE-established.
    if trn and _TRN_RE.search(str(trn)):
        return "United Arab Emirates", True

    return None, None


def is_gcc(country: str | None) -> bool:
    return bool(country) and any(country == c for c, _ in _GCC.values())


def _valid_uae_trn(trn: str | None) -> bool:
    if not trn:
        return False
    digits = "".join(ch for ch in str(trn) if ch.isdigit())
    return len(digits) == 15


def assess_party(party) -> None:
    """Populate ``country``, ``is_uae`` and ``vat_registration_status`` on a
    :class:`PartyDetails` in place. Never flags an overseas party for a missing UAE TRN.
    """
    country, is_uae = detect_country(party.address, party.trn, party.name)
    party.country = country
    party.is_uae = is_uae

    has_trn = _valid_uae_trn(party.trn)
    if is_uae is True:
        party.vat_registration_status = (
            "Registered (UAE TRN present)" if has_trn
            else "UAE entity — TRN missing / review required"
        )
    elif is_uae is False:
        # Overseas: a UAE TRN is not expected. If one is nonetheless present, note it.
        party.vat_registration_status = (
            "UAE TRN present (overseas party)" if has_trn
            else "Not applicable — outside UAE"
        )
    else:
        party.vat_registration_status = (
            "Registered (UAE TRN present)" if has_trn
            else "Unknown — country not detected, review required"
        )
