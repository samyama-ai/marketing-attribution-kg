"""Talking to Samyama Graph over HTTP.

Small on purpose: one class, one upsert, and the two escaping rules that stop a
loader corrupting a graph quietly. Everything here is a measured behaviour of
`public.ecr.aws/f9f6l5u4/samyama-graph:1.1.0`, not an assumption.

No third-party dependency — urllib only.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

#: Status codes worth trying again. A 4xx is our fault and retrying it just
#: sends the same broken query twice.
RETRIED = (429, 500, 502, 503, 504)


class Refused(RuntimeError):
    """The engine answered, and the answer was a refusal.

    Carries the code because the caller's response differs: a 400 is a query we
    wrote wrongly, a 503 is worth waiting on.
    """

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


class Engine:
    def __init__(self, url: str = "http://localhost:8080",
                 timeout: int = 60, attempts: int = 4) -> None:
        self.url = url.rstrip("/")
        #: Per-request budget and retry count. Defaults suit the loader, which
        #: writes for half a minute at a time and genuinely wants to wait out a
        #: busy engine. Readers should turn both down — see `queries/run.py`.
        self.timeout = timeout
        self.attempts = attempts

    def run(self, query: str, attempts: int | None = None) -> dict:
        attempts = self.attempts if attempts is None else attempts
        body = json.dumps({"query": query}).encode()
        request = urllib.request.Request(
            f"{self.url}/api/query", data=body,
            headers={"Content-Type": "application/json"})
        for attempt in range(attempts):
            try:
                with urllib.request.urlopen(request,
                                        timeout=self.timeout) as response:
                    answer = json.loads(response.read())
            except urllib.error.HTTPError as refused:
                detail = refused.read().decode(errors="replace")[:200]
                if refused.code in RETRIED and attempt < attempts - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise Refused(refused.code,
                              f"{refused.code} on: {query[:90]}\n{detail}")
            except (urllib.error.URLError, TimeoutError, OSError) as gone:
                if attempt < attempts - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise Refused(0, f"{self.url} unreachable: {gone}")
            # A 200 carrying an "error" key is still a failure. Treating it as
            # success is how a loader reports counts for rows it never wrote.
            if isinstance(answer, dict) and answer.get("error"):
                raise Refused(200, f"{answer['error']} on: {query[:90]}")
            return answer
        raise Refused(0, "retries exhausted")

    def scalar(self, query: str):
        """The single value a `RETURN count(x)` produces.

        Guarded, because **a bare aggregate always returns exactly one row on
        this engine, even over an empty graph** — `count()` gives `[[0]]` and
        `max()` gives `[[null]]`. So `records != []` is not an emptiness check
        and never was; read the value.
        """
        records = self.run(query).get("records") or []
        if not records or not records[0]:
            return None
        return records[0][0]


def lit(value) -> str:
    """A Cypher literal.

    Strings are escaped for backslash and both quote characters. This build
    does NOT decode escape sequences consistently across builds — one renders
    `\\t` as a tab, another leaves it — so a string carrying both quote
    characters is refused rather than guessed at.
    """
    if value is None or value == "":
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    text = str(value)
    if '"' in text and "'" in text:
        raise ValueError(f"cannot quote a value holding both quote "
                         f"characters: {text[:60]!r}")
    if '"' in text:
        return "'" + text.replace("\\", "\\\\") + "'"
    return '"' + text.replace("\\", "\\\\") + '"'


def identifier(name: str) -> str:
    """A label or property name, checked rather than escaped.

    There is no way to quote an identifier safely here, so anything that is not
    a plain word is refused. A label built from data is how a loader becomes an
    injection.
    """
    if not name.replace("_", "").isalnum():
        raise ValueError(f"unsafe identifier: {name!r}")
    return name


def upsert(engine: Engine, label: str, key: str, value, props: dict) -> None:
    """MERGE the key, then SET the rest — two statements, deliberately.

    `MERGE (n:L {k: v}) SET n.p = x` does not parse on 1.1.0: the parser takes
    `ON CREATE SET` and `ON MATCH SET` after a MERGE but not a bare SET.
    `ON CREATE SET` alone would be one statement, but it fires only on insert,
    so a re-run after a value changes leaves the old one in place. A separate
    MATCH … SET always refreshes, which is what a re-runnable loader needs.

    **This cannot UNWRITE a property.** It SETs what it is given and never
    REMOVEs, and on this build `REMOVE` reports success and changes nothing.
    So a graph that has already held a value keeps it. Load into a FRESH
    engine; never over an existing one.
    """
    identifier(label)
    identifier(key)
    for name in props:
        identifier(name)

    # Every value is rendered BEFORE anything is sent. Rendering inside the
    # second statement means an unquotable value raises after the MERGE has
    # landed, leaving a node that exists and carries nothing.
    key_literal = lit(value)
    rendered = {name: lit(v) for name, v in props.items() if v not in (None, "")}

    engine.run(f"MERGE (n:{label} {{{key}: {key_literal}}})")
    if rendered:
        sets = ", ".join(f"n.{name} = {v}" for name, v in rendered.items())
        engine.run(f"MATCH (n:{label}) WHERE n.{key} = {key_literal} "
                   f"SET {sets}")


def link(engine: Engine, a_label: str, a_key: str, a_value,
         edge: str, b_label: str, b_key: str, b_value,
         props: dict | None = None) -> None:
    """One edge between two nodes found by key.

    **Both ends are matched with WHERE, never with an inline `{...}` map.** A
    bare single-node `MATCH (n:L {k: v})` silently ignores its property map on
    this build — an aggregate behind it counts the whole label and a projection
    returns nothing, with no error either way. Inside a relationship pattern
    the same map filters correctly, which is exactly why the bug is hard to
    see. Using WHERE everywhere removes the question.
    """
    for name in (a_label, a_key, edge, b_label, b_key):
        identifier(name)
    rendered = {k: lit(v) for k, v in (props or {}).items()
                if v not in (None, "")}
    payload = ""
    if rendered:
        payload = " {" + ", ".join(f"{k}: {v}" for k, v in rendered.items()) + "}"
    engine.run(
        f"MATCH (a:{a_label}) WHERE a.{a_key} = {lit(a_value)} "
        f"WITH a "                       # a MATCH cannot follow a WHERE
        f"MATCH (b:{b_label}) WHERE b.{b_key} = {lit(b_value)} "
        f"MERGE (a)-[:{edge}{payload}]->(b)")


# ---------------------------------------------------------------------------
# Bulk writing
# ---------------------------------------------------------------------------
#: How many nodes to put in one CREATE. Measured on 1.1.0: 200 gives roughly
#: 15,000 nodes/sec against 219/sec for one-per-request — about a 70x gain, and
#: larger batches keep helping until the query string itself becomes the cost.
#:
#: An earlier note here claimed 51,000/sec. That number was measured against a
#: hub-anchored CREATE that wrote nothing (see the note below `create_nodes`),
#: so it timed an empty round trip. The 0.00s should have been the tell.
BATCH = 200


def create_nodes(engine: Engine, label: str, rows: list[dict],
                 batch: int = BATCH) -> int:
    """Create many nodes in one request each batch.

    **`UNWIND` is not supported on this engine** — a parse error alone, and an
    empty result rather than an error inside a longer query — so the usual
    batching idiom is unavailable. Comma-separated CREATE is what works:

        CREATE (n0:L {...}), (n1:L {...}), (n2:L {...})

    CREATE rather than MERGE because the loader refuses to run against a
    non-empty graph, so there is nothing to merge with. That also halves the
    round trips: MERGE-then-SET was two requests per node.
    """
    identifier(label)
    written = 0
    for start in range(0, len(rows), batch):
        chunk = rows[start:start + batch]
        parts = []
        for i, props in enumerate(chunk):
            fields = ", ".join(f"{identifier(k)}: {lit(v)}"
                               for k, v in props.items() if v not in (None, ""))
            parts.append(f"(n{i}:{label} {{{fields}}})")
        engine.run("CREATE " + ", ".join(parts))
        written += len(chunk)
    return written


# A `create_hub_anchored` helper lived here and was deleted, because on this
# engine **a CREATE that introduces a new node writes nothing when it appears
# after a MATCH.** Measured, every form:
#
#     MATCH (r:Run) WHERE ... WITH r CREATE (c:Claim {...})        -> 0 written
#     MATCH (r:Run) WHERE ... CREATE (c:Claim {...})               -> 0 written
#     MATCH (r:Run), (p:Period) WHERE ... CREATE (c:Claim {...})   -> 0 written
#
# It does not error. It returns success and creates nothing, which is how the
# first version of this loader reported 19,716 claims written against a graph
# holding zero — caught only because the loader reads its counts back.
#
# Creating a RELATIONSHIP between two already-matched nodes works fine, which
# is what `create_edges` below does. So the shape is: batch the nodes with a
# bare CREATE, then batch the edges with MATCH ... CREATE. Nodes and their
# edges cannot be written in one statement.

def create_edges(engine: Engine, pairs: list[tuple], edge_type: str,
                 a_label: str, a_key: str, b_label: str, b_key: str,
                 batch: int = 25) -> int:
    """Edges between nodes found by key, batched.

    Slower than the hub-anchored path by two orders of magnitude, because each
    pair needs both endpoints matched and the batch becomes a cartesian
    product. Kept for the edges that do not share a hub — lineage chains,
    supersedes, and anything one-to-one. Batch stays small for that reason.
    """
    for name in (edge_type, a_label, a_key, b_label, b_key):
        identifier(name)
    written = 0
    for start in range(0, len(pairs), batch):
        chunk = pairs[start:start + batch]
        terms, wheres, creates = [], [], []
        for i, (a, b) in enumerate(chunk):
            terms += [f"(a{i}:{a_label})", f"(b{i}:{b_label})"]
            wheres += [f"a{i}.{a_key} = {lit(a)}", f"b{i}.{b_key} = {lit(b)}"]
            creates.append(f"(a{i})-[:{edge_type}]->(b{i})")
        answer = engine.run("MATCH " + ", ".join(terms)
                            + " WHERE " + " AND ".join(wheres)
                            + " CREATE " + ", ".join(creates))
        # **The count comes from the engine, never from len(chunk).** Measured
        # on 1.1.0: a CREATE between matched nodes returns one record per edge
        # it actually made, so `len(records)` IS the number written. Both ways
        # this can go wrong are silent otherwise:
        #
        #   one endpoint missing  -> the whole batch's MATCH yields no rows,
        #                            zero edges are written, no error is raised
        #   a duplicate key value -> that term binds twice and the cartesian
        #                            join writes MORE edges than were asked for
        #
        # Reporting len(chunk) through either is the same "19,716 written
        # against a graph holding zero" bug the note above this function
        # describes, one layer down. So compare, and refuse on a mismatch.
        made = len(answer.get("records") or [])
        if made != len(chunk):
            raise Refused(200, (
                f"{edge_type}: asked for {len(chunk)} edges, engine made "
                f"{made}. " + ("An endpoint did not match — check "
                               f"{a_label}.{a_key} / {b_label}.{b_key} exist."
                               if made < len(chunk) else
                               f"A duplicate {a_key}/{b_key} value multiplied "
                               "the join.")))
        written += made
    return written
