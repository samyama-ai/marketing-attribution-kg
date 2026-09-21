// Marketing Attribution Knowledge Graph -- schema
//
// A ledger for marketing measurement. A Claim is the centre of the graph;
// every other label exists to say where a claim came from, what it is about,
// and what was booked or decided from it.
//
// We are not modelling how customers buy. We are modelling how the brand knows
// what it knows. The graph holds claims, not customers -- it is the methods
// being recorded, not the company's underlying data.
//
// Where a graph helps, and where it does not:
//   The modelling itself is NOT graph-shaped. MMM is regression over weekly
//   aggregates, incrementality is a randomised experiment, platform reporting
//   is a windowed aggregation -- all of that belongs in a columnar store with a
//   stats library, and a graph adds nothing to any of it. What is graph-shaped
//   is the structure those models report into: provenance of unknown depth,
//   reachability from a stale dataset to every number standing on it, and
//   agreement across independent methods. That is all this schema holds.
//
// Node labels -- core (tiers 1-4, per the schema brief):
//              Method, Run, Claim, Dataset, Source, Channel, Product, Segment,
//              Period, PLLine, Spend, Decision
//
// Node labels -- seasonal DTC pitch (tier 5, cut if the pitch changes):
//              GeoTest, Study, PlanningCycle
//
// Edge types:  EXECUTED_AS, PRODUCED, CONSUMED, DERIVED_FROM, EXTRACTED_FROM,
//              ABOUT, FOR, BOOKED_FROM, SUPERSEDES, CITED, ON,
//              EXECUTED_TEST, COMMISSIONED, DUE_FOR, IN_CYCLE, FOR_CYCLE
//
// Every node carries `provenance` ("real" | "synthetic") and `source`.
// This graph is synthetic and says so on every node.
//
// ---------------------------------------------------------------------------
// Engine notes -- measured on public.ecr.aws/f9f6l5u4/samyama-graph:1.1.0
//
//   Constraint syntax -- SETTLED BY MEASUREMENT, do not re-litigate:
//     CREATE CONSTRAINT ... ASSERT ... IS UNIQUE   parses.
//     CREATE CONSTRAINT ... REQUIRE ... IS UNIQUE  returns 400.
//     NEITHER ENFORCES. Nothing stops two nodes sharing a key.
//   The constraint is documentation of intent. The loader mints ids
//   deterministically and reads every count back out of the engine, and that is
//   the only real uniqueness guarantee.
//
//   CREATE INDEX ON :Label(prop) is accepted. The key indexes are kept
//   alongside the constraints because they drive edge-creation lookups (see
//   edge-ai-kg/schema/edge_ai_kg.cypher); it is not established that an ASSERT
//   constraint creates a backing index on this engine. Drop them if it does.
//
//   A property cannot be unwritten -- REMOVE reports success and changes
//   nothing. Always load into a FRESH engine, never over an existing graph.
//
//   Filters go in WHERE, never in an inline {...} map on a bare single-node
//   MATCH; the map is silently ignored and the query returns a plausible wrong
//   answer. Inside a relationship pattern the same map filters correctly.
//
//   A MATCH cannot directly follow a WHERE -- put a WITH between them.
//
//   Variable-length paths work: -[:DERIVED_FROM*1..5]-> is fine, and is what
//   the provenance and blast-radius questions rely on.
//
//   NOT yet verified: OPTIONAL MATCH and round(). Test both before any query
//   depends on them -- round() appears in every gap-percentage query.
// ---------------------------------------------------------------------------


// === KEYS ==================================================================
// One per label, ASSERT form. Grouped so the whole key surface of the graph
// reads in one place. Declares intent; does not enforce -- see engine notes.

CREATE CONSTRAINT ON (n:Method)        ASSERT n.id   IS UNIQUE;
CREATE CONSTRAINT ON (n:Run)           ASSERT n.id   IS UNIQUE;
CREATE CONSTRAINT ON (n:Claim)         ASSERT n.id   IS UNIQUE;
CREATE CONSTRAINT ON (n:Dataset)       ASSERT n.id   IS UNIQUE;
CREATE CONSTRAINT ON (n:Source)        ASSERT n.id   IS UNIQUE;
CREATE CONSTRAINT ON (n:Channel)       ASSERT n.name IS UNIQUE;
CREATE CONSTRAINT ON (n:Product)       ASSERT n.sku  IS UNIQUE;
CREATE CONSTRAINT ON (n:Segment)       ASSERT n.name IS UNIQUE;
CREATE CONSTRAINT ON (n:Period)        ASSERT n.id   IS UNIQUE;
CREATE CONSTRAINT ON (n:PLLine)        ASSERT n.id   IS UNIQUE;
CREATE CONSTRAINT ON (n:Spend)         ASSERT n.id   IS UNIQUE;
CREATE CONSTRAINT ON (n:Decision)      ASSERT n.id   IS UNIQUE;
CREATE CONSTRAINT ON (n:GeoTest)       ASSERT n.id   IS UNIQUE;
CREATE CONSTRAINT ON (n:Study)         ASSERT n.id   IS UNIQUE;
CREATE CONSTRAINT ON (n:PlanningCycle) ASSERT n.id   IS UNIQUE;

// Key lookups -- these drive edge-creation. See engine notes.
CREATE INDEX ON :Method(id);
CREATE INDEX ON :Run(id);
CREATE INDEX ON :Claim(id);
CREATE INDEX ON :Dataset(id);
CREATE INDEX ON :Source(id);
CREATE INDEX ON :Channel(name);
CREATE INDEX ON :Product(sku);
CREATE INDEX ON :Segment(name);
CREATE INDEX ON :Period(id);
CREATE INDEX ON :PLLine(id);
CREATE INDEX ON :Spend(id);
CREATE INDEX ON :Decision(id);
CREATE INDEX ON :GeoTest(id);
CREATE INDEX ON :Study(id);
CREATE INDEX ON :PlanningCycle(id);


// === TIER 1 -- the measurement machinery ===================================

// Method  id = "<kind>|<name>"
//   Two vendors can both run an MMM; kind alone is not identity.
//   kind:     mmm | geo | incrementality | platform | multiplier
//             `geo` is explicit because Geospatial Analysis is one of the six
//             named products in the programme this models. Folding it into
//             incrementality would model the programme wrong.
//   observes: clicks | modelled | experimental
//             What the method can structurally see. A click-based method
//             cannot produce a claim about an upper-funnel channel -- it is
//             blind to it, which is not the same as reading it as zero. With
//             Channel.funnel_stage this makes the finding an ABSENCE, and a
//             dashboard cannot show you what it never collected.
CREATE INDEX ON :Method(kind);
CREATE INDEX ON :Method(observes);

// Run  id = "<method id>|<executed_on>|<seq>"
//   The same method runs repeatedly; a run is a method at a time. Collapsing
//   Method and Run loses which version of the answer was believed on the day
//   the money moved -- which is the audit trail, and the product.
//   observed_from, observed_to -- see tier 5.
CREATE INDEX ON :Run(executed_on);

// Claim  id = sha1(run + about + metric + period)
//   One method's answer, about one thing, for one period. Nothing else makes
//   it unique. A claim is never a fact: it is stored with its circumstances and
//   is never promoted to a truth.
//   metric:      contribution | incremental_revenue | cac | roas
//   value:       the number
//   granularity: "channel" | "channel+product" | "channel+segment"
//   confidence:  as the method reported it, if it did
//
//   granularity carries the demo's best moment. The same method produces claims
//   at more than one level, and the aggregate read disagreeing with the parts
//   is the finding -- a channel dead across the catalogue and alive on two
//   products. Without this property that question cannot be asked.
CREATE INDEX ON :Claim(metric);
CREATE INDEX ON :Claim(granularity);


// === TIER 2 -- evidence ====================================================

// Dataset  id = "<source>|<name>|<window>"
//   The same extract re-pulled for a different window is a different dataset.
//   refreshed_on drives every freshness question: a dataset that stopped
//   refreshing does not announce itself, it quietly keeps feeding numbers.
CREATE INDEX ON :Dataset(refreshed_on);

// Source  id = the system's own identifier
//   A real system of record -- platform API, CRM, POS, panel, warehouse.


// === TIER 3 -- what a claim is about =======================================

// Channel  key = name
//   The brand's own channel taxonomy, not ours.
//   funnel_stage: upper | lower
//     Paired with Method.observes, this answers "which upper-funnel channels do
//     our click-based methods never see?" The answer is a hole in the graph.
CREATE INDEX ON :Channel(funnel_stage);

// Product  key = sku
//   Needed for the granularity questions. Without products there is nowhere
//   for an aggregate-versus-parts reversal to live.

// Segment  key = name
//   Full-Price / Discount / New / Returning. Channels routinely reverse under
//   a segment split -- weak in aggregate, primary acquisition path for one
//   segment -- and both reads are honest.

// Period  id = "2026-Q3"
//   So claims, spend and decisions align on the same calendar. A node rather
//   than a property: "the same period" becomes a shared traversal instead of a
//   string comparison, and this engine drops some property filters silently.
//   is_peak, season -- see tier 5.


// === TIER 4 -- outcomes ====================================================

// PLLine  id = "<period>|<line name>"
//   A line in the marketing P&L. The trial balance -- what finance carries.
//
//   booked_value  numeric, in `currency`. The amount actually carried in the
//                 marketing P&L for this line, in this period. This is the
//                 figure a CFO points at when saying "prove it", and it is what
//                 the blast-radius query sums to state value at risk when an
//                 upstream dataset turns out to be stale.
//                 Deliberately separate from the claim's value: a line may be
//                 booked conservatively, or booked from a claim that has since
//                 been superseded. The ledger has to be able to show that
//                 difference rather than silently reconcile it away.
//   currency      ISO code, held per line rather than assumed globally.
//   booked_on     when it entered the P&L. Compared against Run.executed_on it
//                 says whether the number existed when it was booked, or was
//                 backfilled afterwards.
//   booked_by     who carried it.

// Spend  id = "<channel>|<period>"
//   What was actually invested. Without it nothing can end in a reallocation,
//   and the three budget questions have no answer. Every beat is supposed to
//   terminate in a decision rather than a finding; Spend is what makes that
//   possible.
//
//   amount        numeric, in `currency`. Media investment in this channel for
//                 this period as committed -- not as modelled, and not as any
//                 method reports it back.
//                 It is the denominator for every efficiency read (CAC, ROAS)
//                 and the pool a reallocation moves within, so "shift 12% from
//                 one channel to another" is only expressible because this
//                 number is in the graph.
//                 Kept separate from Claim.value by design: spend is a fact the
//                 business owns; a claim is one method's opinion about what
//                 that spend did.
//   currency      ISO code, matching PLLine.
//   committed_on  when the budget was committed, which is what makes
//                 PlanningCycle.budget_locked_on meaningful.

// Decision  id
//   What someone actually did, and when. A finding that never became a
//   decision did not matter; a decision whose evidence has since been
//   superseded is a live risk. Both are only queryable if decisions are in the
//   graph rather than in a deck.
//   action, rationale, actor, taken_on, amount_moved, currency.


// === provenance -- every node stamped real | synthetic ======================
CREATE INDEX ON :Claim(provenance);
CREATE INDEX ON :Run(provenance);
CREATE INDEX ON :Dataset(provenance);
CREATE INDEX ON :Method(provenance);


// ===========================================================================
// === TIER 5 -- ADDED FOR THE SEASONAL DTC PITCH ============================
// ===========================================================================
//
// Everything above is the general ledger and matches the schema brief.
// Everything below exists because the demo has to be usable in one specific
// room: a seasonal DTC brand expanding from a gifting peak into year-round
// demand, whose programme used geospatial analysis.
//
// Four additions, each tied to something the pitch cannot do without. If the
// pitch changes, cut this tier -- nothing above depends on it.
//
//   1. Season on Period          the brand's actual strategic question
//   2. GeoTest                   the design behind a geo read, without which a
//                                null cannot be told from a zero
//   3. Run observation window    the seasonal extrapolation trap
//   4. Study + PlanningCycle     the graph mirrors the programme being sold,
//                                not just the data it produces
//
// CUT FOR v1: :Market. Geography beneath every claim cannot be generated in the
// time available. GeoTest survives without it -- see below.
// ---------------------------------------------------------------------------


// --- 1. Season -------------------------------------------------------------
//
// Additional properties on :Period (no new label).
//   is_peak  true | false      -- is this a demand peak for the brand
//   season   "gifting" | "off_peak" | "shoulder"
//
// A brand whose year is 80-90% one quarter is the case where methods disagree
// most violently, and disagree for a reason nobody can see. A model fitted
// across a year dominated by peak behaviour reads an off-peak channel through
// peak-shaped coefficients. A test run in a quiet month reads the same channel
// on its own terms. Both are honest; they are answering different questions.
//
// Without season on Period that difference is invisible, and the demo has
// nothing to say to a brand whose whole strategy is off-peak growth.
CREATE INDEX ON :Period(season);
CREATE INDEX ON :Period(is_peak);


// --- 2. Test design ---------------------------------------------------------

// GeoTest  id = "<channel>|<started_on>"
//   design:            matched_market | scaled_holdout | synthetic_control
//   spend_delta_pct:   how hard the treatment was pushed
//   mde:               minimum detectable effect
//   treatment_markets  count of markets in treatment
//   control_markets    count of markets in control
//   matched_on         what the pairs were matched on, e.g.
//                      "trailing 52w revenue, category mix"
//
//   With :Market cut for v1, the markets are recorded as counts plus a matching
//   description rather than as nodes. This costs the "which markets" question,
//   which no v1 question asks, and keeps everything the design questions need.
//   Restoring :Market later is purely additive: add the label and the
//   TREATMENT/CONTROL edges, and the counts become derivable rather than stored.
//
//   mde is the property that earns this label. A test underpowered for the
//   effect it was looking for produces a null meaning "we could not see it",
//   not "it is not there". For an off-peak channel with a small true effect
//   that distinction decides whether a brand invests or walks away, and a
//   ledger that stores the lift while discarding the design cannot tell the two
//   apart.
CREATE INDEX ON :GeoTest(design);


// --- 3. What a run actually observed ----------------------------------------
//
// Additional properties on :Run (no new label).
//   observed_from, observed_to  -- the window the run's data covered
//
// A run whose data never covered the period its claim describes is
// extrapolating. Sometimes legitimate, sometimes a silent error, never visible
// today:
//
//   "which booked numbers rest on runs that never observed that period?"
//
// For a brand moving into off-peak this is the whole conversation. Most of
// their history is peak; a model built on it has barely seen the season they
// are about to spend into. No dashboard asks this, because none holds both the
// run's observation window and the claim's period as first-class.
CREATE INDEX ON :Run(observed_from);


// --- 4. The programme, not just its output ---------------------------------

// Study  id = "<question slug>|<commissioned_on>"
//   question, hypothesis, owner, status
//   A run exists because someone asked a question. Storing the question beside
//   the answer is what lets the ledger say "we have answered this already"
//   instead of re-running it -- the difference between a measurement programme
//   and a series of measurement projects.
CREATE INDEX ON :Study(status);

// PlanningCycle  id = "<fy>|<cycle name>"
//   board_date, budget_locked_on
//   The calendar the business actually decides on. A read that lands after
//   budget lock had no chance to influence anything, however good it was. For a
//   seasonal brand the lock date is the entire game: miss it and the answer
//   waits a full year for another peak.


// --- Relationship shapes (documentation only) ------------------------------
//
// core
// (:Method)-[:EXECUTED_AS]->(:Run)
// (:Run)-[:PRODUCED]->(:Claim)
// (:Run)-[:CONSUMED]->(:Dataset)
// (:Dataset)-[:DERIVED_FROM]->(:Dataset)     -- chains 3-4 deep, see note below
// (:Dataset)-[:EXTRACTED_FROM]->(:Source)
// (:Claim)-[:ABOUT]->(:Channel)
// (:Claim)-[:ABOUT]->(:Product)              -- when granularity includes it
// (:Claim)-[:ABOUT]->(:Segment)              -- when granularity includes it
// (:Claim)-[:FOR]->(:Period)
// (:Claim)-[:SUPERSEDES]->(:Claim)           -- a later read replacing an earlier
// (:PLLine)-[:BOOKED_FROM]->(:Claim)
// (:PLLine)-[:FOR]->(:Period)
// (:Decision)-[:CITED]->(:Claim)
// (:Decision)-[:ABOUT]->(:Channel)
// (:Spend)-[:ON]->(:Channel)
// (:Spend)-[:FOR]->(:Period)
//
// tier 5
// (:Run)-[:EXECUTED_TEST]->(:GeoTest)
// (:Study)-[:COMMISSIONED]->(:Run)
// (:Study)-[:DUE_FOR]->(:PlanningCycle)
// (:Period)-[:IN_CYCLE]->(:PlanningCycle)
// (:Decision)-[:FOR_CYCLE]->(:PlanningCycle)
//
// DERIVED_FROM must chain several levels deep. That is the whole point of the
// provenance and blast-radius questions: the depth is not known when the query
// is written. If every dataset points straight at a source the traversal
// collapses to one hop and proves nothing.
//
// Independence is derived, not declared. Two methods that share an upstream
// dataset are not independent, and agreement between them means the extract is
// consistent rather than that the number is right. This is read off
// Run -> Dataset -[:DERIVED_FROM*]-> Dataset, never asserted as a property.


// --- Deliberately not modelled ---------------------------------------------
//
// No AGREES_WITH or CONFLICTS_WITH edge. Ever. Agreement between two methods is
// computed at read time from the raw claims. If the loader writes it we are
// asserting agreement rather than computing it, the central claim of the demo
// becomes false, and it is exactly the failure this audience has spent a career
// naming. It will be looked for.
//
// No Customer, Session, Touchpoint or Journey. That is a customer-journey graph
// -- someone else's patent, and most of those questions are GROUP BY anyway. If
// ever needed they sit underneath as a (:Dataset) an attribution run consumed.
// Not v1.
//
// No attribution weights. No first-touch, last-touch or time-decay values
// stored as properties.
//
// The graph never computes a measurement. Claims arrive from methods; the graph
// rolls them up and down granularity, compares them and traces them. It never
// calculates an incrementality, an attribution weight or an MMM coefficient.
// The moment it does, we have built an attribution model.
//
// No node whose only purpose is to make a query shorter.
//
// Orphan claims: none, except the ones planted deliberately for "which of our
// booked numbers have no traceable source at all?" Those are part of the story.
// Accidental orphans are a bug.
