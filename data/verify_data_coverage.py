"""Assert that every planted finding is actually in the generated data.

The demo rests on fifteen specific situations being present. Each one is
planted deliberately, and each one can be destroyed by a one-line edit to
`generate.py` that looks harmless — a value nudged, a run renamed, a claim
dropped. Without this check the failure is silent: the generator still runs,
the graph still loads, the query returns an empty set, and nobody finds out
until someone is looking at the screen.

So this is the guard. It reads the CSVs — not the graph — because a finding
that is missing from the data cannot be rescued by the loader, and catching it
here costs seconds instead of a reload.

    python data/verify_data_coverage.py

Exit 0 if all fifteen are present, 1 with a list if any are not.
"""

from __future__ import annotations

import csv
import pathlib
import sys

CSV = pathlib.Path(__file__).resolve().parent / "csv"


def read(name: str) -> list[dict]:
    with (CSV / f"{name}.csv").open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def num(row: dict, key: str) -> float:
    return float(row[key])


def claims_where(claims, **match) -> list[dict]:
    return [c for c in claims
            if all(c.get(k) == v for k, v in match.items())]


def need(mapping: dict, key, what: str):
    """A lookup that explains itself when the key is gone.

    Every id in this file is hardcoded against `generate.py`, so the likeliest
    edit anyone makes — renaming a run, dropping a channel, removing a period —
    lands here first. A bare `KeyError: 'run-geo-q1'` names the symptom; this
    names the cause and which finding it belongs to.
    """
    try:
        return mapping[key]
    except KeyError:
        raise LookupError(
            f"{what} {key!r} is not in the generated data — it was renamed or "
            f"removed in generate.py") from None


def check(label: str, ok, detail: str = "") -> tuple[str, bool, str]:
    """One result row, with `ok` coerced to a real bool.

    Several checks compute `ok` from expressions that can produce a dict, None
    or an empty list. Those are truthy or falsy by accident rather than by
    intent, and a dict landing in the PASS column is a finding reported as
    present because a lookup happened to be non-empty.
    """
    return (label, bool(ok), detail)


def run(out: list | None = None) -> list[tuple[str, bool, str]]:
    out = [] if out is None else out
    claims = read("claims")
    runs = {r["id"]: r for r in read("runs")}
    datasets = {d["id"]: d for d in read("datasets")}
    pllines = read("pllines")
    methods = {m["id"]: m for m in read("methods")}
    channels = {c["name"]: c for c in read("channels")}
    spend = read("spend")
    decisions = read("decisions")
    supersedes = read("supersedes")
    by_id = {c["id"]: c for c in claims}

    def kind_of(claim) -> str:
        return methods[runs[claim["run"]]["method"]]["kind"]

    # 1 — a channel dead in aggregate, alive on two products
    agg = claims_where(claims, channel="Podcast", granularity="channel",
                       period="2026-Q1", metric="contribution")
    per_product = claims_where(claims, channel="Podcast",
                               granularity="channel+product",
                               period="2026-Q1", metric="contribution")
    positive = [c for c in per_product if num(c, "value") > 0]
    # The parts must SUM to the aggregate, not merely be small beside it.
    # `abs(agg) < 100_000` passed for any aggregate under an arbitrary
    # threshold, so the identity this finding is about — five SKU claims
    # summing to the channel line — was free to drift while staying green.
    parts = sum(num(c, "value") for c in per_product)
    out.append(check(
        "1  Podcast dead in aggregate, alive on 2 products",
        bool(agg) and len(per_product) == 5 and len(positive) == 2
        and abs(parts - num(agg[0], "value")) < 1,
        f"aggregate {agg[0]['value'] if agg else '-'}, parts sum {parts:.0f}, "
        f"{len(positive)} positive of {len(per_product)}"))

    # 2 — a channel that reverses under a segment split
    seg = claims_where(claims, channel="Affiliate",
                       granularity="channel+segment", period="2026-Q1",
                       metric="contribution")
    signs = {c["segment"]: num(c, "value") > 0 for c in seg}
    aff_ch = claims_where(claims, channel="Affiliate", granularity="channel",
                          period="2026-Q1", metric="contribution")
    seg_sum = sum(num(c, "value") for c in seg)
    out.append(check(
        "2  Affiliate reverses under a segment split",
        len(seg) == 2 and True in signs.values() and False in signs.values()
        and bool(aff_ch) and abs(seg_sum - num(aff_ch[0], "value")) < 1,
        str({c["segment"]: round(num(c, "value")) for c in seg})
        + f", sum {seg_sum:.0f} vs channel "
        + (f"{num(aff_ch[0], 'value'):.0f}" if aff_ch else "-")))

    # 3 — an upper-funnel channel a click-based method cannot see
    ctv = claims_where(claims, channel="CTV", period="2026-Q1")
    kinds = {kind_of(c) for c in ctv}
    out.append(check(
        "3  CTV is upper-funnel and has no platform claim",
        channels["CTV"]["funnel_stage"] == "upper"
        and "platform" not in kinds and len(kinds) >= 2,
        f"methods seeing CTV: {sorted(kinds)}"))

    # 4 — one channel, several methods, platform the highest
    ps = claims_where(claims, channel="Paid Social", granularity="channel",
                      period="2026-Q1", metric="contribution")
    top = max(ps, key=lambda c: num(c, "value")) if ps else None
    out.append(check(
        "4  Paid Social: 3+ methods, platform reads highest",
        len({kind_of(c) for c in ps}) >= 3 and top and kind_of(top) ==
        "platform",
        f"{len(ps)} claims, highest is {kind_of(top) if top else '-'}"))

    # 5 — a material MMM vs geo gap on one channel
    mmm = [c for c in ps if kind_of(c) == "mmm"]
    geo = [c for c in ps if kind_of(c) == "geo"]
    # abs() on the denominator too: a negative contribution is legitimate, and
    # dividing by it flips the sign so a 40% gap reads as -40% and fails.
    gap = (abs(num(mmm[0], "value") - num(geo[0], "value"))
           / abs(num(mmm[0], "value"))
           if mmm and geo and num(mmm[0], "value") else 0)
    out.append(check(
        "5  MMM vs geo gap on Paid Social is material",
        # Banded: the hero beat is 40%. `>= 0.25` let the headline number of
        # the whole demo drift by half without failing.
        0.35 <= gap <= 0.45, f"{gap:.0%}"))

    # 6 — a stale dataset several booked lines stand on, at varying depth
    def upstream(ds_id: str, seen=None) -> list[str]:
        """The lineage chain, IN ORDER, nearest first.

        A list rather than a set. `source_of` walks this to find the system of
        record, and iterating a set gave a different answer between runs when a
        chain reached more than one source — a nondeterministic figure in a
        file whose whole job is to be deterministic.
        """
        seen = seen if seen is not None else []
        if not ds_id or ds_id in seen:
            return seen
        seen.append(ds_id)
        parent = datasets[ds_id]["derived_from"]
        return upstream(parent, seen) if parent else seen

    # Note: more than one dataset is stale, and that is correct rather than a
    # mistake — an extract that stops refreshing takes everything derived from
    # it with it. The check asks about the OLDEST one, which is the root cause.
    stale = sorted((d for d in datasets.values()
                    if d["refreshed_on"] < "2025-11-01"),
                   key=lambda d: d["refreshed_on"])
    root = stale[0] if stale else None
    standing = [line for line in pllines
                if root and root["id"] in
                upstream(runs[by_id[line["booked_from"]]["run"]]["dataset"])]
    depths = set()
    for line in pllines:
        chain = upstream(runs[by_id[line["booked_from"]]["run"]]["dataset"])
        if root and root["id"] in chain:
            depths.add(len(chain))
    out.append(check(
        "6  A stale dataset underpins several booked lines",
        bool(root) and len(standing) >= 3 and len(depths) >= 2,
        f"{root['id'] if root else '-'} feeds {len(standing)} lines "
        f"at {len(depths)} different depths"))

    # 7 — the largest booked line rests on a single method
    largest = (max(pllines, key=lambda p: num(p, "booked_value"))
               if pllines else None)
    same_channel = claims_where(
        claims, channel=largest["channel"], granularity="channel",
        period=largest["period"], metric="contribution") if largest else []
    out.append(check(
        "7  The largest booked line rests on one method",
        len({kind_of(c) for c in same_channel}) == 1,
        f"{largest['channel'] if largest else '-'}: "
        f"{sorted({kind_of(c) for c in same_channel})}"))

    # 8 — two methods that look independent and share an upstream dataset
    geo_up = upstream(need(runs, "run-geo-q1", "run")["dataset"])
    inc_up = upstream(need(runs, "run-inc-q1", "run")["dataset"])
    shared = sorted(set(geo_up) & set(inc_up))
    out.append(check(
        "8  Geo and incrementality share an upstream dataset",
        bool(shared), f"shared: {shared}"))

    # 9 — claims with no dataset behind them at all
    orphans = [c for c in claims if not runs[c["run"]]["dataset"]]
    out.append(check(
        "9  Some booked claims have no traceable source",
        len(orphans) == 2 and {c["run"] for c in orphans} == {"run-orphan"},
        f"{len(orphans)} orphan claims from "
        f"{sorted({c['run'] for c in orphans})}"))

    # 10 — a run executed before the period it describes had closed
    periods = {p["id"]: p for p in read("periods")}
    early = [c for c in claims
             if need(runs, c["run"], "run")["executed_on"]
             < need(periods, c["period"], "period")["ends"]]
    # **Two-sided on purpose.** `bool(early)` passed with 19,681 claims when
    # every bulk run was dated day-28 — the corpus had grown into the shape of
    # the plant, and the check could not tell the difference. Exactly one run
    # is premature here, and it is a named one.
    out.append(check(
        "10 A run was executed before its period closed",
        len(early) == 1 and {c["run"] for c in early} == {"run-plat-q1-early"},
        f"{len(early)} claims from {sorted({c['run'] for c in early})}"))

    # 11 — one source underpins a disproportionate share of booked value
    def source_of(ds_id: str) -> str:
        for d in upstream(ds_id):
            if datasets[d]["source"]:
                return datasets[d]["source"]
        return ""

    exposure: dict[str, float] = {}
    for line in pllines:
        src = source_of(runs[by_id[line["booked_from"]]["run"]]["dataset"])
        exposure[src] = exposure.get(src, 0) + num(line, "booked_value")
    total = sum(exposure.values())
    worst = max(exposure.items(), key=lambda kv: kv[1]) if exposure else None
    out.append(check(
        "11 One source underpins most of the booked value",
        # Banded: the demo says 79%, and `> 0.5` would stay green at 51% —
        # a materially different story told by an unchanged PASS.
        bool(worst) and bool(total) and worst[0] == "src-panel"
        and 0.70 <= worst[1] / total <= 0.85,
        f"{worst[0]} at {worst[1]/total:.0%}" if worst and total else "no exposure"))

    # 12 — a decision taken on evidence since superseded
    superseded = {s["earlier"] for s in supersedes}
    exposed = [d for d in decisions if d["cited_claim"] in superseded]
    out.append(check(
        "12 A decision stands on superseded evidence",
        bool(exposed), f"{len(exposed)} decision(s)"))

    # 13 — the best CAC sits on the smallest spend
    cacs = claims_where(claims, metric="cac", granularity="channel",
                        period="2026-Q1")
    q1 = {s["channel"]: num(s, "amount") for s in spend
          if s["period"] == "2026-Q1"}
    # Every aggregate below is guarded. An unguarded min() over an empty list
    # RAISES, and a raise here reports a crash rather than a missing finding —
    # which is the wrong answer to "is finding 13 present?". A missing finding
    # must FAIL, loudly and in the table, not abort the run.
    priced = [c for c in cacs if c["channel"] in q1]
    best = min(priced, key=lambda c: num(c, "value")) if priced else None
    cheapest = (min((c["channel"] for c in priced), key=lambda ch: q1[ch])
                if priced else None)
    out.append(check(
        "13 Best CAC is also the smallest spend",
        bool(best) and best["channel"] == cheapest,
        f"best CAC {best['channel'] if best else '-'}, "
        f"smallest spend {cheapest or '-'} "
        f"({len(cacs) - len(priced)} CAC channels have no Q1 spend row)"))

    # 14 — channels only one method has ever looked at
    single = [ch for ch in channels
              if len({kind_of(c) for c in
                      claims_where(claims, channel=ch,
                                   period="2026-Q1")}) == 1]
    # `len(single) >= 2` stayed green after giving Organic and Display a second
    # method — the two channels the finding is actually about. The set is
    # asserted, not its size.
    EXPECTED_SINGLE = {"Paid Search", "Podcast", "Affiliate", "Email",
                       "Organic", "Display"}
    out.append(check(
        "14 Some channels have only ever had one method",
        set(single) == EXPECTED_SINGLE,
        f"{sorted(single)}" + ("" if set(single) == EXPECTED_SINGLE else
                               f" != {sorted(EXPECTED_SINGLE)}")))

    # 15 — a run whose data never covered the period it describes
    extrapolating = [c for c in claims
                     if need(runs, c["run"], "run")["observed_to"]
                     < need(periods, c["period"], "period")["starts"]]
    out.append(check(
        "15 A run never observed the period it describes",
        len(extrapolating) == 12
        and {c["run"] for c in extrapolating} == {"run-mmm-q1"},
        f"{len(extrapolating)} claims extrapolated from "
        f"{sorted({c['run'] for c in extrapolating})}"))

    return out


def main() -> int:
    # **A crash here must not replace the report.** This script exists to say
    # which planted finding went missing; a traceback says only that something
    # did. `run` fills a list this function owns, so the checks that completed
    # still print and the failure becomes the last FAIL row rather than the
    # whole output. Mutation-tested: renaming a run in generate.py used to
    # raise `KeyError: 'run-geo-q1'` and print nothing at all.
    results: list[tuple[str, bool, str]] = []
    try:
        run(results)
    except Exception as broke:
        results.append(("!! verification could not finish", False,
                        f"{type(broke).__name__}: {broke}"))
    width = max(len(label) for label, _, _ in results)
    for label, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {label:<{width}}  {detail}")
    missing = [label for label, ok, _ in results if not ok]
    print()
    if missing:
        print(f"{len(missing)} of {len(results)} findings are NOT in the data:")
        for label in missing:
            print(f"  - {label}")
        print("\nA question in the bank has just become unanswerable. Fix "
              "generate.py rather than the question.")
        return 1
    print(f"All {len(results)} planted findings present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
