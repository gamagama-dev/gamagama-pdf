import json
import subprocess
import sys
from unittest.mock import patch, MagicMock

import pytest
from fpdf import FPDF

from gamagama.pdf.main import (
    build_parser,
    parse_page_range,
    handle_convert,
    handle_split_md,
    slugify,
    split_markdown,
    strip_image_placeholders,
)


def test_help_exits_zero():
    result = subprocess.run(
        [sys.executable, "-m", "gamagama.pdf", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "gg-pdf" in result.stdout


def test_help_lists_subcommands():
    result = subprocess.run(
        [sys.executable, "-m", "gamagama.pdf", "--help"],
        capture_output=True,
        text=True,
    )
    assert "convert" in result.stdout
    assert "split-md" in result.stdout
    assert "extract-tables" in result.stdout


def test_convert_help():
    result = subprocess.run(
        [sys.executable, "-m", "gamagama.pdf", "convert", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "input" in result.stdout
    assert "--output-dir" in result.stdout


def test_split_md_help():
    result = subprocess.run(
        [sys.executable, "-m", "gamagama.pdf", "split-md", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "input" in result.stdout
    assert "--output-dir" in result.stdout


def test_extract_tables_help():
    result = subprocess.run(
        [sys.executable, "-m", "gamagama.pdf", "extract-tables", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "input" in result.stdout
    assert "--output-dir" in result.stdout


def test_build_parser_returns_parser():
    parser = build_parser()
    assert parser.prog == "gg-pdf"


def test_no_args_prints_help():
    result = subprocess.run(
        [sys.executable, "-m", "gamagama.pdf"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "gg-pdf" in result.stdout


# --- parse_page_range tests ---


def test_parse_page_range_none():
    assert parse_page_range(None) == (1, sys.maxsize)


def test_parse_page_range_single():
    assert parse_page_range("5") == (5, 5)


def test_parse_page_range_range():
    assert parse_page_range("1-50") == (1, 50)


# --- convert --help shows new args ---


def test_convert_help_shows_new_args():
    result = subprocess.run(
        [sys.executable, "-m", "gamagama.pdf", "convert", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "--ocr" in result.stdout
    assert "--pages" in result.stdout
    assert "--force" in result.stdout


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

    with pytest.raises(SystemExit) as exc_info:
        handle_convert(args)
    assert exc_info.value.code == 1


# --- split-md help ---


def test_split_md_help_shows_new_args():
    result = subprocess.run(
        [sys.executable, "-m", "gamagama.pdf", "split-md", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "--level" in result.stdout
    assert "--force" in result.stdout


# --- slugify tests ---


def test_slugify_basic():
    assert slugify("Core Rules") == "core-rules"


def test_slugify_chapter_prefix():
    assert slugify("Chapter 1: Core Rules") == "core-rules"


def test_slugify_chapter_prefix_dash():
    assert slugify("Chapter 3 - Combat") == "combat"


def test_slugify_part_roman_numeral():
    assert slugify("Part III: Advanced Topics") == "advanced-topics"


def test_slugify_section_prefix():
    assert slugify("Section 5: Magic") == "magic"


def test_slugify_appendix_prefix():
    assert slugify("Appendix A: Tables") == "tables"


def test_slugify_special_chars():
    assert slugify("Hello, World! (2024)") == "hello-world-2024"


def test_slugify_empty_result():
    assert slugify("Chapter 1:") == "untitled"


def test_slugify_truncates_long_heading():
    long_heading = " ".join(f"Word{i}" for i in range(50))
    slug = slugify(long_heading)
    assert len(slug) <= 80


def test_slugify_truncates_at_hyphen_boundary():
    # 'aaa-bbb-ccc-...' pattern where truncation should not leave a partial word
    long_heading = "-".join(["abcdefgh"] * 20)
    slug = slugify(long_heading)
    assert len(slug) <= 80
    assert not slug.endswith("-")


def test_slugify_no_truncation_when_short():
    result = slugify("Short Heading")
    assert result == "short-heading"
    # Same as unlimited
    assert result == slugify("Short Heading", max_length=None)


def test_slugify_max_length_none_disables_truncation():
    long_heading = " ".join(f"Word{i}" for i in range(50))
    slug = slugify(long_heading, max_length=None)
    assert len(slug) > 80


# --- split_markdown tests ---


def test_split_markdown_basic():
    text = "preamble\n\n## Chapter 1\n\nbody 1\n\n## Chapter 2\n\nbody 2\n"
    sections = split_markdown(text)
    assert len(sections) == 3
    assert sections[0][0] == ""
    assert "preamble" in sections[0][1]
    assert sections[1][0] == "Chapter 1"
    assert "body 1" in sections[1][1]
    assert sections[2][0] == "Chapter 2"
    assert "body 2" in sections[2][1]


def test_split_markdown_no_preamble():
    text = "## First\n\ncontent\n"
    sections = split_markdown(text)
    assert len(sections) == 2
    assert sections[0][0] == ""
    assert sections[0][1].strip() == ""
    assert sections[1][0] == "First"


def test_split_markdown_level_3():
    text = "## Keep Together\n\n### Sub A\n\nsub body\n\n### Sub B\n\nsub body 2\n"
    sections = split_markdown(text, level=3)
    assert len(sections) == 3
    assert sections[0][0] == ""
    assert "Keep Together" in sections[0][1]
    assert sections[1][0] == "Sub A"
    assert sections[2][0] == "Sub B"


def test_split_markdown_ignores_subheadings():
    text = "## Main\n\n### Sub\n\nbody\n"
    sections = split_markdown(text, level=2)
    assert len(sections) == 2
    assert sections[1][0] == "Main"
    assert "### Sub" in sections[1][1]


def test_split_markdown_no_headings():
    text = "Just some text\nwith no headings.\n"
    sections = split_markdown(text)
    assert len(sections) == 1
    assert sections[0][0] == ""
    assert "Just some text" in sections[0][1]


# --- strip_image_placeholders tests ---


def test_strip_image_placeholders_single():
    text = "before\n\n![img](image://abc123)\n\nafter\n"
    result = strip_image_placeholders(text)
    assert "image://" not in result
    assert "before" in result
    assert "after" in result


def test_strip_image_placeholders_multiple():
    text = "text\n\n![a](image://1)\n\n![b](image://2)\n\n![c](image://3)\n\nmore\n"
    result = strip_image_placeholders(text)
    assert "image://" not in result
    assert "text" in result
    assert "more" in result


def test_strip_image_placeholders_preserves_normal_images():
    text = "![photo](https://example.com/photo.jpg)\n"
    result = strip_image_placeholders(text)
    assert "![photo](https://example.com/photo.jpg)" in result


# --- handle_split_md tests ---


def test_handle_split_md_basic(tmp_path, capsys):
    """End-to-end: split a markdown file and verify output files."""
    md_content = (
        "# Title\n\nIntro paragraph.\n\n"
        "## Chapter 1: Core Rules\n\nRules content here.\n\n"
        "## Chapter 2: Equipment\n\nEquipment content.\n"
    )
    input_file = tmp_path / "book.md"
    input_file.write_text(md_content)
    output_dir = tmp_path / "output"

    args = MagicMock()
    args.input = str(input_file)
    args.output_dir = str(output_dir)
    args.level = 2
    args.force = False

    handle_split_md(args)

    assert (output_dir / "00-preamble.md").exists()
    assert (output_dir / "01-core-rules.md").exists()
    assert (output_dir / "02-equipment.md").exists()

    # Preamble contains the title
    preamble = (output_dir / "00-preamble.md").read_text()
    assert "Title" in preamble

    # Chapter files re-add the heading
    ch1 = (output_dir / "01-core-rules.md").read_text()
    assert ch1.startswith("## Chapter 1: Core Rules")
    assert "Rules content here." in ch1

    # Summary printed
    captured = capsys.readouterr()
    assert "3 files" in captured.out


def test_handle_split_md_input_not_found(tmp_path):
    args = MagicMock()
    args.input = str(tmp_path / "nonexistent.md")
    args.output_dir = str(tmp_path)
    args.level = 2
    args.force = False

    with pytest.raises(SystemExit) as exc_info:
        handle_split_md(args)
    assert exc_info.value.code == 1


def test_handle_split_md_warns_on_long_heading(tmp_path, capsys):
    """When a heading is too long and gets truncated, warn on stderr."""
    long_title = " ".join(f"Word{i}" for i in range(50))
    md_content = f"## {long_title}\n\ncontent\n"
    input_file = tmp_path / "book.md"
    input_file.write_text(md_content)
    output_dir = tmp_path / "output"

    args = MagicMock()
    args.input = str(input_file)
    args.output_dir = str(output_dir)
    args.level = 2
    args.force = False

    handle_split_md(args)

    captured = capsys.readouterr()
    assert "Warning" in captured.err
    assert "truncated" in captured.err
    # Warning should include a preview of the heading to help find it
    assert "Word0" in captured.err

    # File should still be created with a truncated name
    files = list(output_dir.glob("*.md"))
    assert len(files) == 1
    assert len(files[0].name) <= 255


def test_handle_split_md_refuses_overwrite(tmp_path):
    md_content = "## Chapter 1\n\ncontent\n"
    input_file = tmp_path / "book.md"
    input_file.write_text(md_content)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "01-chapter-1.md").write_text("old")

    args = MagicMock()
    args.input = str(input_file)
    args.output_dir = str(output_dir)
    args.level = 2
    args.force = False

    with pytest.raises(SystemExit) as exc_info:
        handle_split_md(args)
    assert exc_info.value.code == 1
