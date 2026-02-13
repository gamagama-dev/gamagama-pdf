import sys
from unittest.mock import MagicMock

import pytest
from fpdf import FPDF

from gamagama.pdf.bookmarks import format_toc_tree, handle_bookmarks


# --- format_toc_tree tests ---


def test_format_toc_tree_empty():
    assert format_toc_tree([]) is None


def test_format_toc_tree_single_entry():
    toc = [[1, "Introduction", 1]]
    result = format_toc_tree(toc)
    assert "L1" in result
    assert "Introduction" in result
    assert "p.1" in result
    assert "1 levels, 1 entries" in result


def test_format_toc_tree_nested():
    toc = [
        [1, "Part I", 1],
        [2, "Chapter 1", 2],
        [2, "Chapter 2", 10],
        [1, "Part II", 50],
        [2, "Chapter 3", 51],
    ]
    result = format_toc_tree(toc)
    # L1 entries with children should NOT be annotated
    assert "Part I" in result
    assert "Part II" in result
    for line in result.splitlines():
        if "Part I" in line or "Part II" in line:
            assert "redundant" not in line
    # L2 entries should be indented
    for line in result.splitlines():
        if "Chapter 1" in line:
            assert line.startswith("  ")
    assert "2 levels, 5 entries" in result


def test_format_toc_tree_redundant_annotated():
    """Index entries whose pages fall within a structural sibling's span are annotated."""
    toc = [
        [1, "Part I", 1],
        [2, "Chapter 1", 2],
        [2, "Chapter 2", 10],
        [1, "Part II", 50],
        [2, "Chapter 3", 51],
        [1, "Index Entry", 5],  # page 5 falls within Part I's bounded span [1, 50)
    ]
    result = format_toc_tree(toc)
    for line in result.splitlines():
        if "Index Entry" in line:
            assert "redundant" in line
        if "Part I" in line:
            assert "redundant" not in line


def test_format_toc_tree_three_levels():
    toc = [
        [1, "Part I", 1],
        [2, "Chapter 1", 2],
        [3, "Section A", 3],
    ]
    result = format_toc_tree(toc)
    assert "3 levels, 3 entries" in result
    # L3 should have 4 spaces indent
    for line in result.splitlines():
        if "Section A" in line:
            assert line.startswith("    ")


def test_format_toc_tree_dot_leaders():
    toc = [[1, "Intro", 1]]
    result = format_toc_tree(toc)
    # Should contain dots between title and page number
    for line in result.splitlines():
        if "Intro" in line:
            assert ".." in line


# --- handle_bookmarks tests ---


def test_handle_bookmarks_file_not_found(tmp_path):
    args = MagicMock()
    args.input = str(tmp_path / "nonexistent.pdf")

    with pytest.raises(SystemExit) as exc_info:
        handle_bookmarks(args)
    assert exc_info.value.code == 1


@pytest.fixture
def pdf_with_bookmarks(tmp_path):
    """Create a PDF with bookmarks using fpdf2."""
    pdf = FPDF()
    pdf.set_auto_page_break(auto=False)

    pdf.add_page()
    pdf.set_font("Helvetica", "B", 24)
    pdf.cell(text="Introduction")

    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(text="Chapter 1")

    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(text="Section 1.1")

    path = tmp_path / "bookmarks.pdf"
    pdf.output(str(path))

    # Add bookmarks using PyMuPDF since fpdf2 bookmark support is limited
    import fitz

    doc = fitz.open(str(path))
    toc = [
        [1, "Introduction", 1],
        [1, "Chapter 1", 2],
        [2, "Section 1.1", 3],
    ]
    doc.set_toc(toc)
    doc.save(str(path), incremental=True, encryption=0)
    doc.close()
    return path


@pytest.fixture
def pdf_without_bookmarks(tmp_path):
    """Create a PDF without bookmarks."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.cell(text="Hello World")
    path = tmp_path / "no_bookmarks.pdf"
    pdf.output(str(path))
    return path


def test_handle_bookmarks_with_bookmarks(pdf_with_bookmarks, capsys):
    args = MagicMock()
    args.input = str(pdf_with_bookmarks)

    handle_bookmarks(args)

    captured = capsys.readouterr()
    assert "Introduction" in captured.out
    assert "Chapter 1" in captured.out
    assert "Section 1.1" in captured.out
    assert "2 levels, 3 entries" in captured.out


def test_handle_bookmarks_no_bookmarks(pdf_without_bookmarks, capsys):
    args = MagicMock()
    args.input = str(pdf_without_bookmarks)

    handle_bookmarks(args)

    captured = capsys.readouterr()
    assert "No bookmarks found" in captured.out
    assert "numbering" in captured.out


def test_handle_bookmarks_annotates_redundant(tmp_path, capsys):
    """A leaf L1 whose page falls within a non-leaf sibling's span is annotated."""
    pdf = FPDF()
    pdf.set_auto_page_break(auto=False)
    for _ in range(5):
        pdf.add_page()
        pdf.set_font("Helvetica", size=12)
        pdf.cell(text="content")
    path = tmp_path / "test.pdf"
    pdf.output(str(path))

    import fitz

    doc = fitz.open(str(path))
    toc = [
        [1, "Part I", 1],
        [2, "Chapter 1", 2],
        [2, "Chapter 2", 3],
        [1, "Index", 2],  # page 2 falls within Part I's span
        [1, "Part II", 4],
        [2, "Chapter 3", 5],
    ]
    doc.set_toc(toc)
    doc.save(str(path), incremental=True, encryption=0)
    doc.close()

    args = MagicMock()
    args.input = str(path)
    handle_bookmarks(args)

    captured = capsys.readouterr()
    for line in captured.out.splitlines():
        if "Index" in line:
            assert "redundant" in line
        if "Part I" in line:
            assert "redundant" not in line


def test_bookmarks_help():
    result = __import__("subprocess").run(
        [sys.executable, "-m", "gamagama.pdf", "bookmarks", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "input" in result.stdout


def test_help_lists_bookmarks_subcommand():
    result = __import__("subprocess").run(
        [sys.executable, "-m", "gamagama.pdf", "--help"],
        capture_output=True,
        text=True,
    )
    assert "bookmarks" in result.stdout
