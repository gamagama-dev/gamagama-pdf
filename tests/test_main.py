import subprocess
import sys
from unittest.mock import patch, MagicMock

import pytest

from gamagama.pdf.main import build_parser, parse_page_range, handle_convert


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
