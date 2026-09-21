# schema/

Graph model for marketing measurement.

A **Claim** is the centre of the graph. Every other label exists to say where a
claim came from, what it is about, and what was booked or decided from it.

We are not modelling how customers buy. We are modelling **how the brand knows
what it knows** — the graph holds claims, not customers. It is the methods being
recorded, not the company's underlying data.

## Where a graph helps, and where it does not

The modelling itself is not graph-shaped. MMM is regression over weekly
aggregates, incrementality is a randomised experiment, platform reporting is a
windowed aggregation. All of that belongs in a columnar store with a stats
library beside it, and a graph adds nothing to any of it.

What is graph-shaped is the structure those models report into: provenance of
unknown depth, reachability from a stale dataset to every number standing on it,
and agreement across independent methods. That is all this schema holds.

## Core entities

- **Method** — how a number was produced: `mmm | geo | incrementality | platform | multiplier`
- **Run** — one execution of a method, at a time, on a window of data
- **Claim** — one method's answer, about one thing, for one period. Never a fact
- **Dataset** — what a run consumed; derives from other datasets, several deep
- **Source** — the system of record an extract came from
- **Channel · Product · Segment · Period** — what a claim is about
- **PLLine** — a line in the marketing P&L. The trial balance
- **Spend** — what was actually invested. Without it nothing ends in a reallocation
- **Decision** — what someone did, and what they cited

Tier 5, for the seasonal DTC pitch, cut as one block if the pitch changes:
**GeoTest** (the design behind a geo read), **Study** (the question a run
answers), **PlanningCycle** (the calendar the business decides on).

## Core relationships

```
(Method)-[:EXECUTED_AS]->(Run)-[:PRODUCED]->(Claim)
(Run)-[:CONSUMED]->(Dataset)-[:DERIVED_FROM]->(Dataset)   // chains 3-4 deep
(Dataset)-[:EXTRACTED_FROM]->(Source)
(Claim)-[:ABOUT]->(Channel | Product | Segment)
(Claim)-[:FOR]->(Period)
(Claim)-[:SUPERSEDES]->(Claim)
(PLLine)-[:BOOKED_FROM]->(Claim)
(Spend)-[:ON]->(Channel)
(Decision)-[:CITED]->(Claim)
```

`DERIVED_FROM` is the edge that earns the graph. The depth from a booked number
to its system of record is not known when the query is written, and differs per
method — which is what the provenance and blast-radius questions traverse.

## Deliberately not modelled

**No Customer, Session, Touchpoint or Journey.** That is a customer-journey
graph, and it is the wrong model here twice over: it is the reviewer's own
patent territory, and the questions it answers — first touch, last touch, most
common path, channel co-occurrence — are `GROUP BY` and window functions over an
event table that a columnar store serves better. A journey is a chain, not a
network. Where one exists it enters this graph as a `Dataset` that an
attribution `Run` consumed — one node, not a layer.

**No AGREES_WITH or CONFLICTS_WITH edge.** Ever. Agreement between two methods is
computed at read time from the raw claims. If the loader writes it, we are
asserting agreement rather than computing it.

**No attribution weights**, and the graph never computes a measurement. Claims
arrive from methods; the graph rolls them up and down granularity, compares them
and traces them.

## The file

`marketing_attribution_kg.cypher` — 15 labels, 16 edge types, keys and indexes,
with the reasoning written beside every choice and the measured engine
behaviours at the foot. Read the engine notes before writing queries: several
constructs return a wrong answer with no error.
