import sys
from unittest.mock import MagicMock

import pytest
from fpdf import FPDF

from gamagama.pdf.headers import format_toc_tree, handle_headers


# --- format_toc_tree tests ---


def test_format_toc_tree_empty():
    assert format_toc_tree([]) is None


def test_format_toc_tree_single_entry():
    toc = [[1, "Introduction", 1]]
    result = format_toc_tree(toc)
    assert "L1" in result
    assert "Introduction" in result
    assert "p.1" in result
    # Childless L1 should be annotated
    assert "removed by 'filtered'" in result
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
            assert "removed by 'filtered'" not in line
    # L2 entries should be indented
    for line in result.splitlines():
        if "Chapter 1" in line:
            assert line.startswith("  ")
    assert "2 levels, 5 entries" in result


def test_format_toc_tree_childless_l1_annotated():
    toc = [
        [1, "Introduction", 1],
        [2, "Overview", 2],
        [1, "Index", 100],
    ]
    result = format_toc_tree(toc)
    for line in result.splitlines():
        if "Index" in line:
            assert "removed by 'filtered'" in line
        if "Introduction" in line:
            assert "removed by 'filtered'" not in line


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


# --- handle_headers tests ---


def test_handle_headers_file_not_found(tmp_path):
    args = MagicMock()
    args.input = str(tmp_path / "nonexistent.pdf")

    with pytest.raises(SystemExit) as exc_info:
        handle_headers(args)
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


def test_handle_headers_with_bookmarks(pdf_with_bookmarks, capsys):
    args = MagicMock()
    args.input = str(pdf_with_bookmarks)

    handle_headers(args)

    captured = capsys.readouterr()
    assert "Introduction" in captured.out
    assert "Chapter 1" in captured.out
    assert "Section 1.1" in captured.out
    assert "2 levels, 3 entries" in captured.out


def test_handle_headers_no_bookmarks(pdf_without_bookmarks, capsys):
    args = MagicMock()
    args.input = str(pdf_without_bookmarks)

    handle_headers(args)

    captured = capsys.readouterr()
    assert "No bookmarks found" in captured.out
    assert "numbering" in captured.out


def test_handle_headers_annotates_childless_l1(pdf_with_bookmarks, capsys):
    """Introduction is a childless L1 — should be annotated."""
    args = MagicMock()
    args.input = str(pdf_with_bookmarks)

    handle_headers(args)

    captured = capsys.readouterr()
    for line in captured.out.splitlines():
        if "Introduction" in line:
            assert "removed by 'filtered'" in line
        if "Chapter 1" in line and "L1" in line:
            assert "removed by 'filtered'" not in line


def test_headers_help():
    result = __import__("subprocess").run(
        [sys.executable, "-m", "gamagama.pdf", "headers", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "input" in result.stdout


def test_help_lists_headers_subcommand():
    result = __import__("subprocess").run(
        [sys.executable, "-m", "gamagama.pdf", "--help"],
        capture_output=True,
        text=True,
    )
    assert "headers" in result.stdout
