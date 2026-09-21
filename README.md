# Marketing Attribution Knowledge Graph

**20,102 nodes. 78,752 edges.** Every measurement read a brand takes about its own
media — from every method — held as claims with the run, the data and the lineage
behind each one, so any booked number can be walked back to its source.

> Part of the **Samyama** ecosystem — loaded into and queried via the graph engine at
> [samyama-ai/samyama-graph](https://github.com/samyama-ai/samyama-graph).
> This repo holds the loader, the synthetic ledger and the question catalogue.

<a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache_2.0-blue" alt="License"></a>

> **Status.** The schema, the generator, the loader and the 24-question catalogue are
> all on `main`. Four commands in [Quick start](#quick-start) take you from an empty
> engine to a loaded graph answering questions — **20,102 nodes / 78,752 edges, all 24
> questions answering, all 15 planted findings present.**

---

A brand measures the same channel several ways at once. A mix model, a geo holdout, an
incrementality test, what the platform reports, a multiplier on top. The answers never
match, because the methods observe different things over different windows under different
assumptions — and all of them are honest.

Someone picks one and books it into the marketing P&L. A quarter later, nobody can say
which one, or why, or what it rested on.

> *"Our MMM says $2.0M and the geo test says $1.2M. Which do we book?"*

```cypher
// Two independent methods, one channel, one quarter - sized, not averaged.
// Every filter lands BEFORE the two claims are paired, and the period is
// pinned on both sides.
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
```

| p.id | ma.kind | a.value | mb.kind | b.value | gap | gap_pct |
|---|---|---:|---|---:|---:|---:|
| 2026-Q1 | mmm | 2,000,000 | geo | 1,200,000 | 800,000 | 40 |

The `WITH` between every `MATCH` is not style. Written the obvious way - pair the two
claims first, filter afterwards - this matches roughly 2,500 claims on each side and tries
to build six million pairs. It does not return slowly; it takes the engine down. At 115
nodes the readable version is instant, which is why a demo that only ever runs small is
not evidence of anything.

**Nothing stored that gap.** It is computed at read time from the raw claims — there is no
`AGREES_WITH` edge in this graph, and the loader is forbidden from writing one. That is the
difference between a ledger and an opinion saved to disk.

The graph does not pick a winner and does not average the two. It sizes the disagreement,
names what each read rests on, and leaves the decision where it belongs.

---

## Measured

Every figure below is read from the engine as it runs. Nothing here is asserted.

| | |
|---|---|
| 20,102 nodes / 78,752 edges | loads in **40.5s**, every count read back from the engine |
| 24 questions | all answering, **1.6s** for the whole catalogue |
| 8 quarters · 65 SKUs · 210 DMAs · 19,716 claims | 5 methods, 8 channels, 2 segments |
| 15 planted findings | all present, asserted by [`data/verify_data_coverage.py`](data/verify_data_coverage.py) |

## What is loaded

**20,102 nodes across 16 labels.** Read back out of the engine by `python -m etl.probe_readme --record`, which [`tests/test_readme.py`](tests/test_readme.py) holds this page to.

| Label | Count | |
|---|---:|---|
| `Claim` | 19,716 | one measurement read — a method's answer for one channel, period and cut |
| `Market` | 210 | a DMA a geo test can be run in |
| `Product` | 65 | a SKU a claim can be broken down to |
| `Run` | 41 | one execution of a method, with the date it ran |
| `Spend` | 16 | what was actually spent on a channel in a period |
| `Dataset` | 10 | a table a run consumed, with the date it last refreshed |
| `Channel` | 8 | a media channel a claim is about |
| `PLLine` | 8 | a line in the marketing P&L — a booked number |
| `Period` | 8 | a quarter |
| `Method` | 5 | a way of measuring: mmm, geo, incrementality, platform, multiplier |
| `Source` | 4 | the system a dataset ultimately came from |
| `Study` | 3 | a commissioned piece of measurement work |
| `Decision` | 2 | a budget decision taken, and the evidence it cited |
| `GeoTest` | 2 | a geo holdout, and the markets it held out |
| `PlanningCycle` | 2 | the planning round a period belongs to |
| `Segment` | 2 | a customer cut a claim can be broken down to |

**78,752 edges across 16 types.**

| Edge | Count | |
|---|---:|---|
| `ABOUT` | 39,166 | claim or decision → what it concerns (channel, product, segment, market) |
| `FOR` | 19,740 | claim, P&L line or spend → the period it covers |
| `PRODUCED` | 19,716 | run → the claims it output |
| `EXECUTED_AS` | 41 | method → each run of it |
| `CONSUMED` | 40 | run → the datasets it read |
| `ON` | 16 | spend → the channel it went to |
| `BOOKED_FROM` | 8 | P&L line → the claim it was booked from |
| `DERIVED_FROM` | 7 | dataset → the dataset upstream of it |
| `COMMISSIONED` | 3 | study → the run it commissioned |
| `DUE_FOR` | 3 | study → the period it reports on |
| `EXTRACTED_FROM` | 3 | dataset → the source system it came out of |
| `CITED` | 2 | decision → the claim it cited |
| `EXECUTED_TEST` | 2 | run → the geo test it executed |
| `FOR_CYCLE` | 2 | P&L line → its planning cycle |
| `IN_CYCLE` | 2 | period → its planning cycle |
| `SUPERSEDES` | 1 | claim → the claim it replaced |

`Claim` is 98% of the graph, and that is the point: everything else is the structure 19,716 measurement reads hang from.

## The data is synthetic, and the findings were planted

Said plainly, because it matters to how the demo is read.

The ledger is generated, not observed. Fifteen findings were placed in it deliberately — a
channel dead in aggregate and alive on two products, a line resting on a single method, a
dataset that stopped refreshing four hops upstream of a booked number, and twelve more.
[`data/generate.py`](data/generate.py) is committed and readable, and its assumptions are
listed at the top.

What is demonstrated is not that the findings exist. It is that **the structure surfaces
them without being told where to look** — the same queries run unchanged over any claim
set, and `verify_data_coverage.py` asserts each planted finding is reachable so a change to
the generator cannot silently kill a question.

## Where every row comes from

No real or scraped marketing data, and no client. Each generator below is committed and
seeded, so two runs produce identical files.

| Generator | What it produces | |
|---|---|---|
| [`data/world.py`](data/world.py) | 8 quarters · 65 SKUs · 210 DMAs · 8 channels · 5 methods · 2 segments · 4 sources · 10 datasets | the cast. Nothing here is a finding, and changing a SKU name cannot move one |
| [`data/corpus.py`](data/corpus.py) | the ~19,600 claims around the findings | the noise the findings sit inside. No `random` anywhere — values hash from the thing they describe, so two runs are byte-identical |
| [`data/generate.py`](data/generate.py) | 41 runs, 3 studies, 2 geo tests, 8 P&L lines, 16 spend rows, 2 decisions — and the **15 planted situations** | the findings, placed by hand where they can be read without scrolling past the reference data |
| [`data/verify_data_coverage.py`](data/verify_data_coverage.py) | 15 of 15 findings reachable | fails if a generator change kills a question |

Modelled on the **shape** of cases practitioners publish openly — a channel that dies in
aggregate and lives at SKU level, a booked line resting on one method, a dataset that
stopped refreshing four hops upstream. No brand is named, no client is named, and none of
these numbers came from anyone.

## What this does not claim

It does not do marketing mix modelling. It does not run incrementality tests or geo
experiments. It does not compute attribution weights, and it holds no first-touch,
last-touch or time-decay values.

Those are the practitioner's, and they stay there. Claims arrive from methods already
formed; the graph rolls them up and down granularity, compares them across methods, and
traces them back to the data underneath. The moment it calculated one of those numbers
itself, it would be an attribution model rather than a ledger.

Nor is the modelling itself graph-shaped. A mix model is regression over weekly aggregates,
an incrementality test is a randomised experiment, platform reporting is a windowed
aggregation. A columnar store with a stats library beside it serves all of that better than
a graph does, and this repo does not pretend otherwise.

What is graph-shaped is the structure those methods report into: provenance at a depth not
known when the query is written, reachability from one stale dataset to every number
standing on it, and agreement computed across independent methods.

## Quick start

```bash
docker run -d --rm -p 8080:8080 public.ecr.aws/f9f6l5u4/samyama-graph:1.1.0
python data/generate.py
python etl/load.py --url http://localhost:8080
python queries/run.py --url http://localhost:8080
```

Four commands, no database to install. The loader reads every count back out of the engine
and fails loudly on a mismatch rather than reporting success.

Always load into a fresh engine. A property cannot be unwritten on this engine — `REMOVE`
reports success and changes nothing — so a reload over an existing graph carries the old
state forward silently.

## What is in the graph

`Method` → `Run` → `Claim`, with `Dataset` chains running back to `Source`, and `PLLine`,
`Spend` and `Decision` on the outcome side. Sixteen labels, sixteen edge types, a written
reason beside every choice.

[`schema/`](schema/) has the model and the measured engine behaviours. Read the engine
notes before writing queries: several constructs return a wrong answer with no error.

[`queries/`](queries/) has the 24 questions, each in the words someone would actually ask,
and each ending in a decision rather than a finding.

## The query catalogue

**24 questions across 7 categories**, each in the words someone would actually ask, each ending in a decision rather than a finding. All 24 answer against the loaded graph in 1.6s. Full Cypher, persona, tags and design notes in [`queries/catalogue.py`](queries/catalogue.py).

| id | Question | Asked by | Category |
|---|---|---|---|
| Q1 | Where did this number come from? | CFO, in the quarterly review | Provenance & Audit |
| Q2 | Which of our booked numbers have no traceable source at all? | CFO | Provenance & Audit |
| Q3 | Who else used that dataset, and did they get the same answer? | analytics lead | Provenance & Audit |
| Q4 | Which numbers came from runs executed before the quarter even closed? | CFO, finance controller | Provenance & Audit |
| Q5 | Our MMM says $2.0M and the geo test says $1.2M. Which do we book? | analytics lead, before the number goes to finance | Method Reconciliation |
| Q6 | Where our methods agree — is that real, or two runs off the same data? | analytics lead | Method Reconciliation |
| Q7 | Which channels have never been measured by more than one method? | analytics lead, CMO | Method Reconciliation |
| Q8 | When these two methods disagree, is one of them systematically higher? | analytics lead, data scientist | Method Reconciliation |
| Q9 | This data was stale. What else is wrong? | whoever just found out, usually at the worst moment | Data Freshness & Blast Radius |
| Q10 | If we re-ran everything today, which numbers would move most? | CFO, analytics lead | Data Freshness & Blast Radius |
| Q11 | Which source system, if it went down, would invalidate the most booked value? | CFO, data lead | Data Freshness & Blast Radius |
| Q12 | How old is the oldest data any current number rests on? | CFO | Data Freshness & Blast Radius |
| Q13 | Is this one method's opinion, or all of them? | CFO, CMO | Confidence & Corroboration |
| Q14 | Which of our biggest budget lines have the thinnest evidence? | CFO | Confidence & Corroboration |
| Q15 | Where did we act on a single-method read and later find out it was wrong? | analytics lead, CMO | Confidence & Corroboration |
| Q16 | The model says kill this channel. Is that true at every product, or only on average? | CMO | Growth & Alpha |
| Q17 | Which channels look weak overall but strong in one segment? | CMO | Growth & Alpha |
| Q19 | Which upper-funnel channels do our click-based methods never see? | CMO | Growth & Alpha |
| Q20 | Which channel has our best CAC and the least budget? | CMO | Growth & Alpha |
| Q21 | We ran this test last quarter. Do we need to run it again, or does it still hold? | analytics lead, CMO | Compounding & Memory |
| Q22 | Which decisions did we take on evidence that has since been superseded? | CMO, CFO | Compounding & Memory |
| Q23 | Have we already answered this question before? | anyone, at any point | Compounding & Memory |
| Q24 | If we shift budget from paid social to CTV, what supports that and what contradicts it? | CMO, taking it to the board | Reallocation |
| Q25 | What is the largest reallocation we can justify on corroborated evidence only? | CFO and CMO together | Reallocation |

## Structure

| | |
|---|---|
| [`schema/`](schema/) | the model, and the engine behaviours measured against it |
| [`data/`](data/) | the generators, the seeded ledger and the coverage check |
| [`etl/`](etl/) | the loader, the engine client and `probe_readme` |
| [`queries/`](queries/) | the 24 questions, their Cypher and the runner |
| [`tests/`](tests/) | the front page held to the run that produced it |
| [`docs/`](docs/) | the design decisions, and the records the page is pinned to |
| [`demo/`](demo/) | the demo script, beat by beat |
| [`app/`](app/) · [`mcp_server/`](mcp_server/) · [`benchmarks/`](benchmarks/) | specified, not built — a README each, no code |

## Tests

```bash
python -m pytest tests/ -q
```

No engine needed — they read the committed record. To re-measure after a change to the
generator or the loader:

```bash
python -m etl.probe_readme --url http://localhost:8080 --record
```

## Status

| | |
|---|---|
| Schema | ✅ 46 statements, verified against the engine on load |
| Generators | ✅ seeded, committed, 15 planted findings |
| Loader | ✅ every count read back out of the engine, refuses a non-empty engine |
| **Graph loaded** | ✅ **20,102 nodes, 78,752 edges** in 40.5s |
| Question catalogue | ✅ **24 of 24 answer**, 1.6s for the whole run |
| Front page pinned to a run | ✅ `probe_readme` + `tests/test_readme.py` |
| MCP server | ⬜ specified, not built |
| App | ⬜ specified, not built |
| Benchmarks | ⬜ specified, not run |
| Snapshot release | ⬜ load takes 40s from CSV; no `.sgsnap` published yet |

## Links

| | |
|---|---|
| Samyama Graph | [github.com/samyama-ai/samyama-graph](https://github.com/samyama-ai/samyama-graph) |
| The Book | [samyama-ai.github.io/samyama-graph-book](https://samyama-ai.github.io/samyama-graph-book/) |
| Contact | [samyama.dev/contact](https://samyama.dev/contact) |

## License

Apache-2.0. See [LICENSE](LICENSE).
