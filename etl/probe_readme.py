"""The front page held to the graph that produced it.

Every figure on `README.md` — the node and edge totals, the per-label
breakdown, the hero query's own result table — is read out of a loaded engine
here and written to `docs/sources/readme-measured.json`. `tests/test_readme.py`
then fails when the page and that record disagree.

Why this exists: the README stated **78,758 edges** for weeks. A run today read
back **78,752**. Six edges is nothing; a page asserting a count the engine does
not return is the exact failure `etl/load.py:verify` refuses to let the loader
commit, and the most-read numbers in the repo were the ones nothing checked.

Two engine behaviours shape how this is written, both measured on 1.1.0:

- **`DISTINCT` on a projected expression is ignored.** `RETURN DISTINCT
  labels(n)` returns one row per node, duplicates included, with no error. So
  the label list is collected and deduplicated in Python rather than trusted to
  the engine — a `DISTINCT` here would have produced a correct-looking list only
  because the dedupe happened by accident downstream.
- **`CALL db.labels()` parses and returns nothing usable** — sixteen empty rows,
  one per label, with no names in them. It cannot be used for introspection.

Run:

    python -m etl.probe_readme --url http://localhost:8080            # print
    python -m etl.probe_readme --url http://localhost:8080 --record   # write
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys
import time

from etl.engine import Engine, Refused

ROOT = pathlib.Path(__file__).resolve().parents[1]
RECORD = ROOT / "docs" / "sources" / "readme-measured.json"

#: The hero query on the front page, character for character. A paraphrase here
#: would let the page and the record agree about a query the page does not show.
HERO = """MATCH (a:Claim)-[:ABOUT]->(ch:Channel)
WHERE ch.name = "Paid Social" AND a.granularity = "channel"
  AND a.metric = "contribution"
WITH a, ch
MATCH (a)-[:FOR]->(p:Period) WHERE p.id = "2026-Q1"
WITH a, ch, p
MATCH (ma:Method)-[:EXECUTED_AS]->(:Run)-[:PRODUCED]->(a) WHERE ma.kind = "mmm"
WITH a, ch, p, ma
MATCH (b:Claim)-[:ABOUT]->(ch)
WHERE b.granularity = "channel" AND b.metric = "contribution"
WITH a, ch, p, ma, b
MATCH (b)-[:FOR]->(pb:Period) WHERE pb.id = "2026-Q1"
WITH a, p, ma, b
MATCH (mb:Method)-[:EXECUTED_AS]->(:Run)-[:PRODUCED]->(b) WHERE mb.kind = "geo"
RETURN p.id, ma.kind, a.value, mb.kind, b.value,
       abs(a.value - b.value) AS gap,
       round(100.0 * abs(a.value - b.value) / a.value) AS gap_pct"""


def names(engine: Engine, query: str) -> list[str]:
    """Collect one column and deduplicate **here**, not in the engine.

    `DISTINCT` is ignored on a projected expression on this build, so this asks
    for every row and reduces it locally. Sorted so the record is stable across
    runs; an unsorted list would make every re-record a diff.
    """
    rows = engine.run(query).get("records") or []
    seen = set()
    for row in rows:
        value = row[0]
        # `labels(n)` answers a LIST; `type(r)` answers a string.
        for item in (value if isinstance(value, list) else [value]):
            if item:
                seen.add(item)
    return sorted(seen)


def provenance() -> dict:
    """The commit this record was measured from, and whether the tree was dirty.

    A record whose whole job is to be the evidence behind the front page should
    say which code produced it. `dirty` is the load-bearing field: a record
    written from an uncommitted tree cannot be reproduced by checking out the
    commit it names, and `tests/test_readme.py` refuses to let one merge.
    """
    def git(*args: str) -> str:
        try:
            return subprocess.run(("git", *args), cwd=ROOT, capture_output=True,
                                  text=True, timeout=10).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return ""

    commit = git("rev-parse", "HEAD")
    return {
        "commit": commit or None,
        # Anything git reports as changed, staged or not. An empty answer from
        # a working `git` means clean; a failure to run git at all is reported
        # as dirty rather than clean, because unknown is not the same as safe.
        "dirty": True if not commit else bool(git("status", "--porcelain")),
    }


def measure(url: str) -> tuple[dict, float]:
    """The record, and the hero query's wall-clock time.

    The timing is returned rather than recorded. It changes on every run,
    so keeping it in the committed record would guarantee a diff each time
    the page is re-recorded while checking nothing.
    """
    engine = Engine(url)

    total_nodes = engine.scalar("MATCH (n) RETURN count(n)")
    if not total_nodes:
        raise Refused(0, f"{url} holds no nodes. Load the graph first: "
                         f"python etl/load.py --url {url}")
    total_edges = engine.scalar("MATCH ()-[r]->() RETURN count(r)")
    # The same guard the node total gets. Without it a None reaches the page as
    # "the graph holds None edges", which sends whoever reads it looking at the
    # graph rather than at the query that failed to answer.
    if not total_edges:
        raise Refused(0, f"{url} answered {total_edges!r} for the edge count; "
                         f"the graph holds nodes but no edges, or the count "
                         f"query did not answer")

    labels = names(engine, "MATCH (n) RETURN labels(n)")
    edge_types = names(engine, "MATCH ()-[r]->() RETURN type(r)")

    # The label and edge-type names are interpolated rather than bound,
    # because a label cannot be a query parameter. They come from the
    # engine's own answer above, never from user input — but a label
    # carrying a space or a backtick would still produce a parse error
    # rather than a clear one.
    by_label = {label: engine.scalar(f"MATCH (n:{label}) RETURN count(n)")
                for label in labels}
    by_edge = {kind: engine.scalar(f"MATCH ()-[r:{kind}]->() RETURN count(r)")
               for kind in edge_types}

    # The per-label counts must sum to the total, or one of the two is wrong and
    # the page would quote both. A node carrying two labels would break this
    # legitimately — this graph has none, and the check says so rather than
    # assuming it.
    # A count that did not answer is refused by name. Summing a None raises
    # TypeError, which is not Refused and so escapes main()'s handler as a
    # traceback rather than as this tool's own error.
    for name, count in list(by_label.items()) + list(by_edge.items()):
        if not isinstance(count, int):
            raise Refused(0, f"`{name}` counted {count!r}, not a number — the "
                             f"engine did not answer that count")

    if sum(by_label.values()) != total_nodes:
        raise Refused(0, f"labels sum to {sum(by_label.values())} but the graph "
                         f"holds {total_nodes} nodes — a multi-labelled node "
                         f"would explain it; the page cannot quote both")
    if sum(by_edge.values()) != total_edges:
        raise Refused(0, f"edge types sum to {sum(by_edge.values())} but the "
                         f"graph holds {total_edges} edges")

    started = time.time()
    hero = engine.run(HERO)
    hero_ms = round((time.time() - started) * 1000, 1)
    # The odd one out in a probe that refuses an empty graph and a sum
    # mismatch: a hero query answering nothing would record cleanly and exit 0,
    # leaving the page's headline table with no row behind it. The test catches
    # it afterwards; the probe is where the context to explain it lives.
    if not (hero.get("records") or []):
        raise Refused(0, "the hero query returned no rows. The page shows one, "
                         "so either the query or the loaded graph has changed")

    return {
        # Where this run happened. Provenance for a reader; no test
        # asserts it, and the default differs from the engine the
        # committed record was taken from.
        "code": provenance(),
        "url": url,
        "nodes": total_nodes,
        "edges": total_edges,
        "labels": len(labels),
        "edge_types": len(edge_types),
        "by_label": by_label,
        "by_edge_type": by_edge,
        "hero_query": HERO,
        "hero_columns": hero.get("columns") or [],
        "hero_rows": hero.get("records") or [],
    }, hero_ms


def report(measured: dict, hero_ms: float) -> None:
    print(f"  {measured['nodes']:,} nodes / {measured['edges']:,} edges")
    print(f"  {measured['labels']} labels · "
          f"{measured['edge_types']} edge types")
    print()
    for label, count in sorted(measured["by_label"].items(),
                               key=lambda kv: -kv[1]):
        print(f"  {label:<16}{count:>8,}")
    print()
    for kind, count in sorted(measured["by_edge_type"].items(),
                              key=lambda kv: -kv[1]):
        print(f"  {kind:<16}{count:>8,}")
    print()
    print(f"  hero query: {len(measured['hero_rows'])} row(s) "
          f"in {hero_ms}ms")
    for row in measured["hero_rows"]:
        print(f"    {row}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m etl.probe_readme",
        description="Read every front-page figure out of a loaded graph.")
    parser.add_argument("--url", default="http://localhost:8080")
    parser.add_argument("--record", action="store_true",
                        help=f"write {RECORD.relative_to(ROOT)}")
    args = parser.parse_args(argv)

    try:
        measured, hero_ms = measure(args.url)
    except Refused as refused:
        print(f"refused: {refused}", file=sys.stderr)
        return 2

    report(measured, hero_ms)
    if args.record:
        RECORD.parent.mkdir(parents=True, exist_ok=True)
        # Written aside and moved into place. `write_text` truncates first, so
        # an interrupt or a full disk leaves half a record — and the symptom is
        # a JSONDecodeError at test-collection time, a long way from the cause.
        scratch = RECORD.with_suffix(".json.tmp")
        scratch.write_text(json.dumps(measured, indent=2) + "\n",
                           encoding="utf-8")
        os.replace(scratch, RECORD)
        print(f"\nwrote {RECORD.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
