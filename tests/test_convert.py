import json
import sys
from io import BytesIO
from unittest.mock import patch, MagicMock

import pytest
from fpdf import FPDF

from gamagama.pdf.convert import parse_page_range, filter_toc, _prepare_heading_source, handle_convert


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
    args.heading_strategy = "auto"

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
    args.heading_strategy = "auto"

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
    args.heading_strategy = "auto"

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
    args.heading_strategy = "auto"

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
    args.heading_strategy = "auto"

    with pytest.raises(SystemExit) as exc_info:
        handle_convert(args)
    assert exc_info.value.code == 1


# --- filter_toc tests ---


SAMPLE_TOC = [
    # Structural bookmarks (with children)
    [1, "Part I: Core Rules", 1],
    [2, "Chapter 1: Introduction", 2],
    [2, "Chapter 2: Characters", 10],
    [1, "Part II: Advanced Rules", 50],
    [2, "Chapter 3: Combat", 51],
    # Childless L1 index entries
    [1, "Ball, Lightning", 120],
    [1, "Rogue", 130],
    [1, "Sword, Long", 140],
]


def test_filter_toc_auto_returns_unchanged():
    """'auto' strategy returns the TOC unchanged."""
    result = filter_toc(SAMPLE_TOC, "auto")
    assert result == SAMPLE_TOC


def test_filter_toc_numbering_returns_empty():
    """'numbering' strategy returns an empty list."""
    result = filter_toc(SAMPLE_TOC, "numbering")
    assert result == []


def test_filter_toc_filtered_removes_childless_l1():
    """'filtered' strategy removes L1 entries with no children."""
    result = filter_toc(SAMPLE_TOC, "filtered")
    # Structural L1 entries (followed by L2 children) should be kept
    assert [1, "Part I: Core Rules", 1] in result
    assert [1, "Part II: Advanced Rules", 50] in result
    # All L2 entries should be kept
    assert [2, "Chapter 1: Introduction", 2] in result
    assert [2, "Chapter 2: Characters", 10] in result
    assert [2, "Chapter 3: Combat", 51] in result
    # Childless L1 index entries should be removed
    assert [1, "Ball, Lightning", 120] not in result
    assert [1, "Rogue", 130] not in result
    assert [1, "Sword, Long", 140] not in result


def test_filter_toc_filtered_empty_input():
    """'filtered' strategy handles empty TOC."""
    assert filter_toc([], "filtered") == []


def test_filter_toc_filtered_all_childless():
    """'filtered' removes all entries when every L1 is childless."""
    toc = [[1, "A", 1], [1, "B", 2], [1, "C", 3]]
    assert filter_toc(toc, "filtered") == []


def test_filter_toc_filtered_preserves_non_l1():
    """'filtered' preserves L2+ entries even between childless L1s."""
    toc = [
        [1, "Index A", 1],
        [2, "Sub A", 2],
        [1, "Index B", 3],
    ]
    result = filter_toc(toc, "filtered")
    assert [1, "Index A", 1] in result
    assert [2, "Sub A", 2] in result
    assert [1, "Index B", 3] not in result


# --- _prepare_heading_source tests ---


def test_prepare_heading_source_auto(tmp_path):
    """'auto' returns the input path as a string."""
    pdf_path = tmp_path / "test.pdf"
    pdf_path.touch()
    result = _prepare_heading_source(pdf_path, "auto")
    assert result == str(pdf_path)


def test_prepare_heading_source_none(tmp_path):
    """'none' returns None."""
    pdf_path = tmp_path / "test.pdf"
    pdf_path.touch()
    result = _prepare_heading_source(pdf_path, "none")
    assert result is None


def test_prepare_heading_source_filtered_returns_bytesio(sample_pdf):
    """'filtered' returns a BytesIO with a valid PDF."""
    result = _prepare_heading_source(sample_pdf, "filtered")
    assert isinstance(result, BytesIO)
    assert result.read(5) == b"%PDF-"


def test_prepare_heading_source_numbering_returns_bytesio(sample_pdf):
    """'numbering' returns a BytesIO with an empty TOC."""
    import fitz

    result = _prepare_heading_source(sample_pdf, "numbering")
    assert isinstance(result, BytesIO)
    doc = fitz.open(stream=result, filetype="pdf")
    assert doc.get_toc() == []
    doc.close()


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
    assert "auto" in help_text
    assert "filtered" in help_text
    assert "numbering" in help_text
    assert "none" in help_text
