import json
import sys
from io import BytesIO
from unittest.mock import patch, MagicMock

import pytest
from fpdf import FPDF

from gamagama.pdf.convert import (
    parse_page_range,
    drop_redundant_bookmarks,
    _build_title_map,
    restore_bookmark_casing,
    normalize_toc_titles,
    _prepare_heading_source,
    handle_convert,
)


# --- parse_page_range tests ---


def test_parse_page_range_none():
    assert parse_page_range(None) == (1, sys.maxsize)


def test_parse_page_range_single():
    assert parse_page_range("5") == (5, 5)


def test_parse_page_range_range():
    assert parse_page_range("1-50") == (1, 50)


# --- overwrite protection ---


def test_convert_refuses_overwrite_without_force(tmp_path):
    """When output files exist and --force is not set, exit with error."""
    # Create a fake input PDF and existing output file
    fake_pdf = tmp_path / "test.pdf"
    fake_pdf.touch()
    existing_md = tmp_path / "test.md"
    existing_md.write_text("existing content")

    args = MagicMock()
    args.input = str(fake_pdf)
    args.output_dir = str(tmp_path)
    args.force = False
    args.ocr = False
    args.pages = None

    with pytest.raises(SystemExit) as exc_info:
        handle_convert(args)
    assert exc_info.value.code == 1


def test_convert_refuses_overwrite_late_check(tmp_path):
    """When output files appear during conversion, exit with error before writing."""
    fake_pdf = tmp_path / "test.pdf"
    fake_pdf.touch()

    args = MagicMock()
    args.input = str(fake_pdf)
    args.output_dir = str(tmp_path)
    args.force = False
    args.ocr = False
    args.pages = None
    args.heading_strategy = "none"
    args.no_drop_empty_bookmarks = False
    args.no_fuzzy_match = False

    mock_status = MagicMock()
    mock_status.__eq__ = lambda self, other: other.name == "FAILURE"

    # Simulate files appearing after the early check but during conversion
    def fake_convert(*a, **kw):
        (tmp_path / "test.md").write_text("sneaky content")
        (tmp_path / "test.json").write_text("{}")
        result = MagicMock()
        result.status = mock_status
        result.document = MagicMock()
        return result

    fake_docling = {
        "docling.document_converter": MagicMock(),
        "docling.datamodel.base_models": MagicMock(),
        "docling.datamodel.pipeline_options": MagicMock(),
        "docling_core.types.doc.base": MagicMock(),
        "hierarchical": MagicMock(),
        "hierarchical.postprocessor": MagicMock(),
    }
    fake_docling["docling.document_converter"].DocumentConverter.return_value.convert = fake_convert

    with patch.dict("sys.modules", fake_docling):
        with pytest.raises(SystemExit) as exc_info:
            handle_convert(args)
    assert exc_info.value.code == 1


def test_convert_input_not_found(tmp_path):
    """When input file doesn't exist, exit with error."""
    args = MagicMock()
    args.input = str(tmp_path / "nonexistent.pdf")
    args.output_dir = str(tmp_path)
    args.force = False
    args.ocr = False
    args.pages = None

    with pytest.raises(SystemExit) as exc_info:
        handle_convert(args)
    assert exc_info.value.code == 1


# --- real PDF integration test ---


@pytest.fixture
def sample_pdf(tmp_path):
    """Generate a 3-page PDF with headings, paragraphs, and a table."""
    pdf = FPDF()

    # --- Page 1: Title + intro paragraphs ---
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 24)
    pdf.multi_cell(w=0, h=12, text="Sample Rulebook")
    pdf.ln(4)
    pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(
        w=0, h=7,
        text=(
            "Welcome to the Sample Rulebook. This document explains the core "
            "mechanics and equipment used during gameplay sessions."
        ),
    )
    pdf.ln(3)
    pdf.multi_cell(
        w=0, h=7,
        text=(
            "Players should read all chapters before their first session to "
            "understand the rules and character creation process."
        ),
    )

    # --- Page 2: Section header + paragraph + table ---
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.multi_cell(w=0, h=10, text="Chapter 1: Core Rules")
    pdf.ln(3)
    pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(
        w=0, h=7,
        text=(
            "Every character has three primary attributes that determine their "
            "capabilities in the game world."
        ),
    )
    pdf.ln(4)

    # 4x3 table with borders
    pdf.set_font("Helvetica", "B", 11)
    col_widths = [40, 80, 30]
    row_height = 8
    headers = ["Attribute", "Description", "Default"]
    for header, w in zip(headers, col_widths):
        pdf.cell(w=w, h=row_height, text=header, border=1)
    pdf.ln(row_height)

    pdf.set_font("Helvetica", size=11)
    rows = [
        ("Strength", "Physical power and endurance", "10"),
        ("Agility", "Speed and reflexes", "10"),
        ("Intellect", "Mental acuity and knowledge", "10"),
    ]
    for row in rows:
        for cell, w in zip(row, col_widths):
            pdf.cell(w=w, h=row_height, text=cell, border=1)
        pdf.ln(row_height)

    # --- Page 3: Section header + paragraphs ---
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.multi_cell(w=0, h=10, text="Chapter 2: Equipment")
    pdf.ln(3)
    pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(
        w=0, h=7,
        text=(
            "Equipment plays a vital role in survival. Characters begin with "
            "basic gear and acquire better items through exploration."
        ),
    )
    pdf.ln(3)
    pdf.multi_cell(
        w=0, h=7,
        text=(
            "Weapons and armor follow a tiered quality system ranging from "
            "common to legendary, each with increasing bonuses."
        ),
    )

    path = tmp_path / "sample.pdf"
    pdf.output(str(path))
    return path


@pytest.mark.slow
def test_convert_real_pdf(sample_pdf, tmp_path, capsys):
    """Integration test: convert a real multi-page PDF and verify outputs."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    args = MagicMock()
    args.input = str(sample_pdf)
    args.output_dir = str(output_dir)
    args.force = False
    args.ocr = False
    args.pages = None
    args.heading_strategy = "bookmarks"
    args.no_drop_empty_bookmarks = False
    args.no_fuzzy_match = False

    handle_convert(args)

    stem = sample_pdf.stem
    md_path = output_dir / f"{stem}.md"
    json_path = output_dir / f"{stem}.json"

    # Both outputs created
    assert md_path.exists(), "Markdown output not created"
    assert json_path.exists(), "JSON output not created"

    # Markdown contains expected content
    md_content = md_path.read_text()
    assert "Sample Rulebook" in md_content, "Title not found in markdown"
    assert "Chapter 1" in md_content, "Chapter 1 heading not found in markdown"
    assert "Chapter 2" in md_content, "Chapter 2 heading not found in markdown"
    assert "Strength" in md_content, "Table cell 'Strength' not found in markdown"

    # JSON is valid and is a dict
    json_text = json_path.read_text()
    json_data = json.loads(json_text)
    assert isinstance(json_data, dict)

    # Stdout summary mentions page count and table count
    captured = capsys.readouterr()
    assert "3 pages" in captured.out
    assert "1 tables" in captured.out


@pytest.mark.slow
def test_convert_pages_mid_range(sample_pdf, tmp_path, capsys):
    """--pages 2-3 should convert only pages 2-3, excluding page 1 content."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    args = MagicMock()
    args.input = str(sample_pdf)
    args.output_dir = str(output_dir)
    args.force = False
    args.ocr = False
    args.pages = "2-3"
    args.heading_strategy = "none"
    args.no_drop_empty_bookmarks = False
    args.no_fuzzy_match = False

    handle_convert(args)

    stem = sample_pdf.stem
    md_content = (output_dir / f"{stem}.md").read_text()

    # Page 1 content should be absent
    assert "Sample Rulebook" not in md_content, "Page 1 title should not appear"

    # Pages 2–3 content should be present
    assert "Chapter 1" in md_content, "Page 2 heading not found"
    assert "Chapter 2" in md_content, "Page 3 heading not found"

    captured = capsys.readouterr()
    assert "2 pages" in captured.out


@pytest.mark.slow
def test_convert_pages_single_middle(sample_pdf, tmp_path, capsys):
    """--pages 2 should convert only page 2."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    args = MagicMock()
    args.input = str(sample_pdf)
    args.output_dir = str(output_dir)
    args.force = False
    args.ocr = False
    args.pages = "2"
    args.heading_strategy = "none"
    args.no_drop_empty_bookmarks = False
    args.no_fuzzy_match = False

    handle_convert(args)

    stem = sample_pdf.stem
    md_content = (output_dir / f"{stem}.md").read_text()

    assert "Sample Rulebook" not in md_content, "Page 1 title should not appear"
    assert "Chapter 1" in md_content, "Page 2 heading not found"
    assert "Chapter 2" not in md_content, "Page 3 heading should not appear"

    captured = capsys.readouterr()
    assert "1 pages" in captured.out


@pytest.mark.slow
def test_convert_pages_out_of_range(sample_pdf, tmp_path):
    """--pages beyond the document's page count should fail."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    args = MagicMock()
    args.input = str(sample_pdf)
    args.output_dir = str(output_dir)
    args.force = False
    args.ocr = False
    args.pages = "5-10"
    args.heading_strategy = "none"
    args.no_drop_empty_bookmarks = False
    args.no_fuzzy_match = False

    with pytest.raises(SystemExit) as exc_info:
        handle_convert(args)
    assert exc_info.value.code == 1


# --- drop_redundant_bookmarks tests ---


SAMPLE_TOC = [
    # Structural bookmarks (with children)
    [1, "Part I: Core Rules", 1],
    [2, "Chapter 1: Introduction", 2],
    [2, "Chapter 2: Characters", 10],
    [1, "Part II: Advanced Rules", 50],
    [2, "Chapter 3: Combat", 51],
    [1, "Part III: Appendices", 80],
    [2, "Appendix A: Tables", 81],
    # Childless L1 index entries — pages fall within bounded spans
    [1, "Ball, Lightning", 5],
    [1, "Rogue", 12],
    [1, "Sword, Long", 55],
]


def test_drop_redundant_keeps_structural():
    """Structural entries with children are kept."""
    result = drop_redundant_bookmarks(SAMPLE_TOC)
    assert [1, "Part I: Core Rules", 1] in result
    assert [1, "Part II: Advanced Rules", 50] in result
    assert [1, "Part III: Appendices", 80] in result
    assert [2, "Chapter 1: Introduction", 2] in result
    assert [2, "Chapter 2: Characters", 10] in result
    assert [2, "Chapter 3: Combat", 51] in result
    assert [2, "Appendix A: Tables", 81] in result


def test_drop_redundant_removes_index_entries():
    """Index entries whose pages fall within structural siblings' bounded spans are removed."""
    result = drop_redundant_bookmarks(SAMPLE_TOC)
    titles = [e[1] for e in result]
    assert "Ball, Lightning" not in titles  # p.5 in Part I span [1, 50)
    assert "Rogue" not in titles            # p.12 in Part I span [1, 50)
    assert "Sword, Long" not in titles      # p.55 in Part II span [50, 80)


def test_drop_redundant_empty_input():
    assert drop_redundant_bookmarks([]) == []


def test_drop_redundant_all_leaf_same_level():
    """All-leaf entries at the same level with non-overlapping pages are kept."""
    toc = [
        [1, "A", 1],
        [1, "B", 10],
        [1, "C", 20],
    ]
    result = drop_redundant_bookmarks(toc)
    assert len(result) == 3


def test_drop_redundant_l4_leaves_preserved():
    """L4 leaf nodes are preserved when they have no non-leaf siblings."""
    toc = [
        [1, "Part I", 1],
        [2, "Chapter 1", 2],
        [3, "Section 1.1", 3],
        [4, "Detail A", 4],
        [4, "Detail B", 5],
    ]
    result = drop_redundant_bookmarks(toc)
    assert len(result) == 5


def test_drop_redundant_childless_l2_preserved_when_not_positionally_redundant():
    """A childless L2 is kept if its page doesn't fall within a sibling's span."""
    toc = [
        [1, "Part I", 1],
        [2, "Chapter 1", 2],
        [3, "Section 1.1", 3],
        [2, "Chapter 2", 10],  # childless L2, but after Chapter 1's span
    ]
    result = drop_redundant_bookmarks(toc)
    assert [2, "Chapter 2", 10] in result


def test_drop_redundant_structural_leaf_at_root():
    """Root-level leaf entries are dropped when non-leaf root entries exist."""
    toc = [
        [1, "Part I: Core Rules", 1],
        [2, "Chapter 1", 2],
        [1, "Part II: Advanced", 50],
        [2, "Chapter 2", 51],
        # Leaf L1 entries — all pages point to page 1 (out-of-range scenario)
        [1, "Alchemy", 1],
        [1, "Beasts", 1],
        [1, "Curses", 1],
    ]
    result = drop_redundant_bookmarks(toc)
    titles = [e[1] for e in result]
    assert "Part I: Core Rules" in titles
    assert "Part II: Advanced" in titles
    assert "Chapter 1" in titles
    assert "Chapter 2" in titles
    assert "Alchemy" not in titles
    assert "Beasts" not in titles
    assert "Curses" not in titles


def test_drop_redundant_structural_leaf_preserves_deeper_levels():
    """Childless L2 entries are NOT dropped by structural-leaf (root-only heuristic)."""
    toc = [
        [1, "Part I", 1],
        [2, "Chapter 1", 2],
        [3, "Section 1.1", 3],
        [2, "Chapter 2: Quick Start", 10],  # childless L2, legitimate
    ]
    result = drop_redundant_bookmarks(toc)
    titles = [e[1] for e in result]
    assert "Chapter 2: Quick Start" in titles


def test_drop_redundant_all_leaf_roots_preserved():
    """When ALL root entries are leaf (no hierarchy), none are dropped."""
    toc = [
        [1, "Introduction", 1],
        [1, "Getting Started", 5],
        [1, "Appendix", 20],
    ]
    result = drop_redundant_bookmarks(toc)
    assert len(result) == 3


def test_drop_redundant_index_within_sibling_content():
    """L2 leaf whose page falls within an L2 non-leaf sibling's content span is dropped."""
    toc = [
        [1, "Part I", 1],
        [2, "Chapter 1", 2],
        [3, "Section 1.1", 3],
        [3, "Section 1.2", 8],
        [2, "Index: Sword", 4],  # page 4 < max_desc_page(Ch1)=8
        [2, "Chapter 2", 10],
    ]
    result = drop_redundant_bookmarks(toc)
    titles = [e[1] for e in result]
    assert "Index: Sword" not in titles
    assert "Chapter 1" in titles
    assert "Chapter 2" in titles


# --- normalize_toc_titles tests ---


def _make_mock_result(texts):
    """Create a mock ConversionResult with the given text strings."""
    mock = MagicMock()
    items = []
    for t in texts:
        item = MagicMock()
        item.text = t
        items.append(item)
    mock.document.texts = items
    return mock


def test_normalize_toc_titles_case_mismatch():
    """TOC title rewritten when case differs (small-caps scenario)."""
    toc = [[1, "Avinarcs", 1], [2, "Combat", 2]]
    result_mock = _make_mock_result(["avinaRcs", "Combat"])
    result = normalize_toc_titles(toc, result_mock)
    assert result[0][1] == "avinaRcs"
    assert result[1][1] == "Combat"


def test_normalize_toc_titles_already_matching():
    """TOC title unchanged when it already matches."""
    toc = [[1, "Introduction", 1]]
    result_mock = _make_mock_result(["Introduction"])
    result = normalize_toc_titles(toc, result_mock)
    assert result[0][1] == "Introduction"


def test_normalize_toc_titles_unmatched_left_as_is():
    """Unmatched TOC titles are left as-is."""
    toc = [[1, "Missing Chapter", 1]]
    result_mock = _make_mock_result(["Something Else"])
    result = normalize_toc_titles(toc, result_mock)
    assert result[0][1] == "Missing Chapter"


# --- _prepare_heading_source tests ---


def test_prepare_heading_source_none(tmp_path):
    """'none' returns (None, {})."""
    pdf_path = tmp_path / "test.pdf"
    pdf_path.touch()
    source, title_map = _prepare_heading_source(pdf_path, "none")
    assert source is None
    assert title_map == {}


def test_prepare_heading_source_numbering_returns_bytesio(sample_pdf):
    """'numbering' returns a (BytesIO, {}) with an empty TOC."""
    import fitz

    source, title_map = _prepare_heading_source(sample_pdf, "numbering")
    assert isinstance(source, BytesIO)
    doc = fitz.open(stream=source, filetype="pdf")
    assert doc.get_toc() == []
    doc.close()
    assert title_map == {}


def test_prepare_heading_source_bookmarks_returns_bytesio(sample_pdf):
    """'bookmarks' returns a (BytesIO, title_map) with a valid PDF."""
    source, title_map = _prepare_heading_source(sample_pdf, "bookmarks")
    assert isinstance(source, BytesIO)
    assert source.read(5) == b"%PDF-"
    assert isinstance(title_map, dict)


# --- CLI help test ---


# --- _build_title_map tests ---


def test_build_title_map_basic():
    toc = [[1, "Avinarcs", 1], [2, "Combat", 2]]
    result = _build_title_map(toc)
    assert result["avinarcs"] == "Avinarcs"
    assert result["combat"] == "Combat"


def test_build_title_map_collapses_whitespace():
    """Newlines and extra whitespace in bookmark titles are collapsed."""
    toc = [[1, "Part I: \nCharacter Law", 1]]
    result = _build_title_map(toc)
    assert result["particharacterlaw"] == "Part I: Character Law"


def test_build_title_map_first_wins():
    """First occurrence wins when normalized keys collide."""
    toc = [[1, "Hello World", 1], [1, "hello-world", 5]]
    result = _build_title_map(toc)
    assert result["helloworld"] == "Hello World"


# --- restore_bookmark_casing tests ---


def test_restore_bookmark_casing_replaces_text():
    """SectionHeaderItem text is replaced with original bookmark title."""
    from docling_core.types.doc.document import SectionHeaderItem

    mock_result = MagicMock()
    header = SectionHeaderItem.model_construct(
        text="avinaRcs", orig="avinaRcs", self_ref="#/texts/0",
    )
    mock_result.document.texts = [header]

    title_map = {"avinarcs": "Avinarcs"}
    restore_bookmark_casing(mock_result, title_map)
    assert header.text == "Avinarcs"
    assert header.orig == "Avinarcs"


def test_restore_bookmark_casing_prefix_match():
    """Truncated heading text matched to full bookmark title via prefix."""
    from docling_core.types.doc.document import SectionHeaderItem

    mock_result = MagicMock()
    header = SectionHeaderItem.model_construct(
        text="Part I: ", orig="Part I: ", self_ref="#/texts/0",
    )
    mock_result.document.texts = [header]

    title_map = {
        "particharacterlaw": "Part I: Character Law",
        "partiiadvancedrules": "Part II: Advanced Rules",
    }
    restore_bookmark_casing(mock_result, title_map)
    assert header.text == "Part I: Character Law"
    assert header.orig == "Part I: Character Law"


def test_restore_bookmark_casing_prefix_ambiguous_skipped():
    """Prefix match skipped when multiple candidates match."""
    from docling_core.types.doc.document import SectionHeaderItem

    mock_result = MagicMock()
    header = SectionHeaderItem.model_construct(
        text="Part", orig="Part", self_ref="#/texts/0",
    )
    mock_result.document.texts = [header]

    title_map = {
        "particharacterlaw": "Part I: Character Law",
        "partiiadvancedrules": "Part II: Advanced Rules",
    }
    restore_bookmark_casing(mock_result, title_map)
    # "Part" is a prefix of both — ambiguous, so text unchanged
    assert header.text == "Part"


def test_restore_bookmark_casing_skips_non_headers():
    """Non-SectionHeaderItem text items are left unchanged."""
    mock_result = MagicMock()
    item = MagicMock()
    item.text = "avinaRcs"
    # Make isinstance check fail by not being a SectionHeaderItem
    item.__class__ = type("TextItem", (), {})
    mock_result.document.texts = [item]

    title_map = {"avinarcs": "Avinarcs"}
    restore_bookmark_casing(mock_result, title_map)
    assert item.text == "avinaRcs"


def test_restore_bookmark_casing_empty_map():
    """No changes when title_map is empty."""
    from docling_core.types.doc.document import SectionHeaderItem

    mock_result = MagicMock()
    header = SectionHeaderItem.model_construct(
        text="avinaRcs", orig="avinaRcs", self_ref="#/texts/0",
    )
    mock_result.document.texts = [header]

    restore_bookmark_casing(mock_result, {})
    assert header.text == "avinaRcs"


# --- CLI help test ---


def test_heading_strategy_in_convert_help():
    """--heading-strategy appears in convert subcommand help."""
    from gamagama.pdf.main import build_parser

    parser = build_parser()
    for action in parser._subparsers._actions:
        if hasattr(action, "_parser_class"):
            for name, subparser in action.choices.items():
                if name == "convert":
                    help_text = subparser.format_help()
    assert "--heading-strategy" in help_text
    assert "bookmarks" in help_text
    assert "numbering" in help_text
    assert "none" in help_text
