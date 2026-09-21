"""The dataset card, held to the same record as the front page.

`DATASET-CARD.md` restates the totals, the full per-label and per-edge-type
breakdowns and the catalogue shape. That is the whole graph quoted a second
time, in a second file — so every figure on it is a figure that can drift, and
the card is the document an outside reader is most likely to trust.

These read the committed record and the catalogue. No engine.
"""

from __future__ import annotations

import functools
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
CARD_PATH = ROOT / "DATASET-CARD.md"
RECORD_PATH = ROOT / "docs" / "sources" / "readme-measured.json"


@functools.lru_cache(maxsize=1)
def card() -> str:
    return CARD_PATH.read_text(encoding="utf-8")


@functools.lru_cache(maxsize=1)
def record() -> dict:
    return json.loads(RECORD_PATH.read_text(encoding="utf-8"))


def test_the_card_exists_and_says_the_data_is_synthetic():
    """The disclosure this card exists for. A reader who takes one thing from
    it should take this.
    """
    assert CARD_PATH.exists(), "DATASET-CARD.md is missing"
    assert "synthetic" in card().lower(), (
        "the card no longer says the data is synthetic — that is the one claim "
        "on it that must never be dropped")
    assert "planted" in card().lower(), (
        "the card no longer says the findings were planted")


def test_the_headline_totals_match_the_record():
    found = re.search(r"\*\*([\d,]+) nodes across (\d+) labels\. "
                      r"([\d,]+) edges across (\d+) types\.\*\*", card())
    assert found, "the card no longer states its totals in the expected shape"
    nodes, labels, edges, types = found.groups()
    assert nodes == f"{record()['nodes']:,}", (
        f"the card says {nodes} nodes; the record holds {record()['nodes']:,}")
    assert edges == f"{record()['edges']:,}", (
        f"the card says {edges} edges; the record holds {record()['edges']:,}")
    assert labels == str(record()["labels"])
    assert types == str(record()["edge_types"])


def rows_under(header: str) -> dict[str, str]:
    """The `| `name` | count |` rows following a header line."""
    lines = card().splitlines()
    start = next((i for i, line in enumerate(lines)
                  if line.startswith(header)), None)
    if start is None:
        return {}
    out = {}
    for line in lines[start + 2:]:
        if not line.startswith("|"):
            break
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        out[cells[0].strip("`")] = cells[1]
    return out


def test_every_label_row_matches_the_record():
    """All sixteen, not a spot check on the biggest."""
    table = rows_under("| label | count |")
    assert table, "the label table is gone from the card"
    assert set(table) == set(record()["by_label"]), (
        f"the card and the record disagree on which labels exist: "
        f"{sorted(set(table) ^ set(record()['by_label']))}")
    for label, stated in table.items():
        assert stated == f"{record()['by_label'][label]:,}", (
            f"`{label}`: the card says {stated}, the engine holds "
            f"{record()['by_label'][label]:,}")


def test_every_edge_type_row_matches_the_record():
    table = rows_under("| edge type | count |")
    assert table, "the edge-type table is gone from the card"
    assert set(table) == set(record()["by_edge_type"]), (
        f"the card and the record disagree on which edge types exist: "
        f"{sorted(set(table) ^ set(record()['by_edge_type']))}")
    for kind, stated in table.items():
        assert stated == f"{record()['by_edge_type'][kind]:,}", (
            f"`{kind}`: the card says {stated}, the engine holds "
            f"{record()['by_edge_type'][kind]:,}")


def test_the_catalogue_shape_matches_the_catalogue():
    """Both the question count and the per-category split, against
    `queries/catalogue.py` rather than against the card itself.
    """
    from queries import catalogue

    questions = catalogue.QUESTIONS
    categories = {}
    for question in questions:
        categories[question["category"]] = categories.get(
            question["category"], 0) + 1

    assert f"**{len(questions)} questions across {len(categories)} categories**" in card(), (
        f"the card does not state {len(questions)} questions across "
        f"{len(categories)} categories")

    table = rows_under("| category | questions |")
    assert table, "the category table is gone from the card"
    assert {name: int(n) for name, n in table.items()} == categories, (
        f"the card's category split is {table}, the catalogue holds {categories}")


def test_the_prose_figures_that_restate_counts_match():
    """The card explains why `Claim` dominates, quoting three counts in prose.
    Prose drifts more quietly than a table.
    """
    for figure in (f"`Claim` is {record()['by_label']['Claim']:,} of "
                   f"{record()['nodes']:,} nodes",
                   f"`ABOUT` at {record()['by_edge_type']['ABOUT']:,}",
                   f"{record()['by_label']['Market']} markets"):
        assert figure in card(), f"the card no longer says `{figure}`"
