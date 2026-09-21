"""Run the whole question catalogue against a loaded graph.

    python queries/run.py --url http://localhost:8080
    python queries/run.py --only Q5 Q16 Q19
    python queries/run.py --quiet          # just the pass/fail table

**A query that returns nothing is a failure here, not a curiosity.** Every
finding these questions look for is planted deliberately and asserted by
`data/verify_data_coverage.py`, so an empty result means one of three things
went wrong — the data lost a finding, the loader dropped an edge, or the query
is asking the wrong question. All three are worth failing a build over, and
none of them announces itself.

That matters more on this engine than most: a bare aggregate returns one row
over an empty graph, and a silently-ignored property filter returns a plausible
number. "It ran" is not evidence.
"""

from __future__ import annotations

import argparse
import sys

# Run as `python queries/run.py` (what the README documents) and Python puts
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

from etl.engine import Engine, Refused
from queries.catalogue import QUESTIONS


def show(rows: list, limit: int = 6) -> None:
    """Print rows, truncating at `limit`.

    The truncation is not cosmetic when this is being presented. A question
    sorted so its most interesting rows come last will have exactly those rows
    hidden — Q13 sorts thinnest-evidence-first and its payoff is the last two
    rows, so at the default six the presenter narrates a line nobody can see.
    `--limit` exists for that; the demo script sets it per beat.
    """
    for row in rows[:limit]:
        print("        ", row)
    if len(rows) > limit:
        print(f"         … {len(rows) - limit} more "
              f"(use --limit {len(rows)} to see them)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python queries/run.py")
    parser.add_argument("--url", default="http://localhost:8080")
    parser.add_argument("--only", nargs="*", default=None,
                        help="Run only these question ids.")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--limit", type=int, default=6,
                        help="Rows to print per question (default 6). Set it "
                             "higher when presenting a question whose sort "
                             "puts the point at the bottom.")
    # A read has no business waiting 60s four times over. The failure this file
    # exists to catch is a query that takes the engine down — and against a
    # wedged or closed port the old defaults ran past two minutes before giving
    # up, which is the same failure made slower. One retry, 20s each.
    parser.add_argument("--timeout", type=int, default=20,
                        help="Seconds to wait for one query (default 20).")
    parser.add_argument("--attempts", type=int, default=2,
                        help="Tries per query before giving up (default 2).")
    args = parser.parse_args(argv)

    engine = Engine(args.url, timeout=args.timeout,
                    attempts=args.attempts)
    known = {q["id"] for q in QUESTIONS}
    unknown = sorted(set(args.only or []) - known)
    if unknown:
        # For a file whose whole thesis is that a silent nothing must fail
        # loudly, running zero questions and printing "all 0 answer" is the
        # wrong default.
        print(f"no such question: {', '.join(unknown)}", file=sys.stderr)
        return 1
    chosen = [q for q in QUESTIONS
              if not args.only or q["id"] in args.only]
    failures: list[tuple[str, str]] = []

    for question in chosen:
        try:
            rows = engine.run(question["cypher"]).get("records") or []
        except Refused as refused:
            failures.append((question["id"], f"refused: {refused}"))
            print(f"  FAIL  {question['id']:<4} {question['question'][:58]}")
            print(f"        {refused}")
            continue

        # A bare aggregate returns [[null]] over an empty graph, so a row is
        # not evidence on its own — the value has to be there too.
        empty = not rows or all(
            all(cell is None for cell in row) for row in rows)
        if empty:
            failures.append((question["id"], "returned nothing"))

        print(f"  {'FAIL' if empty else 'PASS'}  {question['id']:<4} "
              f"{question['question'][:58]}")
        if not args.quiet:
            print(f"        expects: {question['expects']}")
            show(rows, args.limit)
            print(f"        -> {question['ends_in']}\n")

    print()
    if failures:
        print(f"{len(failures)} of {len(chosen)} questions have no answer:")
        for qid, why in failures:
            print(f"  - {qid}: {why}")
        print("\nAn empty answer means the data lost a finding, the loader "
              "dropped an edge, or the question is wrong. Check "
              "data/verify_data_coverage.py first.")
        return 1
    print(f"All {len(chosen)} questions answer.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
