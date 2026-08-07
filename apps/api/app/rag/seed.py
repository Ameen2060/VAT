"""Seed knowledge base: concise, cited summaries of key UAE VAT provisions.

These are paraphrased reference notes (not verbatim legislative text) authored to
give the RAG assistant a grounded starting corpus with proper citations. Users
should ingest the official FTA PDFs/guides for authoritative wording — this seed is
a scaffold, and each entry names the source article to check.
"""

from __future__ import annotations

SEED_ENTRIES: list[dict] = [
    {
        "title": "Standard rate and scope of VAT",
        "source_ref": "Art. 2–3, Federal Decree-Law No. 8 of 2017",
        "text": (
            "VAT applies to most supplies of goods and services made in the UAE and to "
            "imports. The standard rate is 5%. A taxable supply is one made by a taxable "
            "person for consideration in the course of business, other than an exempt "
            "supply. Supplies are classified as standard-rated (5%), zero-rated (0%), "
            "exempt (no VAT, no input recovery), or outside the scope of UAE VAT."
        ),
    },
    {
        "title": "Registration thresholds",
        "source_ref": "Art. 13 & 17, Federal Decree-Law No. 8 of 2017",
        "text": (
            "Registration is mandatory where taxable supplies and imports in the previous "
            "12 months exceeded AED 375,000, or are expected to exceed it in the next 30 "
            "days. Voluntary registration is available at AED 187,500 of supplies or "
            "taxable expenses. A Tax Registration Number (TRN) is 15 digits."
        ),
    },
    {
        "title": "Mandatory particulars of a full tax invoice",
        "source_ref": "Art. 59(1), Executive Regulation (Cabinet Decision 52 of 2017)",
        "text": (
            "A full tax invoice must clearly display 'Tax Invoice'; the supplier's name, "
            "address and TRN; the recipient's name, address and TRN where registered; a "
            "sequential invoice number; the date of issue (and date of supply if "
            "different); a description of the goods or services; for each line the unit "
            "price, quantity, tax rate and amount payable in AED; any discount; the total "
            "consideration and total tax in AED; and, where currency is other than AED, "
            "the exchange rate. Where the reverse charge applies, a statement to that "
            "effect must appear."
        ),
    },
    {
        "title": "Simplified tax invoice",
        "source_ref": "Art. 59(5), Executive Regulation (Cabinet Decision 52 of 2017)",
        "text": (
            "A simplified tax invoice may be issued where the recipient is not registered "
            "for VAT, or where the recipient is registered but the consideration does not "
            "exceed AED 10,000. It shows 'Tax Invoice', the supplier's name/address/TRN, "
            "the date of issue, a description, and the total consideration and tax amount."
        ),
    },
    {
        "title": "Reverse charge mechanism",
        "source_ref": "Art. 48, Federal Decree-Law No. 8 of 2017",
        "text": (
            "Under the reverse charge, the registered recipient accounts for both output "
            "and input VAT instead of the supplier charging it. It applies to, among "
            "others, the import of concerned goods and services (including cross-border "
            "digital services, SaaS, cloud subscriptions and overseas consultancy) and to "
            "certain domestic supplies of crude/refined oil, gas and hydrocarbons between "
            "registrants. The supplier does not charge UAE VAT; the recipient self-"
            "assesses and may recover the input VAT in the same return if recoverable."
        ),
    },
    {
        "title": "Zero-rated supplies",
        "source_ref": "Art. 45, Federal Decree-Law No. 8 of 2017; Art. 30–34 ER",
        "text": (
            "Zero-rating (0% with input recovery) applies to direct and indirect exports "
            "of goods outside the GCC implementing states, international transport of "
            "passengers and goods, certain means of transport, investment-grade precious "
            "metals, the first supply of residential buildings within three years of "
            "completion, and qualifying education and healthcare. Exports must be "
            "supported by official and commercial evidence retained for audit."
        ),
    },
    {
        "title": "Exempt supplies",
        "source_ref": "Art. 46, Federal Decree-Law No. 8 of 2017; Art. 42 ER",
        "text": (
            "Exempt supplies carry no VAT and do not allow input tax recovery. They "
            "include certain financial services (margin-based, not fee-based), the supply "
            "of bare land, local passenger transport, and the lease/sale of residential "
            "buildings after the first supply. Input tax on costs used for exempt supplies "
            "is irrecoverable and may require apportionment."
        ),
    },
    {
        "title": "Input tax recovery and blocked input tax",
        "source_ref": "Art. 54–55 Decree-Law; Art. 53 Executive Regulation",
        "text": (
            "A registrant may recover input VAT on costs used to make taxable supplies, "
            "subject to holding a valid tax invoice and paying (or intending to pay) "
            "within six months. Input tax is blocked (non-recoverable) on entertainment "
            "provided to non-employees, on motor vehicles available for personal use, and "
            "on certain employee-related costs. Where costs relate to both taxable and "
            "exempt supplies, input tax must be apportioned."
        ),
    },
    {
        "title": "Import VAT",
        "source_ref": "Art. 48 & 50 Decree-Law; Art. 50 ER",
        "text": (
            "Import VAT is due on goods entering the UAE. A registered importer generally "
            "accounts for import VAT through the VAT return (reverse-charge style) rather "
            "than paying at the border, declaring it in the return period of import. The "
            "customs value plus duties forms the base. Records of customs declarations and "
            "import documentation must be retained."
        ),
    },
    {
        "title": "Designated Zones",
        "source_ref": "Art. 51, Federal Decree-Law No. 8 of 2017; Art. 51 ER",
        "text": (
            "A Designated Zone specified by Cabinet Decision is treated as outside the UAE "
            "for VAT on goods in defined circumstances. Supplies of goods within or between "
            "Designated Zones can be outside scope, but supplies of services within a "
            "Designated Zone are generally treated as made within the UAE and taxed "
            "normally. Goods consumed within a Designated Zone are treated as supplied in "
            "the UAE."
        ),
    },
    {
        "title": "Time of supply (tax point)",
        "source_ref": "Art. 25–26, Federal Decree-Law No. 8 of 2017",
        "text": (
            "The basic tax point is the earliest of: the date goods are transferred or "
            "services completed, the date of the tax invoice, or the date payment is "
            "received. Special rules apply to continuous supplies (earliest of invoice, "
            "payment, or 12 months) and to periodic payments."
        ),
    },
    {
        "title": "Credit and debit notes",
        "source_ref": "Art. 62, Federal Decree-Law No. 8 of 2017; Art. 60 ER",
        "text": (
            "Where the consideration or VAT on a supply changes (e.g. returns, discounts, "
            "cancellations), a tax credit note (or debit note) must be issued referencing "
            "the original tax invoice, showing the adjustment to the VAT, and provided to "
            "the recipient. The adjustment is reflected in the VAT return for the period "
            "in which it occurs."
        ),
    },
    {
        "title": "Record keeping and audit",
        "source_ref": "Art. 78 Decree-Law; Federal Decree-Law No. 28 of 2022 (Tax Procedures)",
        "text": (
            "Taxable persons must retain records — invoices, credit/debit notes, import/"
            "export and customs documents, accounting records and the VAT account — "
            "generally for five years (longer for real estate). Records must be available "
            "for FTA inspection and support every figure in the VAT return."
        ),
    },
]
