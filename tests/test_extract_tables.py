import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from gamagama.pdf.extract_tables.extraction import (
    _normalize_title,
    _source_from_stem,
)
from gamagama.pdf.extract_tables.dedup import (
    _tables_content_equal,
    _deduplicate_within_book,
    _resolve_conflicts,
)
from gamagama.pdf.extract_tables.index import (
    _assign_filenames,
    _update_cross_index,
)


# ---------------------------------------------------------------------------
# _source_from_stem
# ---------------------------------------------------------------------------


def test_source_from_stem_valid_prefix():
    assert _source_from_stem("gcp-rmu-001-SomeBook-v2") == "gcp-rmu-001"


def test_source_from_stem_no_prefix():
    assert _source_from_stem("some-other-file") == "some-other-file"


def test_source_from_stem_short_stem():
    assert _source_from_stem("gcp-rmu-042") == "gcp-rmu-042"


# ---------------------------------------------------------------------------
# _normalize_title
# ---------------------------------------------------------------------------


def test_normalize_title_punctuation():
    assert _normalize_title("Table 2-2a: Race Stat Bonuses!") == "table 2 2a race stat bonuses"


def test_normalize_title_case():
    assert _normalize_title("ATTACK TABLE") == "attack table"


def test_normalize_title_whitespace():
    assert _normalize_title("  Combat   Maneuver  ") == "combat maneuver"


def test_normalize_title_mixed():
    assert _normalize_title("Table 5.3b: Spell (RR) Results") == "table 5 3b spell rr results"


# ---------------------------------------------------------------------------
# _tables_content_equal
# ---------------------------------------------------------------------------


def test_tables_content_equal_identical():
    rows = [["a", "b"], ["c", "d"]]
    headers = ["Col1", "Col2"]
    assert _tables_content_equal(rows, headers, rows, headers)


def test_tables_content_equal_different_shape():
    assert not _tables_content_equal(
        [["a", "b"]], ["Col1", "Col2"],
        [["a", "b"], ["c", "d"]], ["Col1", "Col2"],
    )


def test_tables_content_equal_different_cell():
    assert not _tables_content_equal(
        [["a", "b"]], ["Col1", "Col2"],
        [["a", "X"]], ["Col1", "Col2"],
    )


def test_tables_content_equal_normalized_whitespace():
    rows1 = [["  hello  ", "world"]]
    rows2 = [["hello", "world"]]
    assert _tables_content_equal(rows1, None, rows2, None)


def test_tables_content_equal_both_no_headers():
    rows = [["x"]]
    assert _tables_content_equal(rows, None, rows, None)


def test_tables_content_equal_header_mismatch():
    rows = [["a"]]
    assert not _tables_content_equal(rows, ["Col1"], rows, ["Col2"])


def test_tables_content_equal_one_null_header():
    rows = [["a"]]
    assert not _tables_content_equal(rows, ["Col1"], rows, None)


# ---------------------------------------------------------------------------
# _deduplicate_within_book
# ---------------------------------------------------------------------------


def _make_table(title, rows, col_headers=None, page=1):
    return {
        "source": "gcp-rmu-001",
        "page": page,
        "heading": "Section",
        "title": title,
        "col_headers": col_headers,
        "row_headers": None,
        "rows": rows,
    }


def test_deduplicate_identical():
    """Two tables with same title and same content → one output, no conflict."""
    t1 = _make_table("Table A", [["a", "b"]], ["Col1", "Col2"], page=10)
    t2 = _make_table("Table A", [["a", "b"]], ["Col1", "Col2"], page=20)
    unique, conflicts, dupe_count = _deduplicate_within_book([t1, t2])
    assert len(unique) == 1
    assert len(conflicts) == 0
    assert dupe_count == 1


def test_deduplicate_conflict():
    """Two tables with same title but different content → conflict list."""
    t1 = _make_table("Table A", [["a", "b"]], ["Col1", "Col2"], page=10)
    t2 = _make_table("Table A", [["x", "y"]], ["Col1", "Col2"], page=20)
    unique, conflicts, dupe_count = _deduplicate_within_book([t1, t2])
    assert len(unique) == 0
    assert len(conflicts) == 1
    assert conflicts[0]["norm_title"] == _normalize_title("Table A")
    assert len(conflicts[0]["versions"]) == 2
    assert dupe_count == 0


def test_deduplicate_different_titles():
    """Two tables with different titles → both in output."""
    t1 = _make_table("Table A", [["a"]], page=10)
    t2 = _make_table("Table B", [["b"]], page=20)
    unique, conflicts, dupe_count = _deduplicate_within_book([t1, t2])
    assert len(unique) == 2
    assert len(conflicts) == 0
    assert dupe_count == 0


def test_deduplicate_three_identical():
    """Three tables, same title and content → one output, two dupes."""
    t1 = _make_table("Table A", [["a"]], page=5)
    t2 = _make_table("Table A", [["a"]], page=10)
    t3 = _make_table("Table A", [["a"]], page=15)
    unique, conflicts, dupe_count = _deduplicate_within_book([t1, t2, t3])
    assert len(unique) == 1
    assert dupe_count == 2


# ---------------------------------------------------------------------------
# _assign_filenames
# ---------------------------------------------------------------------------


def test_assign_filenames_same_page():
    t1 = _make_table("A", [], page=1)
    t2 = _make_table("B", [], page=1)
    _assign_filenames([t1, t2])
    assert t1["filename"] == "table-p001-01.json"
    assert t2["filename"] == "table-p001-02.json"


def test_assign_filenames_different_pages():
    t1 = _make_table("A", [], page=1)
    t2 = _make_table("B", [], page=2)
    _assign_filenames([t1, t2])
    assert t1["filename"] == "table-p001-01.json"
    assert t2["filename"] == "table-p002-01.json"


def test_assign_filenames_sorts_by_page():
    t1 = _make_table("A", [], page=5)
    t2 = _make_table("B", [], page=2)
    tables = [t1, t2]
    _assign_filenames(tables)
    # After sort, t2 (page 2) comes first
    assert tables[0]["page"] == 2
    assert tables[0]["filename"] == "table-p002-01.json"
    assert tables[1]["filename"] == "table-p005-01.json"


# ---------------------------------------------------------------------------
# _update_cross_index
# ---------------------------------------------------------------------------


def _table_with_filename(title, page, source, filename):
    return {
        "source": source,
        "page": page,
        "heading": "Section",
        "title": title,
        "col_headers": None,
        "row_headers": None,
        "rows": [["x"]],
        "filename": filename,
    }


def test_update_cross_index_create(tmp_path):
    """No existing file → creates index with one entry."""
    table = _table_with_filename("Table A", 10, "gcp-rmu-001", "table-p010-01.json")
    _update_cross_index(tmp_path, "gcp-rmu-001", [table])

    index_path = tmp_path / "index.json"
    assert index_path.exists()
    data = json.loads(index_path.read_text())
    assert len(data["tables"]) == 1
    entry = data["tables"][0]
    assert entry["normalized_title"] == _normalize_title("Table A")
    assert entry["canonical"]["source"] == "gcp-rmu-001"
    assert len(entry["versions"]) == 1
    assert entry["versions"][0]["page"] == 10


def test_update_cross_index_add_book(tmp_path):
    """Existing index with book 001 → adding book 002 sets canonical to 002."""
    t1 = _table_with_filename("Table A", 10, "gcp-rmu-001", "table-p010-01.json")
    _update_cross_index(tmp_path, "gcp-rmu-001", [t1])

    t2 = _table_with_filename("Table A", 15, "gcp-rmu-002", "table-p015-01.json")
    _update_cross_index(tmp_path, "gcp-rmu-002", [t2])

    data = json.loads((tmp_path / "index.json").read_text())
    assert len(data["tables"]) == 1
    entry = data["tables"][0]
    assert len(entry["versions"]) == 2
    # Canonical should be highest: gcp-rmu-002
    assert entry["canonical"]["source"] == "gcp-rmu-002"


def test_update_cross_index_replace(tmp_path):
    """Re-running for same source replaces its entries, keeps other books."""
    t1 = _table_with_filename("Table A", 10, "gcp-rmu-001", "table-p010-01.json")
    t2 = _table_with_filename("Table B", 20, "gcp-rmu-002", "table-p020-01.json")
    _update_cross_index(tmp_path, "gcp-rmu-001", [t1])
    _update_cross_index(tmp_path, "gcp-rmu-002", [t2])

    # Re-run gcp-rmu-001 with a different table
    t1_new = _table_with_filename("Table C", 30, "gcp-rmu-001", "table-p030-01.json")
    _update_cross_index(tmp_path, "gcp-rmu-001", [t1_new])

    data = json.loads((tmp_path / "index.json").read_text())
    titles = {e["normalized_title"] for e in data["tables"]}
    assert _normalize_title("Table A") not in titles  # removed
    assert _normalize_title("Table B") in titles      # kept from book 002
    assert _normalize_title("Table C") in titles      # added from re-run


# ---------------------------------------------------------------------------
# _resolve_conflicts
# ---------------------------------------------------------------------------


def test_resolve_conflicts_choice1():
    """Mock input '1' → returns first version."""
    t1 = _make_table("Table A", [["a"]], page=5)
    t2 = _make_table("Table A", [["b"]], page=10)
    conflict = {"norm_title": "table a", "versions": [t1, t2]}
    with patch("builtins.input", return_value="1"):
        result = _resolve_conflicts([conflict])
    assert len(result) == 1
    assert result[0]["page"] == 5


def test_resolve_conflicts_both():
    """Mock input 'both' → returns both versions."""
    t1 = _make_table("Table A", [["a"]], page=5)
    t2 = _make_table("Table A", [["b"]], page=10)
    conflict = {"norm_title": "table a", "versions": [t1, t2]}
    with patch("builtins.input", return_value="both"):
        result = _resolve_conflicts([conflict])
    assert len(result) == 2


def test_resolve_conflicts_skip():
    """Mock input 'skip' → returns empty list."""
    t1 = _make_table("Table A", [["a"]], page=5)
    t2 = _make_table("Table A", [["b"]], page=10)
    conflict = {"norm_title": "table a", "versions": [t1, t2]}
    with patch("builtins.input", return_value="skip"):
        result = _resolve_conflicts([conflict])
    assert len(result) == 0


# ---------------------------------------------------------------------------
# --force flag in CLI
# ---------------------------------------------------------------------------


def test_extract_tables_subcommand_help():
    result = subprocess.run(
        [sys.executable, "-m", "gamagama.pdf", "extract-tables", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "--force" in result.stdout


# ---------------------------------------------------------------------------
# Integration test (slow — requires Core Law docling JSON)
# ---------------------------------------------------------------------------

CORE_LAW_JSON = Path(
    "/home/dwhorton/git/gg/gamagama-rmu/rulebooks/core-law/"
    "gcp-rmu-001-RMUCoreLaw-online-20230312.json"
)


@pytest.mark.slow
def test_integration_core_law(tmp_path):
    """Extract tables from Core Law JSON and verify output structure."""
    if not CORE_LAW_JSON.exists():
        pytest.skip("Core Law JSON not available")

    from gamagama.pdf.extract_tables import handle_extract_tables

    class Args:
        input = str(CORE_LAW_JSON)
        output_dir = str(tmp_path)
        force = False

    handle_extract_tables(Args())

    book_dir = tmp_path / "gcp-rmu-001"
    assert book_dir.is_dir()

    # Per-book index exists and is valid JSON
    book_index_path = book_dir / "index.json"
    assert book_index_path.exists()
    book_index = json.loads(book_index_path.read_text())
    assert "source" in book_index
    assert book_index["source"] == "gcp-rmu-001"
    assert "tables" in book_index
    assert len(book_index["tables"]) > 0

    # Cross-book index exists
    cross_index_path = tmp_path / "index.json"
    assert cross_index_path.exists()
    cross_index = json.loads(cross_index_path.read_text())
    assert "tables" in cross_index
    assert len(cross_index["tables"]) > 0

    # Each entry in cross_index has required fields
    for entry in cross_index["tables"]:
        assert "normalized_title" in entry
        assert "canonical" in entry
        assert "versions" in entry
        assert "source" in entry["canonical"]
        assert "file" in entry["canonical"]

    # Check a few individual table files
    table_files = list(book_dir.glob("table-p*.json"))
    assert len(table_files) > 100  # Core Law has ~300+ tables

    first_file = sorted(table_files)[0]
    table_data = json.loads(first_file.read_text())
    assert "source" in table_data
    assert "page" in table_data
    assert "title" in table_data
    assert "heading" in table_data
    assert "col_headers" in table_data
    assert "row_headers" in table_data
    assert "rows" in table_data

    # Cross-book index entry files reference existing files
    for entry in cross_index["tables"][:10]:
        file_path = tmp_path / entry["canonical"]["file"]
        assert file_path.exists(), f"Missing file: {entry['canonical']['file']}"

    # --force flag: re-running without force should fail
    import io
    import contextlib

    class Args2:
        input = str(CORE_LAW_JSON)
        output_dir = str(tmp_path)
        force = False

    with pytest.raises(SystemExit):
        handle_extract_tables(Args2())

    # --force flag: re-running with force should succeed
    class Args3:
        input = str(CORE_LAW_JSON)
        output_dir = str(tmp_path)
        force = True

    handle_extract_tables(Args3())
    assert book_dir.is_dir()
