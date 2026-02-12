import subprocess
import sys

from gamagama.pdf.main import build_parser


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


def test_split_md_help_shows_new_args():
    result = subprocess.run(
        [sys.executable, "-m", "gamagama.pdf", "split-md", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "--level" in result.stdout
    assert "--force" in result.stdout
