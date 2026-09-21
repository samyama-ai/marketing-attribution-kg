"""Questions E–G — what should we do, and have we learnt anything?

Growth and alpha, compounding and memory, reallocation. These take the evidence
established in `questions_evidence.py` as given and ask what follows from it, so
every one ends in a decision rather than a finding.

Split out of `catalogue.py` purely for size. The engine behaviours that shaped
these queries are documented there.
"""

from __future__ import annotations

DECISIONS: list[dict] = [

    # ================= E · Growth & Alpha ==============================
    dict(
        id="Q16", category="Growth & Alpha",
        question="The model says kill this channel. Is that true at every product, or only on average?",
        persona="CMO",
        tags=["granularity", "growth", "alpha", "aggregation-trap", "hero"],
        design_notes=(
            "Same method, same period, two granularities, opposite "
            "conclusions. The graph does not compute anything here — both "
            "reads already exist, and all it does is put them side by side. "
            "That distinction matters: the moment we calculate a per-product "
            "incrementality we have built an attribution model."),
        cypher="""
MATCH (c:Claim)-[:ABOUT]->(ch:Channel) WHERE ch.name = "Podcast"
WITH c
MATCH (c)-[:FOR]->(p:Period) WHERE p.id = "2026-Q1"
WITH c WHERE c.metric = "contribution"
OPTIONAL MATCH (c)-[:ABOUT]->(prod:Product)
RETURN c.granularity, prod.sku, c.value
ORDER BY c.value DESC
""",
        expects="40,000 at channel level, +310,000 and +260,000 on two SKUs",
        ends_in="do not kill it — reallocate within it"),

    dict(
        id="Q17", category="Growth & Alpha",
        question="Which channels look weak overall but strong in one segment?",
        persona="CMO",
        tags=["segmentation", "growth", "alpha"],
        design_notes=(
            "Structurally the same traversal as Q16 on a different dimension "
            "— which is the point. One structure, many cuts, no new code."),
        cypher="""
MATCH (c:Claim)-[:ABOUT]->(ch:Channel)
WITH c, ch
MATCH (c)-[:FOR]->(p:Period) WHERE p.id = "2026-Q1"
WITH c, ch WHERE c.metric = "contribution"
OPTIONAL MATCH (c)-[:ABOUT]->(seg:Segment)
WITH ch, c, seg WHERE c.granularity <> "channel+product"
RETURN ch.name, c.granularity, seg.name, c.value
ORDER BY ch.name, c.value DESC
""",
        expects="affiliate weak at channel level, strongly positive for Discount only",
        ends_in="fund it against that segment, not the whole business"),

    dict(
        id="Q19", category="Growth & Alpha",
        question="Which upper-funnel channels do our click-based methods never see?",
        persona="CMO",
        tags=["blind-spot", "upper-funnel", "method-limits", "hero"],
        design_notes=(
            "The finding is an ABSENCE. A click-based method structurally "
            "cannot produce a claim about an upper-funnel channel, so the "
            "answer is a hole in the graph. A dashboard cannot show you what "
            "it never collected."),
        cypher="""
MATCH (ch:Channel) WHERE ch.funnel_stage = "upper"
WITH ch
MATCH (c:Claim)-[:ABOUT]->(ch)
WITH ch, c
MATCH (c)-[:FOR]->(p:Period) WHERE p.id = "2026-Q1"
WITH ch, c
MATCH (m:Method)-[:EXECUTED_AS]->(:Run)-[:PRODUCED]->(c)
WITH ch, m
WITH ch, collect(DISTINCT m.kind) AS seen_by,
     collect(DISTINCT m.observes) AS how
RETURN ch.name, ch.funnel_stage, seen_by, how
""",
        expects="upper-funnel channels seen only by modelled and experimental methods, never clicks",
        ends_in="it is not underperforming, it is unmeasured — fund a geo test"),

    dict(
        id="Q20", category="Growth & Alpha",
        question="Which channel has our best CAC and the least budget?",
        persona="CMO",
        tags=["growth", "alpha", "reallocation", "cac"],
        design_notes=(
            "Where the ledger stops being defensive and finds money. Needs "
            "spend in the graph — without it nothing can end in a "
            "reallocation, which is why Spend is a first-class node."),
        cypher="""
MATCH (c:Claim)-[:ABOUT]->(ch:Channel) WHERE c.metric = "cac"
WITH c, ch
MATCH (c)-[:FOR]->(p:Period) WHERE p.id = "2026-Q1"
WITH c, ch WHERE c.granularity = "channel"
MATCH (s:Spend)-[:ON]->(ch)
WITH c, ch, s
MATCH (s)-[:FOR]->(sp:Period) WHERE sp.id = "2026-Q1"
WITH ch, c.value AS cac, s.amount AS spend
RETURN ch.name, cac, spend
ORDER BY cac ASC
""",
        expects="the cheapest CAC sitting on the smallest budget",
        ends_in="shift budget toward it"),

    # ================= F · Compounding & Memory ========================
    dict(
        id="Q21", category="Compounding & Memory",
        question="We ran this test last quarter. Do we need to run it again, or does it still hold?",
        persona="analytics lead, CMO",
        tags=["memory", "compounding", "study-roadmap"],
        design_notes=(
            "The compounding question phrased as something a client actually "
            "says. A warehouse stores numbers; it has nowhere to put what was "
            "believed, when, and whether it still stands."),
        cypher="""
MATCH (st:Study)-[:COMMISSIONED]->(r:Run)-[:PRODUCED]->(c:Claim)
WITH st, r, c
MATCH (c)-[:ABOUT]->(ch:Channel)
WITH st, r, c, ch
OPTIONAL MATCH (c)<-[:SUPERSEDES]-(newer:Claim)
RETURN st.question, st.status, ch.name, c.value AS answered_then,
       newer.value AS reads_now
ORDER BY st.question
""",
        expects="studies with their answers, and whether anything has since replaced them",
        ends_in="this one still holds; re-run that one"),

    dict(
        id="Q22", category="Compounding & Memory",
        question="Which decisions did we take on evidence that has since been superseded?",
        persona="CMO, CFO",
        tags=["memory", "decisions", "hindsight"],
        design_notes=(
            "The ledger holding the programme to account rather than the "
            "numbers. Requires Decision to be a first-class node — a "
            "warehouse has nowhere to put 'what we decided and why'."),
        cypher="""
MATCH (d:Decision)-[:CITED]->(c:Claim)
WITH d, c
OPTIONAL MATCH (c)<-[:SUPERSEDES]-(newer:Claim)
WITH d, c, newer
MATCH (d)-[:FOR_CYCLE]->(cyc:PlanningCycle)
RETURN d.taken_on, d.rationale, cyc.name, c.value AS evidence_then,
       newer.value AS evidence_now
ORDER BY d.taken_on
""",
        expects="both decisions, one of them standing on evidence since replaced",
        ends_in="revisit that decision at the next board cycle"),

    dict(
        id="Q23", category="Compounding & Memory",
        question="Have we already answered this question before?",
        persona="anyone, at any point",
        tags=["memory", "reuse", "compounding"],
        design_notes=(
            "Makes the asset argument concrete. Every quarter of work makes "
            "this answer richer — the difference between a service that is "
            "consumed and an asset that accumulates."),
        cypher="""
MATCH (ch:Channel) WHERE ch.name = "Affiliate"
WITH ch
MATCH (c:Claim)-[:ABOUT]->(ch)
WITH ch, c
MATCH (c)-[:FOR]->(p:Period)
WITH ch, c, p
MATCH (m:Method)-[:EXECUTED_AS]->(:Run)-[:PRODUCED]->(c)
RETURN p.id, m.kind, c.granularity, c.metric, c.value
ORDER BY p.id, c.value DESC
""",
        expects="every prior read on one channel, across both quarters",
        ends_in="we already know this — no new study needed"),

    # ================= G · Reallocation ================================
    dict(
        id="Q24", category="Reallocation",
        question="If we shift budget from paid social to CTV, what supports that and what contradicts it?",
        persona="CMO, taking it to the board",
        tags=["reallocation", "decision", "triangulation", "hero"],
        design_notes=(
            "The closing move. Every version of the truth in one place "
            "instead of four people each holding one of them — which is the "
            "whole argument for the ledger, made in a single answer."),
        cypher="""
MATCH (c:Claim)-[:ABOUT]->(ch:Channel)
WHERE ch.name = "Paid Social" OR ch.name = "CTV"
WITH c, ch
MATCH (c)-[:FOR]->(p:Period) WHERE p.id = "2026-Q1"
WITH c, ch WHERE c.metric = "contribution" AND c.granularity = "channel"
MATCH (m:Method)-[:EXECUTED_AS]->(:Run)-[:PRODUCED]->(c)
WITH ch, m, c
MATCH (s:Spend)-[:ON]->(ch)
WITH ch, m, c, s
MATCH (s)-[:FOR]->(sp:Period) WHERE sp.id = "2026-Q1"
RETURN ch.name, m.kind, c.value, s.amount
ORDER BY ch.name, c.value DESC
""",
        expects="both channels, every method's read, and what is currently spent on each",
        ends_in="make the shift, with the dissent recorded"),

    dict(
        id="Q25", category="Reallocation",
        question="What is the largest reallocation we can justify on corroborated evidence only?",
        persona="CFO and CMO together",
        tags=["reallocation", "confidence", "governance"],
        design_notes=(
            "Ties the whole ledger together — provenance, independence and "
            "spend in one answer. It shows what the ledger is FOR: not being "
            "right about everything, but knowing which things you are "
            "entitled to act on."),
        cypher="""
MATCH (ch:Channel)<-[:ABOUT]-(c:Claim)-[:FOR]->(p:Period)
WHERE p.id = "2026-Q1"
WITH ch, c
MATCH (m:Method)-[:EXECUTED_AS]->(:Run)-[:PRODUCED]->(c)
WITH ch, m
WITH ch, collect(DISTINCT m.kind) AS kinds
WHERE size(kinds) > 1
WITH ch, kinds
MATCH (s:Spend)-[:ON]->(ch)
WITH ch, kinds, s
MATCH (s)-[:FOR]->(p:Period) WHERE p.id = "2026-Q1"
WITH ch, kinds, size(kinds) AS methods, s.amount AS defensible_spend
RETURN ch.name, methods, kinds, defensible_spend
ORDER BY defensible_spend DESC
""",
        expects="only the channels with two or more independent methods behind them",
        ends_in="this much we can defend; the rest needs another method first"),
]
