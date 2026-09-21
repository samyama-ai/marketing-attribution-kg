"""Load the measurement ledger into Samyama Graph, and verify what landed.

Reads `data/csv/*.csv`, applies `schema/marketing_attribution_kg.cypher`, writes
the graph, and then **reads every count back out of the engine** before saying
it worked. A loader that reports what it intended to write rather than what the
engine actually holds is worse than no loader, because it is confidently wrong.

    python etl/load.py --url http://localhost:8080

**Load into a FRESH engine.** A property cannot be unwritten on this build —
`REMOVE` reports success and changes nothing — so a re-load over an existing
graph keeps values no current CSV contains, and the counts will still look
right. There is no `--reset` for that reason: it would be a promise this engine
cannot keep.

No third-party dependency.
"""

from __future__ import annotations

import argparse
import csv
import pathlib
import re
import sys
import time

# Run as `python etl/load.py` (what the README documents) and Python puts
# `etl/` on sys.path, not the repo root — so `from etl.engine import ...`
# either fails outright or, worse, resolves against an unrelated checkout that
# happens to have an `etl` package. That was observed: it silently imported
# another project's engine.py and failed on a name that exists here.
#
# Anchoring to this file's own parent makes the documented invocation work, and
# `python -m etl.load` keeps working too.
import pathlib
import sys

_ROOT = str(pathlib.Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from etl.engine import Engine, Refused, create_edges, create_nodes

ROOT = pathlib.Path(__file__).resolve().parent.parent
CSV = ROOT / "data" / "csv"
SCHEMA = ROOT / "schema" / "marketing_attribution_kg.cypher"


#: Properties that MUST reach the graph as numbers, not text.
#:
#: CSV has no types, so every field arrives as a string and `lit()` quotes it.
#: A quoted number is a silent defect rather than a loud one: `a.value -
#: b.value` raises "Sub requires numeric operands" if you are lucky, and a
#: comparison like `value > 1000000` sorts LEXICOGRAPHICALLY if you are not —
#: "900000" > "1200000" is true as text. Every reconciliation, ranking and gap
#: question in the bank depends on this list being right.
NUMERIC = {"value", "booked_value", "amount", "mde", "spend_delta_pct"}

#: Booleans, for the same reason. `is_peak` as the string "true" is truthy in
#: every language and equal to nothing in Cypher.
BOOLEAN = {"is_peak"}


def typed(name: str, raw: str):
    """One CSV cell, as the type the graph needs.

    An empty numeric cell returns None rather than `""`. Returning the empty
    string put a STRING into a property the whole catalogue does arithmetic on,
    which is the exact defect the NUMERIC set exists to prevent — reintroduced
    through the blank-cell path. `upsert`/`create_nodes` drop None, so the
    property is simply absent, which is the honest representation of "not
    measured".

    A malformed number is an error, not a silent zero. `float("n/a")` raising
    here names the file and column; coercing it to 0 books a number nobody
    reported.
    """
    if raw in ("", None):
        return None
    if name in NUMERIC:
        try:
            number = float(raw)
        except ValueError:
            raise ValueError(f"{name}: {raw!r} is not a number") from None
        return int(number) if number.is_integer() else number
    if name in BOOLEAN:
        return raw.strip().lower() == "true"
    return raw


def read(name: str) -> list[dict]:
    with (CSV / f"{name}.csv").open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def say(quiet: bool, *args) -> None:
    if not quiet:
        print(*args)


def apply_schema(engine: Engine, quiet: bool = False) -> int:
    """Every statement in the schema file, comments stripped.

    Constraints declare the key and do not enforce it here — measured. That
    makes this documentation the engine happens to accept, not a guard. The
    only real uniqueness guarantee is that ids below are minted from content.
    """
    statements = [s.strip() for s
                  in re.sub(r"//[^\n]*", "", SCHEMA.read_text("utf-8")).split(";")
                  if s.strip()]
    for statement in statements:
        engine.run(statement)
    say(quiet, f"  schema     {len(statements):>5,} statements")
    return len(statements)


def load(engine: Engine, quiet: bool = False) -> dict:
    counts: dict[str, int] = {}

    def nodes(label: str, key: str, rows: list[dict], props: list[str]) -> None:
        # Batched CREATE, not MERGE-then-SET. The loader refuses a non-empty
        # graph, so there is nothing to merge against — and this is the
        # difference between 219 nodes/sec and roughly 51,000.
        payload = [{key: row[key],
                    **{p: typed(p, row.get(p, "")) for p in props}}
                   for row in rows]
        create_nodes(engine, label, payload)
        counts[label] = len(rows)
        say(quiet, f"  {label:<14} {len(rows):>6,}")

    say(quiet, "\nnodes")
    nodes("Period", "id", read("periods"),
          ["season", "is_peak", "starts", "ends", "provenance"])
    nodes("Product", "sku", read("products"), ["name", "provenance"])
    nodes("Segment", "name", read("segments"), ["provenance"])
    nodes("Channel", "name", read("channels"),
          ["funnel_stage", "provenance"])
    nodes("Method", "id", read("methods"),
          ["kind", "name", "observes", "provenance"])
    nodes("Source", "id", read("sources"), ["name", "provenance"])
    nodes("Market", "geo_code", read("markets"),
          ["name", "geo_kind", "provenance"])
    nodes("Dataset", "id", read("datasets"),
          ["name", "window", "refreshed_on", "provenance"])
    nodes("Run", "id", read("runs"),
          ["executed_on", "observed_from", "observed_to", "provenance"])
    nodes("GeoTest", "id", read("geotests"),
          ["design", "mde", "spend_delta_pct", "started_on", "provenance"])
    nodes("Study", "id", read("studies"),
          ["question", "hypothesis", "owner", "status", "provenance"])
    nodes("PlanningCycle", "id", read("cycles"),
          ["fy", "name", "board_date", "budget_locked_on", "provenance"])
    nodes("Spend", "id", read("spend"), ["amount", "provenance"])
    nodes("Claim", "id", read("claims"),
          ["metric", "value", "granularity", "provenance"])
    nodes("PLLine", "id", read("pllines"),
          ["name", "booked_value", "provenance"])
    nodes("Decision", "id", read("decisions"),
          ["taken_on", "rationale", "provenance"])

    say(quiet, "\nedges")
    edges: dict[str, int] = {}

    def edge(name: str, n: int) -> None:
        edges[name] = n
        say(quiet, f"  {name:<16} {n:>6,}")

    def batch(pairs, edge_type, a_label, a_key, b_label, b_key) -> None:
        create_edges(engine, pairs, edge_type, a_label, a_key,
                     b_label, b_key)

    rows = read("datasets")
    derived = [(r["id"], r["derived_from"]) for r in rows if r["derived_from"]]
    create_edges(engine, derived, "DERIVED_FROM", "Dataset", "id",
                 "Dataset", "id")
    edge("DERIVED_FROM", len(derived))

    extracted = [(r["id"], r["source"]) for r in rows if r["source"]]
    create_edges(engine, extracted, "EXTRACTED_FROM", "Dataset", "id",
                 "Source", "id")
    edge("EXTRACTED_FROM", len(extracted))

    runs = read("runs")
    create_edges(engine, [(r["method"], r["id"]) for r in runs],
                 "EXECUTED_AS", "Method", "id", "Run", "id")
    edge("EXECUTED_AS", len(runs))

    consumed = [(r["id"], r["dataset"]) for r in runs if r["dataset"]]
    create_edges(engine, consumed, "CONSUMED", "Run", "id", "Dataset", "id")
    edge("CONSUMED", len(consumed))

    tested = [(r["id"], r["geotest"]) for r in runs if r["geotest"]]
    create_edges(engine, tested, "EXECUTED_TEST", "Run", "id", "GeoTest", "id")
    edge("EXECUTED_TEST", len(tested))

    claims = read("claims")
    create_edges(engine, [(r["run"], r["id"]) for r in claims],
                 "PRODUCED", "Run", "id", "Claim", "id")
    edge("PRODUCED", len(claims))

    create_edges(engine, [(r["id"], r["period"]) for r in claims],
                 "FOR", "Claim", "id", "Period", "id")
    edge("FOR (claim)", len(claims))

    for label, key, column in (("Channel", "name", "channel"),
                               ("Product", "sku", "product"),
                               ("Segment", "name", "segment"),
                               ("Market", "geo_code", "market")):
        pairs = [(r["id"], r[column]) for r in claims if r.get(column)]
        if pairs:
            create_edges(engine, pairs, "ABOUT", "Claim", "id", label, key)
            edge(f"ABOUT ({column})", len(pairs))

    supersedes = read("supersedes")
    create_edges(engine, [(r["later"], r["earlier"]) for r in supersedes],
                 "SUPERSEDES", "Claim", "id", "Claim", "id")
    edge("SUPERSEDES", len(supersedes))

    pllines = read("pllines")
    create_edges(engine, [(r["id"], r["booked_from"]) for r in pllines],
                 "BOOKED_FROM", "PLLine", "id", "Claim", "id")
    edge("BOOKED_FROM", len(pllines))
    create_edges(engine, [(r["id"], r["period"]) for r in pllines],
                 "FOR", "PLLine", "id", "Period", "id")
    edge("FOR (plline)", len(pllines))

    spend = read("spend")
    create_edges(engine, [(r["id"], r["channel"]) for r in spend],
                 "ON", "Spend", "id", "Channel", "name")
    edge("ON", len(spend))
    create_edges(engine, [(r["id"], r["period"]) for r in spend],
                 "FOR", "Spend", "id", "Period", "id")
    edge("FOR (spend)", len(spend))

    decisions = read("decisions")
    create_edges(engine, [(r["id"], r["cited_claim"]) for r in decisions],
                 "CITED", "Decision", "id", "Claim", "id")
    edge("CITED", len(decisions))
    create_edges(engine, [(r["id"], r["channel"]) for r in decisions],
                 "ABOUT", "Decision", "id", "Channel", "name")
    edge("ABOUT (decision)", len(decisions))
    create_edges(engine, [(r["id"], r["cycle"]) for r in decisions],
                 "FOR_CYCLE", "Decision", "id", "PlanningCycle", "id")
    edge("FOR_CYCLE", len(decisions))

    studies = read("studies")
    create_edges(engine, [(r["id"], r["run"]) for r in studies],
                 "COMMISSIONED", "Study", "id", "Run", "id")
    edge("COMMISSIONED", len(studies))
    create_edges(engine, [(r["id"], r["cycle"]) for r in studies],
                 "DUE_FOR", "Study", "id", "PlanningCycle", "id")
    edge("DUE_FOR", len(studies))

    # The cycle a period belongs to, taken from the period's own column.
    #
    # This was `cycles[0] if r["id"] < "2026-Q2" else cycles[-1]`, which reads
    # like a boundary but has none in range: every period this brand has sorts
    # below "2026-Q2", so all eight landed in one cycle and the other got no
    # edges at all. Both the hardcoded literal it replaced and that expression
    # produced the same wrong graph, which is why swapping one for the other
    # looked like a fix.
    #
    # Six periods carry no cycle deliberately — both cycles are FY26 and a 2024
    # quarter was not planned in them — so an empty column means no edge rather
    # than a default.
    periods = read("periods")
    in_cycle = [(r["id"], r["planning_cycle"]) for r in periods
                if r.get("planning_cycle")]

    # Every declared cycle should have something pointing at it. A cycle with no
    # periods is the failure this whole block is about, and it is invisible in
    # the edge count alone.
    declared = {r["id"] for r in read("cycles")}
    linked = {c for _, c in in_cycle}
    if declared - linked:
        raise SystemExit(f"planning cycles with no periods: "
                         f"{sorted(declared - linked)}")
    if linked - declared:
        raise SystemExit(f"periods naming an unknown cycle: "
                         f"{sorted(linked - declared)}")
    create_edges(engine, in_cycle, "IN_CYCLE", "Period", "id",
                 "PlanningCycle", "id")
    edge("IN_CYCLE", len(in_cycle))

    return {"nodes": counts, "edges": edges}


def verify(engine: Engine, loaded: dict, quiet: bool = False) -> list[str]:
    """Read every count back out of the engine and compare.

    This is the only part that makes the numbers above trustworthy. Everything
    before it is what the loader BELIEVES it wrote; this is what the graph
    actually holds, and on an engine where a constraint does not enforce and a
    silently-ignored property map returns plausible wrong answers, those are
    different questions.
    """
    problems = []
    for label, expected in loaded["nodes"].items():
        held = engine.scalar(f"MATCH (n:{label}) RETURN count(n)")
        if held != expected:
            problems.append(f"{label}: loader wrote {expected}, "
                            f"engine holds {held}")
    # Several edge TYPES are written from more than one place — FOR comes from
    # claims, P&L lines and spend; ABOUT from claims and decisions. The engine
    # only knows the type, so the comparison has to sum by type. Getting this
    # wrong is how the first run of this verifier reported a false mismatch,
    # which is the verifier working: the loader's arithmetic was wrong, not the
    # graph.
    by_type: dict[str, int] = {}
    for name, expected in loaded["edges"].items():
        by_type[name.split(" ")[0]] = by_type.get(name.split(" ")[0], 0) + expected
    for edge, expected in by_type.items():
        held = engine.scalar(f"MATCH ()-[r:{edge}]->() RETURN count(r)")
        if held != expected:
            problems.append(f"{edge}: loader wrote {expected}, "
                            f"engine holds {held}")

    say(quiet, "")
    if problems:
        # **Mismatches go to stderr unconditionally.** These used to route
        # through `say()`, so `--quiet` — the mode any automation runs in —
        # produced a bare exit 3 and no indication of WHICH count disagreed.
        # That is the one message that must always survive: "the loader failed"
        # and "Claim: wrote 19,716, engine holds 19,715" are different facts,
        # and only the second one is actionable.
        for problem in problems:
            print(f"  MISMATCH  {problem}", file=sys.stderr)
        print("\n  A count disagreeing after a clean run usually means a "
              "retried write landed twice, or a duplicate key fanned out a "
              "join. The graph is NOT safe to query.", file=sys.stderr)
    else:
        say(quiet, "  verified — every count read back from the engine")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python etl/load.py",
        description="Load the measurement ledger into Samyama Graph.")
    parser.add_argument("--url", default="http://localhost:8080")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    engine = Engine(args.url)
    started = time.time()
    try:
        held = engine.scalar("MATCH (n) RETURN count(n)")
        if held:
            print(f"refused: {args.url} already holds {held:,} nodes. "
                  f"A property cannot be unwritten on this build, so loading "
                  f"over an existing graph keeps values no CSV contains. "
                  f"Start a fresh engine.", file=sys.stderr)
            return 1                       # refused; nothing was written
        say(args.quiet, "schema")
        apply_schema(engine, args.quiet)
        loaded = load(engine, args.quiet)
        problems = verify(engine, loaded, args.quiet)
    except Refused as refused:
        print(f"\nengine refused: {refused}", file=sys.stderr)
        return 2

    total = sum(loaded["nodes"].values())
    edges = sum(loaded["edges"].values())
    say(args.quiet, f"\n  {total:,} nodes / {edges:,} edges "
                    f"in {time.time() - started:.1f}s")
    # 1 = refused to start, 3 = loaded but the counts disagree. Two different
    # facts: the first means nothing was written, the second means something
    # was and it is not what we think.
    return 3 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
