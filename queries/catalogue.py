"""The question catalogue — every question in the client's words, with its Cypher.

Each question carries a Description, a Persona, Tags and **Design Notes saying
why the question is hard**. Two fields are added — the Cypher itself, and what
the answer should be — so the whole catalogue is runnable rather than aspirational.

**Every question is in the client's words, and every answer ends in a decision.**
Not "here is a finding" but "book it, re-run it, stop trusting it, move the
money". A finding that never became a decision did not matter.

Run them:

    python queries/run.py --url http://localhost:8080

`run.py` fails if any query returns nothing. An empty result means the data is
wrong, not the question — the findings are planted deliberately and
`data/verify_data_coverage.py` asserts they are there.

---

## Three engine rules every query below obeys

**Filters go in WHERE, never in an inline `{...}` map** on a bare single-node
MATCH. The map is silently ignored: an aggregate behind it counts the whole
label, a projection returns nothing, and neither errors.

**A `MATCH` may follow a `WHERE` once, but not twice.** Measured:

    MATCH ... WHERE ... MATCH                     -> works
    MATCH ... WHERE ... MATCH ... WHERE ... MATCH -> 400, parse error

This file previously stated the rule as "a MATCH cannot directly follow a
WHERE", which is too broad — and a review caught the contradiction between that
claim and five queries here that do exactly it and answer correctly. The rule
was wrong, not the queries. A `WITH` between the clauses resolves the parse
error and is harmless otherwise, so the loader keeps using one.

**`UNWIND` is not supported.** It is a parse error on its own and, worse,
returns `[]` rather than raising when it appears after a `WITH` in a longer
query. Deduplicate with `WITH DISTINCT` instead. Found by Q11 answering nothing.

**A `MATCH` between two variables that are BOTH already bound does not filter.
It is silently ignored.** Measured on 1.1.0 against a loaded graph, where Paid
Search has exactly two Spend nodes, one per period:

    -- one end bound, the other introduced fresh with its own WHERE
    MATCH (s:Spend)-[:ON]->(ch:Channel) WHERE ch.name = "Paid Search"
    WITH s
    MATCH (s)-[:FOR]->(p:Period) WHERE p.id = "2026-Q1"
    -> 1 row:  2,600,000 | 2026-Q1                              CORRECT

    -- both s and p already bound, MATCH used as a filter between them
    ... WITH s, p
    MATCH (s)-[:FOR]->(p)
    -> 2 rows: 4,200,000 | 2025-Q4                              WRONG
               2,600,000 | 2026-Q1

So re-using a carried variable as a pattern ANCHOR is fine — most questions here
do it and are correct. What does not work is a `MATCH` whose every endpoint is
already bound: it constrains nothing. Give the second side a fresh variable and
its own `WHERE`. This is what Q20 and Q24 were getting wrong.

An earlier version of this note claimed carried variables were REBOUND rather
than constrained. That was wrong, and it is worth saying why, because the wrong
rule produced correct code for four months. Measured:

    MATCH (a:Claim)-[:FOR]->(p:Period) WHERE p.id = "2026-Q1"
    WITH a, p
    MATCH (b:Claim)-[:FOR]->(p) RETURN count(b)
    -> 784, which is 28 x 28.  Rebinding would give 28 x 19,716.

The variable is correlated. The real cause of the original symptom is the
aggregate rule below.

**An aggregate directly over a multi-node MATCH pattern is only correct when the
`WHERE` constrains the variable being aggregated. Interpose a `WITH` and it is
always correct.** The deciding factor is the position of the filter, not the
size of the result and not whether the aggregate is grouped:

    MATCH (c:Claim)-[:FOR]->(p:Period) ...        rows   count()   verdict
      WHERE c.granularity = "channel"  count(c)    268       268   correct
      WHERE c.granularity = "channel"  count(p)    268         1   WRONG
      WHERE p.id = "2026-Q1"           count(c)     28        44   WRONG
      WHERE p.id = "2026-Q1"           count(p)     28        28   correct
      WHERE on both                    count(c)     20        20   correct

Filter the aggregated variable and it is right; filter only the other end of the
pattern and it is wrong in either direction — 1 where 268 was due, 44 where 28
was. Interposing a plain `WITH` before the aggregating clause gave the correct
answer in every case measured, which is why all seven aggregate sites in this
catalogue now do it. They were measured as correct without it; that correctness
was incidental, and it depended on where their filters happened to sit.

The original demonstration, for the record:

    MATCH (c:Claim) RETURN count(c)                            19,716  correct
    MATCH ()-[r:FOR]->() RETURN count(r)                       19,740  correct
    MATCH (c:Claim)-[:FOR]->(p:Period) RETURN count(c)          3,280  WRONG
    MATCH (c:Claim)-[:FOR]->(p:Period) WITH c RETURN count(c)  19,716  correct
    MATCH (c:Claim)-[:FOR]->(p:Period)
      WHERE p.id = "2026-Q1" RETURN count(c)                       44  WRONG
    ... WITH c RETURN count(c)                                      28  correct

Returning the rows and counting them client-side is also correct. The two shapes
`etl/load.py` verifies with — a bare label count and a bare edge-type count —
are both in the correct column, which is why the loader's read-back is sound.

**`ORDER BY` cannot see an alias introduced in `RETURN`. The sort is silently
dropped.** No error, and the rows come back in an arbitrary order that often
looks plausible:

    MATCH (l:PLLine) WITH l
    RETURN l.booked_value AS v ORDER BY v ASC
    -> 5100000, 1250000, 900000, 40000, 120000, 820000 ...   NOT SORTED

    ... RETURN l.booked_value AS v ORDER BY l.booked_value ASC
    -> 40000, 120000, 310000, 640000 ...                     correct

    MATCH (l:PLLine) WITH l, l.booked_value AS v
    RETURN v ORDER BY v ASC
    -> 40000, 120000, 310000, 640000 ...                     correct

Project the alias through a `WITH` before ordering on it. Five queries here had
this — Q8, Q11, Q13, Q20 and Q25 — and three were genuinely mis-sorted. Q20 was
the worst: it asks which channel has the best CAC, and the best CAC was the last
row on screen. Q11 and Q25 happened to come back in the right order anyway,
which is exactly how this survives review.

**Pin the period on BOTH sides of any comparison.** Found the hard way: without
it, the paid-social reconciliation compares a Q4 read against a Q1 one and
returns a confident 71% gap that means nothing. The graph is right, the query
looks right, and the answer is wrong — which is the dangerous kind.
"""

from __future__ import annotations

from queries.questions_decisions import DECISIONS
from queries.questions_evidence import EVIDENCE

#: Order is the demo running order, not an arbitrary sort. Evidence first —
#: a reallocation argued before its evidence is established is just an opinion.
QUESTIONS: list[dict] = EVIDENCE + DECISIONS
