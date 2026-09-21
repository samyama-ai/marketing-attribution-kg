"""The front page, held to the record `etl.probe_readme` wrote.

Every figure the README states about the graph is asserted here against
`docs/sources/readme-measured.json`. The record is a committed run, so **these
tests need no engine** — they read a file and the page.

The failure they exist to catch already happened once: the page carried
**78,758 edges** while a run read back **78,752**, and nothing noticed, because
the README was the only set of figures in this repo with no record behind it.

A test that finds a number *somewhere* on the page is worth very little — the
totals appear three times, and a stale one anywhere is the bug. So each
assertion below names the sentence it is checking and anchors to it. Matching
every `N nodes` on the page instead would be worse than useless: the page also
discusses a 115-node toy graph, and a loose match would call correct prose a
failure the moment that paragraph reflowed.

The page and the record are read lazily rather than at import. Reading them at
module level meant a missing or malformed record raised during collection, so
the test that exists to report exactly that never ran.
"""

from __future__ import annotations

import difflib
import functools
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
RECORD_PATH = ROOT / "docs" / "sources" / "readme-measured.json"


@functools.lru_cache(maxsize=1)
def page() -> str:
    return README.read_text(encoding="utf-8")


@functools.lru_cache(maxsize=1)
def record() -> dict:
    return json.loads(RECORD_PATH.read_text(encoding="utf-8"))


# The three sentences that state the graph totals. Each is anchored to its own
# shape so a reflow cannot move one out of range, and so a sentence going
# missing fails loudly rather than silently reducing what is checked.
TOTALS_SENTENCES = {
    "the headline": r"^\*\*([\d,]+) nodes\. ([\d,]+) edges\.\*\*",
    "the status block": r"\*\*([\d,]+) nodes / ([\d,]+) edges, all \d+",
    "the Measured table": r"^\|\s*([\d,]+) nodes / ([\d,]+) edges\s*\|",
    # The Status table states both totals in one cell, in its own shape.
    "the Status table": r"\*\*([\d,]+) nodes, ([\d,]+) edges\*\* in ",
}

#: Two sections open by restating one total each, in a shape none of the
#: sentences above matches. A re-record that moves the totals would leave these
#: stale in silence — which is the failure this file's docstring says already
#: happened once, at 78,758 against 78,752.
SINGLE_TOTAL_SENTENCES = {
    "the What is loaded heading": (r"^\*\*([\d,]+) nodes across ([\d,]+) "
                                   r"labels\.\*\*", "nodes", "labels"),
    "the edge-table heading": (r"^\*\*([\d,]+) edges across ([\d,]+) "
                               r"types\.\*\*", "edges", "edge_types"),
}


def test_the_record_behind_the_front_page_exists():
    """Named so a rename fails one test rather than erroring the whole file."""
    assert RECORD_PATH.exists(), (
        f"{RECORD_PATH.relative_to(ROOT)} is missing; "
        f"`python -m etl.probe_readme --url ... --record` writes it")


def test_every_stated_total_is_the_measured_one():
    """The headline, the status block and the Measured table each state both
    totals. All three are checked, because a stale figure in any one of them is
    the bug this file exists for.
    """
    nodes = f"{record()['nodes']:,}"
    edges = f"{record()['edges']:,}"
    for where, pattern in TOTALS_SENTENCES.items():
        found = re.search(pattern, page(), re.MULTILINE)
        assert found, f"{where} no longer states the graph totals"
        assert found.group(1) == nodes, (
            f"{where} says {found.group(1)} nodes; the engine holds {nodes}")
        assert found.group(2) == edges, (
            f"{where} says {found.group(2)} edges; the engine holds {edges}")


def test_every_section_heading_states_the_measured_total():
    """`20,102 nodes across 16 labels.` and `78,752 edges across 16 types.` —
    each states a total and a count, and neither was matched by any anchor.

    The typed `16` is pinned here too: the page spells sixteen in prose and
    writes it as a digit in these two headings, and only the prose was checked.
    """
    for where, (pattern, total_key, count_key) in SINGLE_TOTAL_SENTENCES.items():
        found = re.search(pattern, page(), re.MULTILINE)
        assert found, f"{where} no longer states its total"
        assert found.group(1) == f"{record()[total_key]:,}", (
            f"{where} says {found.group(1)} {total_key}; the engine holds "
            f"{record()[total_key]:,}")
        assert found.group(2) == str(record()[count_key]), (
            f"{where} says {found.group(2)} {count_key}; the graph holds "
            f"{record()[count_key]}")


def test_the_page_states_the_label_and_edge_type_counts_it_measured():
    """Prose, not a table — `Fifteen labels, sixteen edge types` was wrong by
    one from the day it was written. Spelled numbers, so this reads the words.

    The map covers the counts this graph plausibly holds. Outside it the
    assertion compares prose against a digit and fails with a message implying
    the page is wrong, so extend the map rather than trusting that failure.
    """
    words = {15: "fifteen", 16: "sixteen", 17: "seventeen", 18: "eighteen"}
    labels = words.get(record()["labels"], str(record()["labels"]))
    edges = words.get(record()["edge_types"], str(record()["edge_types"]))
    sentence = re.search(r"(\w+) labels, (\w+) edge types", page())
    assert sentence, "the page no longer states a label / edge-type count"
    assert sentence.group(1).lower() == labels, (
        f"the page says {sentence.group(1)} labels; the graph holds "
        f"{record()['labels']}")
    assert sentence.group(2).lower() == edges, (
        f"the page says {sentence.group(2)} edge types; the graph holds "
        f"{record()['edge_types']}")


def test_the_hero_query_on_the_page_is_the_one_that_was_run():
    """Character for character. A paraphrase would let the page and the record
    agree about a query the page does not actually show.
    """
    if record()["hero_query"] in page():
        return
    # Exact comparison is the point — a normalising compare would let the page
    # show a query that is not the one that ran. But on a seventeen-line query
    # "not in page" names no divergence point, so the diff is built here.
    block = re.search(r"```cypher\n(.*?)```", page(), re.DOTALL)
    shown = block.group(1) if block else ""
    diff = "\n".join(difflib.unified_diff(
        record()["hero_query"].splitlines(), shown.splitlines(),
        fromfile="the query that was run", tofile="the query on the page",
        lineterm=""))
    raise AssertionError(
        "the Cypher on the front page is not the query the record was measured "
        f"from; re-record, or put the query back:\n{diff}")


def test_the_hero_table_holds_the_values_the_query_returned():
    """The five figures under the query, each asserted against the row the
    engine answered — not against each other.
    """
    assert len(record()["hero_rows"]) == 1, (
        f"the front page shows one row; the query returned "
        f"{len(record()['hero_rows'])}")
    period, mmm_kind, mmm, geo_kind, geo, gap, gap_pct = record()["hero_rows"][0]

    row = re.search(rf"\|\s*{re.escape(period)}\s*\|(.+?)\|\s*$", page(),
                    re.MULTILINE)
    assert row, "the results table under the hero query is gone"
    cells = [cell.strip() for cell in row.group(1).split("|")]

    assert cells[0] == mmm_kind and cells[2] == geo_kind
    assert cells[1] == f"{mmm:,}", f"table says {cells[1]}, engine said {mmm:,}"
    assert cells[3] == f"{geo:,}", f"table says {cells[3]}, engine said {geo:,}"
    assert cells[4] == f"{gap:,}", f"table says {cells[4]}, engine said {gap:,}"
    assert cells[5] == str(int(gap_pct)), (
        f"table says {cells[5]}% gap, engine said {int(gap_pct)}%")


#: The Measured table quotes seven per-label counts in one row. Each can drift
#: while the totals stay right — which is the exact failure this file exists to
#: catch — so all seven are checked rather than the one that was easiest.
QUOTED_COUNTS = {
    "quarters": "Period",
    "SKUs": "Product",
    "DMAs": "Market",
    "claims": "Claim",
    "methods": "Method",
    "channels": "Channel",
    "segments": "Segment",
}


def test_every_per_label_count_the_page_quotes_matches_the_breakdown():
    """`8 quarters · 65 SKUs · 210 DMAs · 19,716 claims | 5 methods, 8 channels,
    2 segments` — seven figures, each a per-label count.
    """
    for phrase, label in QUOTED_COUNTS.items():
        assert label in record()["by_label"], (
            f"the record has no `{label}` count for the page's {phrase}")
        stated = f"{record()['by_label'][label]:,} {phrase}"
        assert stated in page(), (
            f"the page does not state `{stated}`; the graph holds "
            f"{record()['by_label'][label]:,} {label} nodes")


def test_the_record_is_internally_consistent():
    """The probe enforces this at write time, but the record is a committed
    JSON file anyone can hand-edit, and after that nothing re-checks it.
    """
    by_label = sum(record()["by_label"].values())
    assert by_label == record()["nodes"], (
        f"the per-label counts sum to {by_label:,}, the record states "
        f"{record()['nodes']:,} nodes")
    by_type = sum(record()["by_edge_type"].values())
    assert by_type == record()["edges"], (
        f"the per-type counts sum to {by_type:,}, the record states "
        f"{record()['edges']:,} edges")
    assert len(record()["by_label"]) == record()["labels"]
    assert len(record()["by_edge_type"]) == record()["edge_types"]


def test_the_record_was_measured_from_a_committed_tree():
    """A record written from a dirty tree names a commit that cannot reproduce
    it. Disclosed is better than hidden, but un-mergeable is better than both.
    """
    code = record().get("code") or {}
    assert code.get("commit"), (
        "the record does not say which commit produced it; re-run "
        "`python -m etl.probe_readme --url ... --record`")
    assert code.get("dirty") is False, (
        f"the record was measured from a dirty tree at {code.get('commit')}, "
        f"so checking out that commit will not reproduce it — commit the tree "
        f"and re-record before merging")


def test_the_table_header_names_the_columns_the_query_returned():
    """`hero_columns` is recorded; the page prints its own header. Two lines
    stops those disagreeing.
    """
    header = re.search(r"^\|\s*p\.id\s*\|(.+?)\|\s*$", page(), re.MULTILINE)
    assert header, "the header of the results table is gone"
    printed = ["p.id"] + [cell.strip() for cell in header.group(1).split("|")]
    assert printed == record()["hero_columns"], (
        f"the table header reads {printed}; the query returned "
        f"{record()['hero_columns']}")


def rows_of(table_heading: str) -> list[list[str]]:
    """The markdown rows under a `| Label | Count | |`-style header.

    Anchored on the header line rather than on a section heading: two tables sit
    under `## What is loaded`, and a section-anchored reader would return the
    first one twice.
    """
    lines = page().splitlines()
    start = next((i for i, line in enumerate(lines)
                  if line.startswith(table_heading)), None)
    if start is None:
        # Returning empty rather than raising: every caller already asserts the
        # table is non-empty with a message naming which one is gone, and a
        # bare StopIteration from a generator makes those messages unreachable.
        return []
    rows = []
    for line in lines[start + 2:]:
        if not line.startswith("|"):
            break
        rows.append([cell.strip() for cell in line.strip("|").split("|")])
    return rows


def test_the_label_table_holds_the_measured_count_for_every_label():
    """All sixteen rows, against the record — not a spot check on the biggest.
    """
    table = {row[0].strip("`"): row[1] for row in rows_of("| Label | Count |")}
    assert table, "the label table is gone from the page"
    assert set(table) == set(record()["by_label"]), (
        f"the table lists {sorted(set(table) ^ set(record()['by_label']))} "
        f"differently from the graph")
    for label, stated in table.items():
        assert stated == f"{record()['by_label'][label]:,}", (
            f"`{label}`: the table says {stated}, the engine holds "
            f"{record()['by_label'][label]:,}")


def test_the_edge_table_holds_the_measured_count_for_every_type():
    table = {row[0].strip("`"): row[1] for row in rows_of("| Edge | Count |")}
    assert table, "the edge table is gone from the page"
    assert set(table) == set(record()["by_edge_type"]), (
        f"the table lists {sorted(set(table) ^ set(record()['by_edge_type']))} "
        f"differently from the graph")
    for kind, stated in table.items():
        assert stated == f"{record()['by_edge_type'][kind]:,}", (
            f"`{kind}`: the table says {stated}, the engine holds "
            f"{record()['by_edge_type'][kind]:,}")


def test_the_catalogue_table_lists_every_question_the_repo_ships():
    """The page and `queries/catalogue.py`, not the page and itself.

    Every column, not just the id. The page copies the question text, the
    persona and the category straight out of the catalogue, and all three can
    drift with nothing failing — checking only the id leaves three quarters of
    each row to be diffed by hand at review time.
    """
    from queries import catalogue

    shipped = {question["id"]: question for question in catalogue.QUESTIONS}
    rows = rows_of("| id | Question |")
    assert rows, "the catalogue table is gone from the page"
    listed = {row[0]: row for row in rows}

    assert set(listed) == set(shipped), (
        f"on the page but not in the catalogue: {sorted(set(listed) - set(shipped))}; "
        f"in the catalogue but not on the page: {sorted(set(shipped) - set(listed))}")

    for qid, row in sorted(listed.items()):
        question = shipped[qid]
        for column, (index, field) in {
                "question": (1, "question"),
                "persona": (2, "persona"),
                "category": (3, "category")}.items():
            assert row[index] == question[field], (
                f"{qid} {column}: the page says {row[index]!r}, the catalogue "
                f"says {question[field]!r}")

    categories = len({question["category"] for question in catalogue.QUESTIONS})
    assert f"**{len(shipped)} questions across {categories} categories**" in page(), (
        f"the page does not state that it ships {len(shipped)} questions across "
        f"{categories} categories")


def test_the_structure_table_lists_every_top_level_folder():
    """A reader comparing the table to `ls` should find no surprises. Three
    folders exist as spec-only READMEs and were missing from it.
    """
    listed = set(re.findall(r"\[`(\w+)/`\]", page()))
    on_disk = {entry.name for entry in ROOT.iterdir()
               if entry.is_dir() and not entry.name.startswith((".", "__"))
               and entry.name not in {"data_out", "venv"}}
    assert on_disk <= listed, (
        f"on disk but not in the Structure table: {sorted(on_disk - listed)}")
