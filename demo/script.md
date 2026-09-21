# Demo script

The running order for a live walkthrough, written so someone who did not build
this can present it. Each act carries the question in the words a client would
use, the command, what comes back, and what to say over it.

**Roughly twelve minutes at a normal pace.** Every query answers in under a
fifth of a second, so the pauses are yours to place, not the engine's.

---

## Before you start

```bash
docker rm -f samyama-demo 2>/dev/null
docker run -d --rm --name samyama-demo -p 8080:8080 \
  public.ecr.aws/f9f6l5u4/samyama-graph:1.1.0
python data/generate.py
python etl/load.py --url http://localhost:8080
```

The container is named so it can be replaced later, and the `docker rm -f` is
first because a wedged container still holds its port — `docker run` then fails
with `Bind for 0.0.0.0:8080 failed: port is already allocated`, which is not
what you want to be reading mid-demo.

Roughly forty seconds altogether. **Do this before anyone is watching** — the
load is thirty-two of those seconds and there is nothing to see.

Confirm you are ready:

```
20,102 nodes / 78,752 edges in 32.0s
verified — every count read back from the engine
```

Then leave a terminal open at the repo root. Every command below is run from
there.

---

## Opening — thirty seconds, no terminal

> A brand measures the same channel several ways at once. A mix model, a geo
> holdout, an incrementality test, what the platform reports. The answers never
> match — because the methods observe different things, over different windows,
> under different assumptions. **All of them are honest.**
>
> Someone picks one and books it into the marketing P&L. A quarter later,
> nobody can say which one, or why, or what it rested on.
>
> This is a record of that. Not a model — a ledger of who measured what, off
> which data, and whether anyone ever checked.

Say the scope out loud here, once, and do not repeat it:

> Everything you are about to see is synthetic. Invented brand, invented
> numbers. What is real is the structure and the questions.

---

## Act 1 — The divergence

**The question:** *"Our MMM says $2.0M and the geo test says $1.2M. Which do we
book?"*

```bash
python queries/run.py --url http://localhost:8080 --only Q5
```

```
['2026-Q1', 'mmm', 2000000, 'geo', 1200000, 800000, 40]
```

> Two credible methods. One channel, one quarter. An eight-hundred-thousand
> dollar disagreement — forty percent.

**The line that matters, and the one to slow down on:**

> Nothing in this graph stored that gap. It was computed at read time, from the
> raw claims. **There is no `AGREES_WITH` edge here** — the loader is forbidden
> from writing one.
>
> The moment agreement becomes something you save, it is a judgement somebody
> made once, about data that has since moved.

**Ends in a decision, not a finding:** book the geo read, flag the 40% as brand
effect the test cannot see, schedule a longer test.

*Why this opens:* it is the most familiar thing in the room. Nobody is surprised
yet — that is the point. It sets the frame the next four acts pay off.

---

## Act 2 — Agreement that does not count

**The question:** *"Where our methods agree — is that real, or two runs off the
same data?"*

```bash
python queries/run.py --url http://localhost:8080 --only Q6
```

```
['geo', 'incrementality', 'ds-pos-orders', 'POS order lines']
['geo', 'incrementality', 'ds-pos-orders', 'POS order lines']
['geo', 'incrementality', 'ds-pos-orders', 'POS order lines']
['geo', 'incrementality', 'ds-pos-orders', 'POS order lines']
['geo', 'incrementality', 'ds-pos-orders', 'POS order lines']
['geo', 'incrementality', 'ds-pos-orders', 'POS order lines']
 … 269 more (use --limit 275 to see them)
```

**Know this before you run it:** the output repeats. 275 rows carrying six
distinct method pairs, because the query returns one row per shared lineage path
rather than one per pair — `multiplier`/`platform` appears twice, once for each
of two shared datasets. Point at the first line and move on; do not scroll.
The pair that matters is `geo` and `incrementality`, and the root they share is
`ds-pos-orders`.

*(The other five are real too — `multiplier` and `platform` also share
`ds-platform-daily`, and several share the POS table. Mention them only if
someone asks; the story is cleaner with one.)*

> Two different methods, landing on the same answer. That reads as
> confirmation.
>
> They both descend from the same POS order table. Four hops up a chain nobody
> declared. It is not two independent reads — it is the same evidence, counted
> twice.

**Ends in:** that agreement does not count. Get a genuinely independent read
before anyone cites it.

*This is the beat that lands.* Everyone in the room already knows corroboration
requires independence. What they have never had is a system that **notices when
it was not**, without anyone thinking to ask. Give it a beat of silence.

If you show only one query, show this one.

---

## Act 3 — Blast radius

**The question:** *"This data was stale. What else is wrong?"*

```bash
python queries/run.py --url http://localhost:8080 --only Q9 --limit 12
```

**Use `--limit 12`.** The default prints six rows, and because each line appears
twice you would show three names while saying six — inviting the room to count
and find you wrong.

```
['ds-panel-raw',    '2025-10-14', 'Paid Search contribution', 5100000]
['ds-panel-weekly', '2025-10-15', 'Paid Search contribution', 5100000]
['ds-panel-raw',    '2025-10-14', 'CTV contribution',          900000]
['ds-panel-weekly', '2025-10-15', 'CTV contribution',          900000]
['ds-panel-raw',    '2025-10-14', 'Email contribution',        820000]
['ds-panel-weekly', '2025-10-15', 'Email contribution',        820000]
['ds-panel-raw',    '2025-10-14', 'Organic contribution',      310000]
['ds-panel-weekly', '2025-10-15', 'Organic contribution',      310000]
['ds-panel-raw',    '2025-10-14', 'Affiliate contribution',    120000]
['ds-panel-weekly', '2025-10-15', 'Affiliate contribution',    120000]
['ds-panel-raw',    '2025-10-14', 'Podcast contribution',       40000]
['ds-panel-weekly', '2025-10-15', 'Podcast contribution',       40000]
```

**Say six lines, not twelve rows.** Each name appears twice because two datasets
in the same chain went stale — `ds-panel-raw` and the weekly aggregate derived
from it. With all twelve on screen the pairing is visible, so the count holds up
if anyone checks it.

> Two datasets in one chain stopped refreshing in October. Six booked lines are
> standing on them — and the distance from the dataset to each line is
> different, and none of it was known when the question was asked.

Then turn it around — the same structure, asked forwards:

```bash
python queries/run.py --url http://localhost:8080 --only Q11
```

```
['src-panel',         6, 7290000]
['src-pos',           1, 1250000]
['src-platform-api',  1,  640000]
```

> One vendor is carrying **$7.29M** of booked value. Seventy-nine percent.
> Nobody chose that. It accumulated.

**Ends in:** unbook those lines, re-run, tell finance before they find out — and
get a second feed behind that source.

*Optional, and only if someone leans in:* this is the beat with no tabular
equivalent. In a warehouse the hop count has to be known when the query is
written, and here it differs per line. Say it once if it is useful; do not
labour it.

---

## Act 4 — How thin is the evidence

**The question:** *"Is this one method's opinion, or all of them?"*

```bash
python queries/run.py --url http://localhost:8080 --only Q13 --limit 8
```

**Use `--limit 8`.** This question sorts thinnest-evidence-first, so its payoff
— the CTV and Paid Social rows — is the last two of eight. At the default six
they are hidden behind `… 2 more`, and the line below about "five methods
behind it" points at something nobody can see.

```
['Paid Search contribution', 5100000, 1, ['mmm']]
['Email contribution',        820000, 1, ['mmm']]
['Display contribution',      640000, 1, ['platform']]
['Organic contribution',      310000, 1, ['mmm']]
['Affiliate contribution',    120000, 1, ['mmm']]
['Podcast contribution',       40000, 1, ['mmm']]
['CTV contribution',          900000, 2, ['geo','mmm']]
['Paid Social contribution', 1250000, 5, ['geo','incrementality','mmm','multiplier','platform']]
```

> Sorted by how many independent methods stand behind each line, not by size.
> Thinnest evidence first.
>
> The largest line in the P&L — five point one million — is at the top, resting
> on exactly one method. The line at a quarter of its size is at the bottom with
> five behind it.

> That is confidence expressed as **agreement between independent methods**
> rather than as a p-value. It is how a practitioner already thinks about it,
> and it is a number a CFO can act on.

**Ends in:** corroborate the top line before the next planning cycle. Do not
shift budget on the single-method reads.

---

## Act 5 — The programme audits itself

**The question:** *"Where did we act on a single-method read and later find out
it was wrong?"*

```bash
python queries/run.py --url http://localhost:8080 --only Q15
```

```
['2026-01-22', 'Scale affiliate into Q1 on the back of a strong Q4 read',
 'Affiliate', 900000, 585000, 35]
```

> A decision cited a claim. That claim was later replaced by one thirty-five
> percent lower. Nobody reopened the decision — because nothing connected them.

**Ends in:** single-method reads do not move budget. That is now a rule with
evidence behind it rather than an opinion.

*Why this closes:* it is the only act where the graph is uncomfortable about its
own programme. It is also the answer to "why would we pay for this" — the four
acts before it are prevention, and this one is the cost of not having had it.

---

## The close — no terminal

> Every method you saw belongs to the practitioner. We do not do mix modelling,
> we do not run incrementality tests, we do not compute attribution weights, and
> we would be wrong to. A columnar store and a stats library serve that better
> than a graph ever will.
>
> **What we hold is the structure those methods report into** — and that turns
> out to answer a class of question the methods themselves cannot ask.

Stop there. Do not add a summary slide.

---

## If the room wants more

**Q16** is the strongest reserve. Ask it as: *"the model says kill this channel
— is that true at every product?"*

```bash
python queries/run.py --url http://localhost:8080 --only Q16
```

```
['channel+product', 'SKU-102',  310000]
['channel+product', 'SKU-104',  260000]
['channel',          None,       40000]
['channel+product', 'SKU-105', -160000]
['channel+product', 'SKU-101', -180000]
['channel+product', 'SKU-103', -190000]
```

> Forty thousand at channel level — barely alive, and an easy thing to cut.
> Underneath it, two products at plus three-ten and plus two-sixty, and three
> deeply negative. The answer is not to kill the channel. It is to reallocate
> inside it.

**Q19** if the conversation turns to upper funnel:

```
['CTV',     'upper', ['geo','mmm'], ['experimental','modelled']]
['Podcast', 'upper', ['mmm'],       ['modelled']]
```

> No click-based method has ever seen either of these, and structurally none can.
> They are not underperforming. They are unmeasured.

And the whole catalogue, if someone asks how many of these there are:

```bash
python queries/run.py --url http://localhost:8080 --quiet
```

```
All 24 questions answer.        # about 1.1 seconds
```

---

## Timings

Every beat, measured. Nothing here is slow enough to need covering.

| Act | Question | Time |
|---|---|---|
| 1 | Q5 | 0.13s |
| 2 | Q6 | 0.12s |
| 3 | Q9 | 0.16s |
| 3 | Q11 | 0.13s |
| 4 | Q13 | 0.13s |
| 5 | Q15 | 0.11s |
| reserve | Q16 | 0.13s |
| reserve | Q19 | 0.18s |
| — | whole catalogue | 1.1s |

---

## What not to say

Five rules. Each one is a way this demo stops working, and the script is where
they get broken first — in front of an audience, at speed.

**Never describe a gap in the practitioner's field.** Everyone in that room has
spent a career on measurement. "Here is what you could not do" is both wrong and
insulting. The surprise is not that the answer exists — they know every answer
here. It is that it took one query and nobody had to commission it.

**Never claim a measurement method.** We do not do MMM. We do not run
incrementality tests. If asked whether we could, the answer is that we would be
the wrong people, and the graph would be the wrong shape.

**Never sound like a warehouse.** "We store all your marketing data" is the
sentence that ends the conversation. What is held is claims and the evidence
under them, and the value is in what is computed at read time.

**Never name a real client, ours or theirs.** The brand in this data is
invented. Say the data is synthetic once, early, plainly — then let the
structure carry it.

**Never say the graph decides.** It sizes a disagreement, names what each read
rests on, and leaves the decision where it belongs. Every act above ends in a
recommendation a person makes, not an answer the graph gave.

---

## If something goes wrong

**A query hangs.** It should not — the runner times out at 20s and retries once,
so the worst case is about forty seconds. If the engine has gone down you will
see `unreachable` in about a second rather than a hang.

**The engine died.** It happens; a badly-shaped query has taken 1.1.0 down
before. You have two options and only one of them is fast:

*Restart and reload* — about forty seconds, in front of the room:

```bash
docker rm -f samyama-demo            # it is wedged, not gone: it still holds 8080
docker run -d --rm --name samyama-demo -p 8080:8080 \
  public.ecr.aws/f9f6l5u4/samyama-graph:1.1.0
python etl/load.py --url http://localhost:8080
```

**The `docker rm -f` is the part people skip.** A wedged engine has not exited,
so `--rm` has not fired and the port is still bound; without it the new
container refuses to start and you are debugging Docker in front of the room.

*Or switch to a warm spare* — instant, but **only if you loaded it beforehand.**
A spare container that is merely running is empty, every query returns nothing,
and the runner correctly treats that as failure — which drops you into the
"a query returns nothing" problem above while you are already recovering from
one. Set it up before anyone is watching:

```bash
docker rm -f samyama-spare 2>/dev/null
docker run -d --rm --name samyama-spare -p 8081:8080 \
  public.ecr.aws/f9f6l5u4/samyama-graph:1.1.0
python etl/load.py --url http://localhost:8081     # the part that matters
```

Then failover is `--url http://localhost:8081`. Note that `etl/load.py` refuses
a graph that already holds nodes, so the spare has to be loaded once, up front,
and left alone.

**A query returns nothing.** That is a failure, not a curiosity, and the runner
exits non-zero for it. Do not improvise around it. `python
data/verify_data_coverage.py` will say which planted finding went missing.

**Someone asks to see the data.** `data/generate.py` is committed and readable,
and the assumptions are listed at the top. The CSVs are generated rather than
committed, so there is nothing hidden and nothing to hunt for.

**Someone asks whether the findings were planted.** They were, and say so
directly. Fifteen of them, and `data/verify_data_coverage.py` asserts every one
is still reachable. What is demonstrated is not that they exist — it is that the
structure surfaces them without being told where to look, using queries written
against the schema rather than against the answers.
