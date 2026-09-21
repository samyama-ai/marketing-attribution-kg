"""The corpus the findings sit inside.

`generate.py` holds fifteen situations placed by hand. This holds the ~19,600
claims around them — one run per method per period across the whole history,
then channel, product and geo level claims off each. Nothing here is a finding
and nothing here should ever become one: if a query only answers because of a
number in this file, the query is reading noise.

**No `random`, anywhere.** Values come from a hash of the thing they describe,
so two runs produce byte-identical files and the planted findings never move
inside the corpus. A seeded generator would not be enough — it still shifts if
anything upstream of it consumes a draw.

Imported by `data/generate.py`.
"""

from __future__ import annotations

import hashlib
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from world import CHANNELS, MARKETS, METHODS, PERIODS, PRODUCTS  # noqa: E402

# --------------------------------------------------------------------------
# The corpus around the findings
# --------------------------------------------------------------------------
#: Deterministic pseudo-randomness. `random` is avoided entirely — a seeded
#: generator still shifts if anything upstream of it consumes a draw, and the
#: findings would move with it. A hash of the identity is stable forever.
def wobble(*parts) -> float:
    """A repeatable number in [0, 1) derived from the thing it describes."""
    raw = "|".join(str(p) for p in parts).encode()
    return int(hashlib.sha1(raw).hexdigest()[:8], 16) / 0xFFFFFFFF


def bulk_runs() -> list[tuple]:
    """One run per method per period, beyond the hand-placed ones.

    The named runs in RUNS carry the findings. These are the rest of the
    programme — the reason a claim can be one of many rather than one of six.
    """
    out = []
    for period, _season, _peak, starts, ends, *_ in PERIODS:
        if period in ("2025-Q4", "2026-Q1"):
            continue                      # the placed runs cover these
        # **Executed AFTER the period closed, and observing all of it.**
        #
        # These dates used to be day-28 of the quarter's last month for both
        # `executed_on` and `observed_to`. Every quarter ends on the 30th or
        # 31st, so all thirty bulk runs read as "executed before the quarter
        # closed" and Q4 returned 19,675 rows — burying the single premature
        # run that finding is about under a corpus that was only ever meant to
        # be background. The question passed while answering nothing.
        #
        # A run executed after close observing the whole period is the ordinary
        # case, which is what background data should be. Prematurity is a
        # planted finding and belongs in RUNS, not in the corpus.
        year, month = int(ends[:4]), int(ends[5:7])
        executed = (f"{year + 1}-01-12" if month == 12
                    else f"{year}-{month + 1:02d}-12")
        for method_id, kind, *_ in METHODS:
            out.append((
                f"run-{kind}-{period.lower()}", method_id,
                executed, starts, ends,
                "ds-mmm-input" if kind == "mmm" else "ds-pos-orders", ""))
    return out


def bulk_claims(runs: list[tuple]) -> list[tuple]:
    """Channel, product and geo level claims across the whole history.

    Every value is derived from `wobble`, so the corpus is identical on every
    run and the planted findings never move inside it.
    """
    out = []
    for run_id, method_id, executed, _, _, _, _ in runs:
        kind = method_id.split("|")[0]
        parts = run_id.split("-")
        period = f"{parts[-2]}-{parts[-1].upper()}"
        if period not in {p[0] for p in PERIODS}:
            continue
        for channel, _stage in CHANNELS:
            base = 400_000 + wobble(channel, period, kind) * 4_000_000
            out.append((run_id, "contribution", round(base), "channel",
                        period, channel, "", ""))
            if kind in ("mmm", "platform", "multiplier"):
                for sku, _name in PRODUCTS:
                    share = wobble(channel, sku, period) * 0.06
                    out.append((run_id, "contribution",
                                round(base * share), "channel+product",
                                period, channel, sku, ""))
            # Geo reads are per market by construction — a geo test IS a
            # market-level design, and storing only its national roll-up
            # throws away the thing that made it a geo test.
            if kind == "geo":
                for code, _name, _k in MARKETS:
                    share = wobble(channel, code, period) * 0.02
                    out.append((run_id, "contribution",
                                round(base * share), "channel+geo",
                                period, channel, "", "", code))
    return out

