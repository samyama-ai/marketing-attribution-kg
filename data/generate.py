"""Generate the synthetic measurement ledger.

One seasonal DTC brand, two quarters, and every number invented. The point is
not the volume — it is that fifteen specific situations are PLANTED in the data
and the graph finds them without being told where to look.

**Everything here is synthetic and every node says so.** No real brand, no real
client, no scraped data. The situations are modelled on the *shape* of cases
published openly by practitioners in this field; no client is named, and none
of these numbers came from anyone.

Run:

    python data/generate.py            # writes data/csv/*.csv
    python data/verify_data_coverage.py

Seeded, so two runs produce identical files. If they ever differ, something
below started depending on iteration order and the planted findings can move.

No third-party dependency — csv and pathlib only.
"""

from __future__ import annotations

import csv
import hashlib
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

# The cast — brand, periods, products, channels, methods, markets, sources,
# datasets, spend. Kept next door so this file is only the planted findings.
# The background the findings sit in. Kept next door so this file reads as
# fifteen deliberate situations rather than as a data factory.
from corpus import bulk_claims, bulk_runs  # noqa: E402
from world import (  # noqa: E402
    BRAND, CHANNELS, DATASETS, MARKETS, METHODS, PERIODS, PRODUCTS,
    SEGMENTS, SOURCES, SPEND,
)

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "csv"

SYNTHETIC = "synthetic"



def claim_id(run: str, about: str, metric: str, period: str,
             granularity: str = "") -> str:
    """sha1(run + about + metric + period + granularity) — the key.

    Granularity is in the hash even though the schema's prose omits it. Without
    it, a channel-level claim and a channel+segment claim about the same
    channel, period and metric hash identically and one silently overwrites the
    other — which is exactly the affiliate finding, where both exist.

    Deterministic, because the constraint declares the key and does not enforce
    it. The loader minting ids from content is the only real uniqueness
    guarantee this engine allows.
    """
    raw = f"{run}|{about}|{metric}|{period}|{granularity}"
    return "clm-" + hashlib.sha1(raw.encode()).hexdigest()[:16]


def rows(name: str, header: list[str], data: list[tuple]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / f"{name}.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(data)
    print(f"  {name+'.csv':<26} {len(data):>4} rows")


# --------------------------------------------------------------------------
# Runs — a method at a time, with the window its data actually covered
# --------------------------------------------------------------------------
#: id, method, executed_on, observed_from, observed_to, dataset, geotest
#:
#: `run-mmm-q1` is the SEASONAL EXTRAPOLATION (finding 15): it makes claims
#: about 2026-Q1 while its data stops at 2025-12-31. It never observed the
#: quarter it describes. Legitimate sometimes, a silent error other times, and
#: invisible unless the observation window is held beside the claim's period.
#:
#: `run-plat-q1-early` is the PREMATURE RUN (finding 9): executed 2026-02-10,
#: producing claims about a quarter that closed on 2026-03-31.
#:
#: `run-geo-q1` and `run-inc-q1` look independent — different designs, both
#: experimental — and BOTH descend from ds-pos-orders (finding 7). Agreement
#: between them means the order table is consistent, not that the number is
#: right.
RUNS = [
    ("run-mmm-q4", "mmm|Northlight MMM", "2026-01-09",
     "2024-10-01", "2025-12-31", "ds-mmm-input", ""),
    ("run-mmm-q1", "mmm|Northlight MMM", "2026-04-07",
     "2024-10-01", "2025-12-31", "ds-mmm-input", ""),          # never saw Q1
    ("run-mmm-q1-refit", "mmm|Northlight MMM", "2026-04-20",
     "2024-10-01", "2026-03-31", "ds-mmm-input-q1", ""),
    ("run-geo-q1", "geo|Northlight Geo", "2026-04-11",
     "2026-01-01", "2026-03-31", "ds-geo-frame", "gt-paid-social-2026-01-06"),
    ("run-inc-q1", "incrementality|Holdout Lab", "2026-04-12",
     "2026-01-01", "2026-03-31", "ds-holdout-frame", ""),
    ("run-plat-q4", "platform|Platform Reported", "2026-01-05",
     "2025-10-01", "2025-12-31", "ds-platform-reported", ""),
    ("run-plat-q1", "platform|Platform Reported", "2026-04-04",
     "2026-01-01", "2026-03-31", "ds-platform-reported", ""),
    ("run-plat-q1-early", "platform|Platform Reported", "2026-02-10",
     "2026-01-01", "2026-02-09", "ds-platform-reported", ""),  # before close
    ("run-mult-q1", "multiplier|Calibrated Multiplier", "2026-04-14",
     "2026-01-01", "2026-03-31", "ds-spend-extract", ""),
    ("run-geo-ctv-q1", "geo|Northlight Geo", "2026-04-11",
     "2026-01-01", "2026-03-31", "ds-geo-frame", "gt-ctv-2026-02-02"),
    ("run-orphan", "mmm|Northlight MMM", "2026-03-02",
     "2025-10-01", "2026-02-28", "", ""),                      # no dataset
]

#: id, channel, design, mde, spend_delta_pct, started_on
#:
#: `mde` is why this label exists. A test underpowered for the effect it was
#: looking for returns a null meaning "we could not see it", not "it is not
#: there" — and for an off-peak channel with a small true effect that decides
#: whether a brand invests or walks away. A ledger that keeps the lift and
#: discards the design cannot tell those apart.
#: id, channel, design, mde, spend_delta_pct, started_on
#:
#: `channel` is carried here for readability and is deliberately NOT loaded as
#: an edge. The merged schema declares one relationship for this label —
#: (:Run)-[:EXECUTED_TEST]->(:GeoTest) — and the channel is already reachable
#: through it: GeoTest <- Run -> Claim -> Channel. Adding a second path would
#: mean two answers to "which channel was tested" that can disagree, and it
#: would extend a schema this PR does not own.
GEOTESTS = [
    ("gt-paid-social-2026-01-06", "Paid Social", "matched_market", 0.08,
     -100, "2026-01-06"),
    # Referenced by run-geo-ctv-q1 below. A GeoTest no run points at is a
    # design with no result — worth having in a real ledger, but here it was
    # simply unreferenced, which is a different thing and a bug.
    ("gt-ctv-2026-02-02", "CTV", "scaled_holdout", 0.22, -60, "2026-02-02"),
]

#: id, question, hypothesis, owner, status, run, cycle
#:
#: A run exists because someone asked a question. Storing the question beside
#: the answer is what lets the ledger say "we have answered this already"
#: instead of commissioning it again.
STUDIES = [
    ("stdy-paid-social-lift|2025-12-15",
     "Is paid social incremental off-peak?",
     "Peak-fitted MMM overstates paid social in Q1",
     "Analytics Lead", "complete", "run-geo-q1", "FY26|Q1 planning"),
    ("stdy-ctv-visibility|2026-01-20",
     "Can we see CTV at all with current methods?",
     "Click-based reporting is structurally blind to CTV",
     "CMO", "complete", "run-mmm-q1", "FY26|Q1 planning"),
    ("stdy-podcast-catalogue|2026-02-01",
     "Is podcast dead, or dead on average?",
     "Podcast works for gift-led SKUs only",
     "Analytics Lead", "complete", "run-mmm-q1-refit", "FY26|Q2 planning"),
]

#: id, fy, name, board_date, budget_locked_on
#:
#: The calendar the business actually decides on. A read that lands after
#: budget lock had no chance to influence anything, however good it was — and
#: for a seasonal brand, missing the lock means waiting a full year for the
#: next peak.
CYCLES = [
    ("FY26|Q1 planning", "FY26", "Q1 planning", "2026-01-28", "2026-02-06"),
    ("FY26|Q2 planning", "FY26", "Q2 planning", "2026-04-28", "2026-05-08"),
]


# --------------------------------------------------------------------------
# Claims — every planted finding lives in this table
# --------------------------------------------------------------------------
#: run, metric, value, granularity, period, channel, product, segment
#:
#: Written out rather than generated from a loop, deliberately. A loop would
#: make the numbers tidy and the findings accidental; here every value is
#: placed, and the table can be read against the question bank line by line.
CLAIMS = [
    # -- Paid Social: four methods, four answers -------------------------
    # The hero disagreement. MMM 2.0 vs geo 1.2 is a 40% gap on the MMM read,
    # and the platform number is the highest of all four (findings 4, 5).
    ("run-mmm-q1",        "contribution", 2_000_000, "channel", "2026-Q1",
     "Paid Social", "", ""),
    ("run-geo-q1",        "contribution", 1_200_000, "channel", "2026-Q1",
     "Paid Social", "", ""),
    ("run-inc-q1",        "contribution", 1_250_000, "channel", "2026-Q1",
     "Paid Social", "", ""),
    ("run-plat-q1",       "contribution", 2_600_000, "channel", "2026-Q1",
     "Paid Social", "", ""),
    ("run-mult-q1",       "contribution", 1_400_000, "channel", "2026-Q1",
     "Paid Social", "", ""),
    # the premature run — executed 2026-02-10, describing a quarter that
    # closed on 2026-03-31 (finding 9)
    ("run-plat-q1-early", "contribution", 2_400_000, "channel", "2026-Q1",
     "Paid Social", "", ""),

    # -- CTV: no platform claim exists, and cannot ------------------------
    # A click-based method is structurally blind to an upper-funnel channel.
    # The finding is the ABSENCE (finding 3). Note also that geo rates CTV
    # ABOVE paid social while MMM rates it below — the direction disagreement
    # that the reallocation question turns on (finding 13).
    ("run-mmm-q1",  "contribution",   900_000, "channel", "2026-Q1",
     "CTV", "", ""),
    ("run-geo-ctv-q1", "contribution", 1_150_000, "channel", "2026-Q1",
     "CTV", "", ""),

    # -- Podcast: dead on average, alive on two SKUs ----------------------
    # Channel level is 40k against 480k of spend — a rounding error, and the
    # obvious read is to cut it. The five product-level claims sum to the same
    # 40k, and two of them are strongly positive (finding 1).
    ("run-mmm-q1-refit", "contribution",    40_000, "channel", "2026-Q1",
     "Podcast", "", ""),
    ("run-mmm-q1-refit", "contribution",   310_000, "channel+product",
     "2026-Q1", "Podcast", "SKU-102", ""),
    ("run-mmm-q1-refit", "contribution",   260_000, "channel+product",
     "2026-Q1", "Podcast", "SKU-104", ""),
    ("run-mmm-q1-refit", "contribution",  -180_000, "channel+product",
     "2026-Q1", "Podcast", "SKU-101", ""),
    ("run-mmm-q1-refit", "contribution",  -190_000, "channel+product",
     "2026-Q1", "Podcast", "SKU-103", ""),
    ("run-mmm-q1-refit", "contribution",  -160_000, "channel+product",
     "2026-Q1", "Podcast", "SKU-105", ""),

    # -- Affiliate: weak overall, primary path for one segment ------------
    # 120k at channel level. Split by segment it is +480k for Discount and
    # -360k for Full-Price. Both reads are honest; they answer different
    # questions (finding 2).
    ("run-mmm-q1-refit", "contribution",   120_000, "channel", "2026-Q1",
     "Affiliate", "", ""),
    ("run-mmm-q1-refit", "contribution",   480_000, "channel+segment",
     "2026-Q1", "Affiliate", "", "Discount"),
    ("run-mmm-q1-refit", "contribution",  -360_000, "channel+segment",
     "2026-Q1", "Affiliate", "", "Full-Price"),

    # -- Paid Search: the biggest line, and only one method has ever looked
    ("run-mmm-q1", "contribution", 5_100_000, "channel", "2026-Q1",
     "Paid Search", "", ""),

    # -- Organic and Display: one method each (finding 14) -----------------
    ("run-mmm-q1",  "contribution", 310_000, "channel", "2026-Q1",
     "Organic", "", ""),
    ("run-plat-q1", "contribution", 640_000, "channel", "2026-Q1",
     "Display", "", ""),

    # -- Email: small spend, best CAC (finding 12) ------------------------
    ("run-mmm-q1", "contribution", 820_000, "channel", "2026-Q1",
     "Email", "", ""),
    ("run-mmm-q1", "cac",  18.40, "channel", "2026-Q1", "Email", "", ""),
    ("run-mmm-q1", "cac",  47.10, "channel", "2026-Q1", "Paid Search", "", ""),
    ("run-mmm-q1", "cac",  62.80, "channel", "2026-Q1", "Paid Social", "", ""),
    ("run-mmm-q1", "cac",  71.20, "channel", "2026-Q1", "CTV", "", ""),
    ("run-mmm-q1", "cac",  95.60, "channel", "2026-Q1", "Podcast", "", ""),
    ("run-mmm-q1", "cac",  38.90, "channel", "2026-Q1", "Affiliate", "", ""),
    ("run-mmm-q1", "cac",  24.30, "channel+segment", "2026-Q1",
     "Email", "", "Full-Price"),

    # -- Q4, so there is a history to compound against --------------------
    ("run-mmm-q4",  "contribution", 6_800_000, "channel", "2025-Q4",
     "Paid Search", "", ""),
    ("run-mmm-q4",  "contribution", 4_100_000, "channel", "2025-Q4",
     "Paid Social", "", ""),
    ("run-mmm-q4",  "contribution",   900_000, "channel", "2025-Q4",
     "Affiliate", "", ""),
    ("run-mmm-q4",  "contribution",    60_000, "channel", "2025-Q4",
     "Podcast", "", ""),
    ("run-plat-q4", "contribution", 4_900_000, "channel", "2025-Q4",
     "Paid Social", "", ""),
    # the later, colder read: 585k against 900k is 35% lower, and a decision
    # was taken on the original (finding 11)
    ("run-mmm-q1-refit", "contribution", 585_000, "channel", "2025-Q4",
     "Affiliate", "", ""),

    # -- Two claims with no dataset behind them at all (finding 8) --------
    # Booked, quoted, and untraceable. Every ledger has them; nobody knows
    # until someone asks.
    ("run-orphan", "contribution", 220_000, "channel", "2025-Q4",
     "Display", "", ""),
    ("run-orphan", "contribution",  95_000, "channel", "2025-Q4",
     "Organic", "", ""),
]

#: (later_run, earlier_run, channel, period) — a read replacing an earlier one
SUPERSEDES = [
    ("run-mmm-q1-refit", "run-mmm-q4", "Affiliate", "2025-Q4"),
]

#: id, name, period, booked_value, from_run, channel
#:
#: The trial balance. Paid Search is the largest line and rests on a single
#: method (finding 6). Four lines descend from the stale panel extract at
#: different depths (finding 5), and because every MMM claim traces to the
#: panel, one source underpins most of the booked value (finding 10).
PLLINES = [
    ("2026-Q1|Paid Search", "Paid Search contribution", "2026-Q1",
     5_100_000, "run-mmm-q1", "Paid Search"),
    ("2026-Q1|Paid Social", "Paid Social contribution", "2026-Q1",
     1_250_000, "run-inc-q1", "Paid Social"),
    ("2026-Q1|CTV", "CTV contribution", "2026-Q1",
     900_000, "run-mmm-q1", "CTV"),
    ("2026-Q1|Podcast", "Podcast contribution", "2026-Q1",
     40_000, "run-mmm-q1-refit", "Podcast"),
    ("2026-Q1|Affiliate", "Affiliate contribution", "2026-Q1",
     120_000, "run-mmm-q1-refit", "Affiliate"),
    ("2026-Q1|Email", "Email contribution", "2026-Q1",
     820_000, "run-mmm-q1", "Email"),
    ("2026-Q1|Organic", "Organic contribution", "2026-Q1",
     310_000, "run-mmm-q1", "Organic"),
    ("2026-Q1|Display", "Display contribution", "2026-Q1",
     640_000, "run-plat-q1", "Display"),
]

#: id, taken_on, rationale, cited_run, channel, period, cycle
#:
#: Both decisions were taken on Q4 reads, before the Q1 work existed — which is
#: the honest sequence and the reason the ledger matters. The affiliate scale-up
#: cited a claim later superseded by a read 35% lower (finding 11). The podcast
#: cut was decided on a channel-level aggregate; the April refit shows it was
#: working for two SKUs the whole time.
DECISIONS = [
    ("dec-affiliate-scale|2026-01-22", "2026-01-22",
     "Scale affiliate into Q1 on the back of a strong Q4 read",
     "run-mmm-q4", "Affiliate", "2025-Q4", "FY26|Q1 planning"),
    ("dec-podcast-cut|2026-02-03", "2026-02-03",
     "Cut podcast — no measurable contribution at channel level",
     "run-mmm-q4", "Podcast", "2025-Q4", "FY26|Q1 planning"),
]



def main() -> int:
    print(f"Generating the {BRAND} measurement ledger — all synthetic\n")

    rows("periods", ["id", "season", "is_peak", "starts", "ends",
                     "planning_cycle", "provenance"],
         [(p[0], p[1], p[2], p[3], p[4], p[5], SYNTHETIC) for p in PERIODS])

    rows("products", ["sku", "name", "provenance"],
         [(s, n, SYNTHETIC) for s, n in PRODUCTS])

    rows("segments", ["name", "provenance"],
         [(s[0], SYNTHETIC) for s in SEGMENTS])

    rows("channels", ["name", "funnel_stage", "provenance"],
         [(n, f, SYNTHETIC) for n, f in CHANNELS])

    rows("methods", ["id", "kind", "name", "observes", "provenance"],
         [(i, k, n, o, SYNTHETIC) for i, k, n, o in METHODS])

    rows("sources", ["id", "name", "provenance"],
         [(i, n, SYNTHETIC) for i, n in SOURCES])

    rows("markets", ["geo_code", "name", "geo_kind", "provenance"],
         [(c, n, k, SYNTHETIC) for c, n, k in MARKETS])

    rows("datasets",
         ["id", "name", "window", "refreshed_on", "derived_from", "source",
          "provenance"],
         [(*d, SYNTHETIC) for d in DATASETS])

    all_runs = RUNS + bulk_runs()
    rows("runs",
         ["id", "method", "executed_on", "observed_from", "observed_to",
          "dataset", "geotest", "provenance"],
         [(*r, SYNTHETIC) for r in all_runs])

    rows("geotests",
         ["id", "channel", "design", "mde", "spend_delta_pct", "started_on",
          "provenance"],
         [(*g, SYNTHETIC) for g in GEOTESTS])

    rows("studies",
         ["id", "question", "hypothesis", "owner", "status", "run", "cycle",
          "provenance"],
         [(*s, SYNTHETIC) for s in STUDIES])

    rows("cycles",
         ["id", "fy", "name", "board_date", "budget_locked_on", "provenance"],
         [(*c, SYNTHETIC) for c in CYCLES])

    rows("spend", ["id", "channel", "period", "amount", "provenance"],
         [(f"{ch}|{per}", ch, per, amt, SYNTHETIC)
          for ch, by_period in SPEND.items()
          for per, amt in by_period.items()])

    claims = []
    # The placed findings first, so they keep their ids, then the corpus they
    # sit inside. Order matters only for readability of the CSV; the ids are
    # content-derived either way.
    for row in (CLAIMS + bulk_claims(bulk_runs())):
        run, metric, value, gran, period, channel, product, segment = row[:8]
        market = row[8] if len(row) > 8 else ""
        about = "|".join(x for x in (channel, product, segment, market) if x)
        claims.append((claim_id(run, about, metric, period, gran), run, metric,
                       value, gran, period, channel, product, segment,
                       market, SYNTHETIC))
    rows("claims",
         ["id", "run", "metric", "value", "granularity", "period", "channel",
          "product", "segment", "market", "provenance"], claims)

    def find(run, channel, period, metric="contribution"):
        """The one channel-level claim matching these four things.

        Granularity is part of the match, and more than one hit is an ERROR
        rather than "take the first". Without that this returned whichever row
        happened to come first in CLAIMS, so a P&L line silently depended on
        the order of a hand-written table — and adding a claim above another
        could repoint a booked number with nothing failing.
        """
        hits = [c[0] for c in claims
                if (c[1], c[6], c[5], c[2], c[4])
                == (run, channel, period, metric, "channel")]
        if len(hits) != 1:
            raise KeyError(f"{len(hits)} claims for {run} {channel} {period} "
                           f"{metric} at channel level — expected exactly one")
        return hits[0]

    rows("supersedes", ["later", "earlier"],
         [(find(a, ch, per), find(b, ch, per))
          for a, b, ch, per in SUPERSEDES])

    rows("pllines",
         ["id", "name", "period", "booked_value", "booked_from", "channel",
          "provenance"],
         [(i, n, per, val, find(run, ch, per), ch, SYNTHETIC)
          for i, n, per, val, run, ch in PLLINES])

    rows("decisions",
         ["id", "taken_on", "rationale", "cited_claim", "channel", "cycle",
          "provenance"],
         [(i, on, why, find(run, ch, per), ch, cyc, SYNTHETIC)
          for i, on, why, run, ch, per, cyc in DECISIONS])

    print(f"\nWritten to {OUT}")
    print("Now run: python data/verify_data_coverage.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
