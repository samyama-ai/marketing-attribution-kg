"""The world the ledger describes — one brand, and the things it can measure.

Split out of `generate.py` so the generator holds the *findings* and this holds
the *cast*. Nothing here is a finding: no situation is planted in this file, and
changing a SKU name or adding a DMA cannot move one. That separation is the
point — the fifteen planted situations live next door, where they can be read
without scrolling past two hundred lines of reference data.

**Everything here is invented.** No real brand, no real client, no scraped data.

Imported by `data/generate.py`. No third-party dependency, and no imports at all.
"""

from __future__ import annotations

# --------------------------------------------------------------------------
# The brand
# --------------------------------------------------------------------------
#: A gifting-led home fragrance brand. Seasonal on purpose: a year dominated by
#: one peak is where methods disagree hardest, and disagree for a reason nobody
#: can see — a model fitted across peak-shaped demand reads an off-peak channel
#: through peak-shaped coefficients.
BRAND = "Halden & Co."

#: Eight quarters, because two cannot demonstrate compounding — "what did we
#: learn last quarter that still applies?" needs something to have been learned.
#: The two named below carry every planted finding; the other six are history.
#: id, season, is_peak, starts, ends, planning_cycle
#:
#: **The cycle is stated here rather than derived at load time.** It used to be
#: `cycles[0] if period_id < "2026-Q2" else cycles[-1]`, and every period this
#: brand has sorts below "2026-Q2" — so all eight landed in FY26 Q1 planning and
#: FY26 Q2 planning ended up with no periods at all. A rule that reads as a
#: boundary but has no boundary in range is worse than a column.
#:
#: The six history quarters belong to no cycle on purpose: both cycles are FY26,
#: and a 2024 quarter was not planned in them. Only the two quarters the demo
#: actually reasons about are in scope — Q1 planning reviews the Q4 results, Q2
#: planning reviews Q1.
PERIODS = [
    ("2024-Q2", "off_peak", "false", "2024-04-01", "2024-06-30", ""),
    ("2024-Q3", "shoulder", "false", "2024-07-01", "2024-09-30", ""),
    ("2024-Q4", "gifting", "true", "2024-10-01", "2024-12-31", ""),
    ("2025-Q1", "off_peak", "false", "2025-01-01", "2025-03-31", ""),
    ("2025-Q2", "off_peak", "false", "2025-04-01", "2025-06-30", ""),
    ("2025-Q3", "shoulder", "false", "2025-07-01", "2025-09-30", ""),
    ("2025-Q4", "gifting", "true", "2025-10-01", "2025-12-31",
     "FY26|Q1 planning"),
    ("2026-Q1", "off_peak", "false", "2026-01-01", "2026-03-31",
     "FY26|Q2 planning"),
]

#: The five named SKUs carry the podcast reversal. The rest are catalogue — a
#: DTC brand of this size has dozens, and a finding that only has to be picked
#: out of five products is not much of a finding.
NAMED_PRODUCTS = [
    ("SKU-101", "Signature Candle"),
    ("SKU-102", "Reed Diffuser"),
    ("SKU-103", "Gift Set Trio"),
    ("SKU-104", "Refill Pack"),
    ("SKU-105", "Travel Tin"),
]

_LINES = ["Amber", "Cedar", "Fig", "Linen", "Neroli", "Oakmoss", "Petitgrain",
          "Saffron", "Tobacco", "Vetiver", "Wild Mint", "Yuzu"]
_FORMS = ["Candle", "Diffuser", "Room Spray", "Refill", "Travel Tin"]

PRODUCTS = NAMED_PRODUCTS + [
    (f"SKU-{200 + i}", f"{line} {form}")
    for i, (line, form) in enumerate(
        (line, form) for line in _LINES for form in _FORMS)
]

SEGMENTS = [("Full-Price",), ("Discount",)]

#: name, funnel_stage
CHANNELS = [
    ("Paid Search", "lower"),
    ("Paid Social", "lower"),
    ("CTV", "upper"),
    ("Podcast", "upper"),
    ("Affiliate", "lower"),
    ("Email", "lower"),
    ("Organic", "lower"),
    ("Display", "lower"),
]

#: id, kind, name, observes
METHODS = [
    ("mmm|Northlight MMM", "mmm", "Northlight MMM", "modelled"),
    ("geo|Northlight Geo", "geo", "Northlight Geo", "experimental"),
    ("incrementality|Holdout Lab", "incrementality", "Holdout Lab",
     "experimental"),
    ("platform|Platform Reported", "platform", "Platform Reported", "clicks"),
    ("multiplier|Calibrated Multiplier", "multiplier",
     "Calibrated Multiplier", "modelled"),
]

#: US DMAs, as geo tests are actually designed. Named generically because the
#: brand is invented and the market names would imply a real footprint.
MARKETS = [(f"DMA-{500 + i}", f"Market {500 + i}",
            "dma") for i in range(210)]

SOURCES = [
    ("src-platform-api", "Ad platform APIs"),
    ("src-warehouse", "Brand data warehouse"),
    ("src-panel", "Consumer panel provider"),
    ("src-pos", "Point of sale"),
]

# --------------------------------------------------------------------------
# Lineage — depth is the point
# --------------------------------------------------------------------------
#: id, name, window, refreshed_on, derived_from, source
#:
#: Depths run 1 to 4. If every dataset pointed straight at a source the
#: provenance and blast-radius traversals would collapse to one hop and prove
#: nothing — that is finding 5 and it is the reason this table looks fussy.
#:
#: `ds-panel-raw` is the STALE one: it stopped refreshing in October and four
#: booked lines still stand on it, at four different depths.
DATASETS = [
    ("ds-platform-daily", "Platform daily spend & clicks", "2025-10..2026-03",
     "2026-04-02", "", "src-platform-api"),
    ("ds-pos-orders", "POS order lines", "2025-10..2026-03",
     "2026-04-02", "", "src-pos"),
    ("ds-panel-raw", "Consumer panel raw", "2024-10..2025-09",
     "2025-10-14", "", "src-panel"),                       # STALE
    ("ds-panel-weekly", "Panel weekly aggregate", "2024-10..2025-09",
     "2025-10-15", "ds-panel-raw", ""),
    ("ds-mmm-input", "MMM modelling frame", "2024-10..2025-12",
     "2026-01-08", "ds-panel-weekly", ""),
    ("ds-mmm-input-q1", "MMM modelling frame, refit", "2024-10..2026-03",
     "2026-04-06", "ds-mmm-input", ""),
    ("ds-spend-extract", "Spend extract", "2025-10..2026-03",
     "2026-04-03", "ds-platform-daily", ""),
    ("ds-geo-frame", "Geo test frame", "2026-01..2026-03",
     "2026-04-05", "ds-pos-orders", ""),
    ("ds-holdout-frame", "Holdout frame", "2026-01..2026-03",
     "2026-04-05", "ds-pos-orders", ""),
    ("ds-platform-reported", "Platform reported conversions",
     "2025-10..2026-03", "2026-04-02", "ds-platform-daily", ""),
]

# --------------------------------------------------------------------------
# Spend — without this nothing can end in a reallocation
# --------------------------------------------------------------------------
#: channel -> {period: amount}. Email is deliberately the smallest spend and
#: will turn out to have the best CAC (finding 12).
SPEND = {
    "Paid Search": {"2025-Q4": 4_200_000, "2026-Q1": 2_600_000},
    "Paid Social": {"2025-Q4": 3_100_000, "2026-Q1": 1_900_000},
    "CTV":         {"2025-Q4": 1_400_000, "2026-Q1": 900_000},
    "Podcast":     {"2025-Q4": 620_000,   "2026-Q1": 480_000},
    "Affiliate":   {"2025-Q4": 1_050_000, "2026-Q1": 700_000},
    "Email":       {"2025-Q4": 180_000,   "2026-Q1": 140_000},
    "Organic":     {"2025-Q4": 90_000,    "2026-Q1": 80_000},
    "Display":     {"2025-Q4": 760_000,   "2026-Q1": 520_000},
}
