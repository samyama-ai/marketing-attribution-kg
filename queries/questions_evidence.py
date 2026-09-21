"""Questions A–D — is the number true, and what does it rest on?

Provenance, method reconciliation, freshness and blast radius, corroboration.
Every one of these asks about the *evidence* under a number rather than about
what to do next; the ones that end in a budget move live in
`questions_decisions.py`.

Split out of `catalogue.py` purely for size. The engine behaviours that shaped
these queries are documented there, and reading them before editing any Cypher
here is not optional — several constructs return a wrong answer with no error.
"""

from __future__ import annotations

EVIDENCE: list[dict] = [

    # ================= A · Provenance & Audit ==========================
    dict(
        id="Q1", category="Provenance & Audit",
        question="Where did this number come from?",
        persona="CFO, in the quarterly review",
        tags=["provenance", "audit", "lineage", "cfo-trust"],
        design_notes=(
            "The hop count is not known when the query is written. An MMM "
            "claim sits three datasets deep; a platform claim sits one. A "
            "fixed set of joins cannot express 'however far back that goes', "
            "which is why this is the opening beat."),
        cypher="""
MATCH (l:PLLine) WHERE l.id = "2026-Q1|Paid Social"
WITH l
MATCH (l)-[:BOOKED_FROM]->(c:Claim)<-[:PRODUCED]-(r:Run)<-[:EXECUTED_AS]-(m:Method)
WITH l, c, r, m
MATCH (r)-[:CONSUMED]->(d:Dataset)-[:DERIVED_FROM*0..4]->(up:Dataset)
RETURN l.booked_value, m.kind, r.executed_on, c.value,
       d.name, up.name, up.refreshed_on
ORDER BY up.refreshed_on
""",
        expects="the booked line, its method and run, and the whole dataset chain behind it",
        ends_in="the number stands, and here is the paper trail"),

    dict(
        id="Q2", category="Provenance & Audit",
        question="Which of our booked numbers have no traceable source at all?",
        persona="CFO",
        tags=["provenance", "audit", "gaps"],
        design_notes=(
            "An absence question. Every ledger has orphans and nobody knows "
            "until someone asks. Answered by the run having consumed nothing "
            "— cheap here, expensive anywhere else."),
        cypher="""
MATCH (r:Run)-[:PRODUCED]->(c:Claim)
WITH r, c
OPTIONAL MATCH (r)-[:CONSUMED]->(d:Dataset)
WITH r, c, d WHERE d IS NULL
MATCH (c)-[:ABOUT]->(ch:Channel)
RETURN r.id, ch.name, c.metric, c.value
""",
        expects="two claims from a run that consumed no dataset",
        ends_in="find the source or stop booking it"),

    dict(
        id="Q3", category="Provenance & Audit",
        question="Who else used that dataset, and did they get the same answer?",
        persona="analytics lead",
        tags=["provenance", "corroboration", "shared-inputs"],
        design_notes=(
            "Inverts Q1. Two methods on the same input reaching different "
            "answers is a method difference; reaching the same answer is NOT "
            "independent corroboration — see Q6."),
        cypher="""
MATCH (d:Dataset) WHERE d.id = "ds-pos-orders"
WITH d
MATCH (d)<-[:DERIVED_FROM*0..3]-(:Dataset)<-[:CONSUMED]-(r:Run)
WITH DISTINCT r
MATCH (m:Method)-[:EXECUTED_AS]->(r)-[:PRODUCED]->(c:Claim)-[:ABOUT]->(ch:Channel)
RETURN m.kind, r.id, ch.name, c.value
ORDER BY m.kind
""",
        expects="two different method kinds descending from one order table",
        ends_in="the difference is the method, not the data"),

    dict(
        id="Q4", category="Provenance & Audit",
        question="Which numbers came from runs executed before the quarter even closed?",
        persona="CFO, finance controller",
        tags=["audit", "timing", "integrity"],
        design_notes=(
            "A forecast being booked as an actual looks identical to "
            "everything else in the P&L. Only the run date beside the period "
            "end reveals it."),
        cypher="""
MATCH (r:Run)-[:PRODUCED]->(c:Claim)-[:FOR]->(p:Period)
WHERE r.executed_on < p.ends
WITH r, c, p
MATCH (c)-[:ABOUT]->(ch:Channel)
RETURN r.id, r.executed_on, p.id, p.ends, ch.name, c.value
""",
        expects="a platform run dated inside the quarter it describes",
        ends_in="re-run it after close, or label it a forecast"),

    # ================= B · Method Reconciliation =======================
    dict(
        id="Q5", category="Method Reconciliation",
        question="Our MMM says $2.0M and the geo test says $1.2M. Which do we book?",
        persona="analytics lead, before the number goes to finance",
        tags=["reconciliation", "triangulation", "decision", "hero"],
        design_notes=(
            "The hero question. Note what is NOT here: no AGREES_WITH edge, "
            "no stored gap. The difference is computed at read time from the "
            "raw claims, which is the difference between a ledger and "
            "somebody's opinion saved to disk. "
            "**The period is pinned on both sides.** Without that this "
            "compares a Q4 read against a Q1 one and returns a confident 71% "
            "that means nothing. "
            "**And every filter is applied BEFORE the two claims are paired.** "
            "Written the obvious way — pair first, filter after — this matched "
            "roughly 2,500 claims on each side and tried to build six million "
            "pairs. It did not return slowly; it took the engine down. At 115 "
            "nodes the same query was instant, which is exactly why a demo "
            "that only ever runs small is not evidence of anything."),
        cypher="""
MATCH (a:Claim)-[:ABOUT]->(ch:Channel)
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
       round(100.0 * abs(a.value - b.value) / a.value) AS gap_pct
""",
        expects="one row: 2,000,000 against 1,200,000, a gap of 800,000, 40%",
        ends_in="book the geo read, flag the 40% as brand effect the test cannot see, schedule a longer test"),

    dict(
        id="Q6", category="Method Reconciliation",
        question="Where our methods agree — is that real, or two runs off the same data?",
        persona="analytics lead",
        tags=["reconciliation", "independence", "false-corroboration"],
        design_notes=(
            "The subtlest question in the bank, and the best test of whether "
            "we understand the field. Agreement between two methods that "
            "share an input is not corroboration — it is the same evidence "
            "counted twice. Answering it means walking BOTH lineage chains "
            "and intersecting them at a depth nobody declared."),
        cypher="""
MATCH (ra:Run)-[:CONSUMED]->(:Dataset)-[:DERIVED_FROM*0..4]->(shared:Dataset)
WITH ra, shared
MATCH (rb:Run)-[:CONSUMED]->(:Dataset)-[:DERIVED_FROM*0..4]->(shared)
WHERE ra.id < rb.id
WITH ra, rb, shared
MATCH (ma:Method)-[:EXECUTED_AS]->(ra)
WITH ra, rb, shared, ma
MATCH (mb:Method)-[:EXECUTED_AS]->(rb)
WHERE ma.kind <> mb.kind
RETURN ma.kind, mb.kind, shared.id, shared.name
""",
        expects="geo and incrementality both descending from ds-pos-orders",
        ends_in="that agreement does not count — get a genuinely independent read"),

    dict(
        id="Q7", category="Method Reconciliation",
        question="Which channels have never been measured by more than one method?",
        persona="analytics lead, CMO",
        tags=["coverage", "corroboration", "blind-spot"],
        design_notes=(
            "A gap in the measurement programme itself rather than in the "
            "data. This is the question that writes next quarter's study "
            "roadmap."),
        cypher="""
MATCH (ch:Channel)<-[:ABOUT]-(c:Claim)-[:FOR]->(p:Period)
WHERE p.id = "2026-Q1"
WITH ch, c
MATCH (m:Method)-[:EXECUTED_AS]->(:Run)-[:PRODUCED]->(c)
WITH ch, m
WITH ch, collect(DISTINCT m.kind) AS kinds
WHERE size(kinds) = 1
RETURN ch.name, kinds[0] AS only_method
""",
        expects="several channels seen by exactly one method kind",
        ends_in="these go on the study roadmap"),

    dict(
        id="Q8", category="Method Reconciliation",
        question="When these two methods disagree, is one of them systematically higher?",
        persona="analytics lead, data scientist",
        tags=["reconciliation", "bias", "systematic-error"],
        design_notes=(
            "Distinguishes bias from noise. One disagreement is a question; a "
            "consistent direction is a calibration problem — and it is what "
            "justifies a multiplier existing at all. "
            "Filters before the pairing, for the reason recorded on Q5: this "
            "one pairs across EVERY channel rather than one, so written the "
            "obvious way it is the worse of the two."),
        cypher="""
MATCH (a:Claim)-[:ABOUT]->(ch:Channel)
WHERE a.granularity = "channel" AND a.metric = "contribution"
WITH a, ch
MATCH (ma:Method)-[:EXECUTED_AS]->(:Run)-[:PRODUCED]->(a)
WHERE ma.kind = "platform"
WITH a, ch, ma
MATCH (a)-[:FOR]->(p:Period) WHERE p.id = "2026-Q1"
WITH a, ch, ma, p
MATCH (b:Claim)-[:ABOUT]->(ch)
WHERE b.granularity = "channel" AND b.metric = "contribution"
WITH a, ch, ma, p, b
MATCH (b)-[:FOR]->(pb:Period) WHERE pb.id = "2026-Q1"
WITH a, ma, b
MATCH (mb:Method)-[:EXECUTED_AS]->(:Run)-[:PRODUCED]->(b)
WHERE mb.kind <> "platform"
WITH mb, a.value - b.value AS platform_minus_other
RETURN mb.kind, platform_minus_other
ORDER BY platform_minus_other DESC
""",
        expects="platform reads above every other method, every time",
        ends_in="apply a multiplier, or stop using the platform number raw"),

    # ================= C · Freshness & Blast Radius ====================
    dict(
        id="Q9", category="Data Freshness & Blast Radius",
        question="This data was stale. What else is wrong?",
        persona="whoever just found out, usually at the worst moment",
        tags=["freshness", "blast-radius", "lineage", "risk", "hero"],
        design_notes=(
            "The beat with no tabular equivalent. The distance from the stale "
            "dataset to the booked line is not known when the query is "
            "written, and it differs per line. In a warehouse this is an "
            "analyst's week."),
        cypher="""
MATCH (stale:Dataset) WHERE stale.refreshed_on < "2025-11-01"
WITH stale
MATCH (stale)<-[:DERIVED_FROM*0..4]-(:Dataset)<-[:CONSUMED]-(:Run)
      -[:PRODUCED]->(:Claim)<-[:BOOKED_FROM]-(l:PLLine)
RETURN DISTINCT stale.id, stale.refreshed_on, l.name, l.booked_value
ORDER BY l.booked_value DESC
""",
        expects="several booked lines standing on a dataset that stopped refreshing in October",
        ends_in="unbook these, re-run, tell finance before they find out"),

    dict(
        id="Q10", category="Data Freshness & Blast Radius",
        question="If we re-ran everything today, which numbers would move most?",
        persona="CFO, analytics lead",
        tags=["freshness", "prioritisation", "risk"],
        design_notes=(
            "Turns Q9 from a fire drill into a work queue. Takes the oldest "
            "dataset anywhere beneath each line, then weights by what is "
            "booked on it — two traversals combined."),
        cypher="""
MATCH (l:PLLine)-[:BOOKED_FROM]->(:Claim)<-[:PRODUCED]-(:Run)
      -[:CONSUMED]->(:Dataset)-[:DERIVED_FROM*0..4]->(up:Dataset)
WITH l, up
WITH l, min(up.refreshed_on) AS oldest
RETURN l.name, l.booked_value, oldest
ORDER BY oldest ASC, l.booked_value DESC
""",
        expects="lines ranked by how old the data underneath them is",
        ends_in="re-run these three first"),

    dict(
        id="Q11", category="Data Freshness & Blast Radius",
        question="Which source system, if it went down, would invalidate the most booked value?",
        persona="CFO, data lead",
        tags=["blast-radius", "concentration-risk", "sources"],
        design_notes=(
            "Pure reachability in the opposite direction from Q9, with an "
            "aggregate at the end. Concentration risk nobody measures, and a "
            "question about the measurement programme rather than the "
            "marketing. "
            "**`WITH DISTINCT s, l` rather than collect-and-UNWIND**: UNWIND "
            "does not parse on this engine, and inside a larger query it "
            "returns an empty result instead of an error — which is how a "
            "correct-looking query silently answers nothing."),
        cypher="""
MATCH (s:Source)<-[:EXTRACTED_FROM]-(:Dataset)<-[:DERIVED_FROM*0..4]-(:Dataset)
      <-[:CONSUMED]-(:Run)-[:PRODUCED]->(:Claim)<-[:BOOKED_FROM]-(l:PLLine)
WITH DISTINCT s, l
WITH s, count(l) AS lines_at_risk, sum(l.booked_value) AS value_at_risk
RETURN s.id, lines_at_risk, value_at_risk
ORDER BY value_at_risk DESC
""",
        expects="one source carrying most of the booked value",
        ends_in="that source needs a second feed"),

    dict(
        id="Q12", category="Data Freshness & Blast Radius",
        question="How old is the oldest data any current number rests on?",
        persona="CFO",
        tags=["freshness", "audit", "one-number"],
        design_notes=(
            "One number summarising the ledger's whole exposure. Easy to "
            "state, and it requires walking every chain to its end."),
        cypher="""
MATCH (:PLLine)-[:BOOKED_FROM]->(:Claim)<-[:PRODUCED]-(:Run)
      -[:CONSUMED]->(:Dataset)-[:DERIVED_FROM*0..4]->(up:Dataset)
WITH up
RETURN min(up.refreshed_on) AS oldest_data_in_the_pl
""",
        expects="a single date, months before the quarter it supports",
        ends_in="the number to put in the board pack"),

    # ================= D · Confidence & Corroboration ==================
    dict(
        id="Q13", category="Confidence & Corroboration",
        question="Is this one method's opinion, or all of them?",
        persona="CFO, CMO",
        tags=["confidence", "corroboration"],
        design_notes=(
            "Confidence expressed as agreement between independent methods "
            "rather than as a p-value — which is how a practitioner in this "
            "field already thinks about it. "
            "Scoped to one period on both sides: unscoped, a 2026-Q1 line was "
            "scored as corroborated on the strength of a 2025-Q4 claim, which "
            "is the same defect Q5's note is about and it was still here."),
        cypher="""
MATCH (l:PLLine)-[:BOOKED_FROM]->(:Claim)-[:ABOUT]->(ch:Channel)
WITH l, ch
MATCH (l)-[:FOR]->(p:Period) WHERE p.id = "2026-Q1"
WITH l, ch
MATCH (c:Claim)-[:ABOUT]->(ch)
WHERE c.granularity = "channel" AND c.metric = "contribution"
WITH l, ch, c
MATCH (c)-[:FOR]->(pc:Period) WHERE pc.id = "2026-Q1"
WITH l, ch, c
MATCH (m:Method)-[:EXECUTED_AS]->(:Run)-[:PRODUCED]->(c)
WITH l, ch, m
WITH l, ch, collect(DISTINCT m.kind) AS kinds
WITH l, kinds, size(kinds) AS methods
RETURN l.name, l.booked_value, methods, kinds
ORDER BY methods ASC, l.booked_value DESC
""",
        expects="lines ranked by how many independent methods stand behind them",
        ends_in="do not shift budget on the single-method ones"),

    dict(
        id="Q14", category="Confidence & Corroboration",
        question="Which of our biggest budget lines have the thinnest evidence?",
        persona="CFO",
        tags=["confidence", "risk", "value-weighted", "hero"],
        design_notes=(
            "The client-facing version of Q13 and the one a CFO acts on. Thin "
            "evidence on a small line is tolerable; thin evidence on the "
            "largest line is a governance problem. "
            "**Scoped to the line's own period.** Across eight quarters of "
            "history every channel has been looked at by something eventually, "
            "so an unscoped version returns nothing and reads as 'no problem "
            "here' — the most dangerous empty answer in the catalogue."),
        cypher="""
MATCH (l:PLLine)-[:BOOKED_FROM]->(:Claim)-[:ABOUT]->(ch:Channel)
WITH l, ch
MATCH (l)-[:FOR]->(p:Period) WHERE p.id = "2026-Q1"
WITH l, ch, p
MATCH (c:Claim)-[:ABOUT]->(ch)
WHERE c.granularity = "channel" AND c.metric = "contribution"
WITH l, ch, p, c
MATCH (c)-[:FOR]->(pc:Period) WHERE pc.id = "2026-Q1"
WITH l, c
MATCH (m:Method)-[:EXECUTED_AS]->(:Run)-[:PRODUCED]->(c)
WITH l, m
WITH l, collect(DISTINCT m.kind) AS kinds
WHERE size(kinds) = 1
RETURN l.name, l.booked_value, kinds[0] AS only_method
ORDER BY l.booked_value DESC
""",
        expects="the largest line in the P&L, resting on exactly one method",
        ends_in="corroborate the top line before the next planning cycle"),

    dict(
        id="Q15", category="Confidence & Corroboration",
        question="Where did we act on a single-method read and later find out it was wrong?",
        persona="analytics lead, CMO",
        tags=["confidence", "hindsight", "learning"],
        design_notes=(
            "The programme auditing itself. Uncomfortable, and it produces "
            "the evidence for why corroboration is worth paying for."),
        cypher="""
MATCH (d:Decision)-[:CITED]->(old:Claim)<-[:SUPERSEDES]-(new:Claim)
WITH d, old, new
MATCH (old)-[:ABOUT]->(ch:Channel)
RETURN d.taken_on, d.rationale, ch.name,
       old.value AS believed_then, new.value AS reads_now,
       round(100.0 * (old.value - new.value) / old.value) AS overstated_pct
""",
        expects="a decision taken on a claim since replaced by a materially lower read",
        ends_in="single-method reads do not move budget"),

]
