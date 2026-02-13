# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Test Commands

```bash
make install                # Create .venv and install in editable mode with test deps
source .venv/bin/activate   # Activate venv (required for pytest/gg-pdf directly)
pytest                      # Run fast tests only (skips @pytest.mark.slow by default)
pytest -m slow              # Run only slow integration tests (~2 min docling import)
pytest -m ''                # Run all tests (fast + slow)
pytest tests/test_main.py   # Run a specific test file
pytest tests/test_main.py::test_name  # Run a single test
make test                   # Safe: ensures venv + deps before running pytest
```

## Architecture

gamagama-pdf is a pipeline CLI tool (`gg-pdf`) with three subcommands: `convert`, `split-md`, and `extract-tables`. It uses `docling` for PDF processing.

### Namespace Package

The `gamagama` Python namespace is a PEP 420 implicit namespace package (no `__init__.py` at `src/gamagama/`). This tool contributes the `gamagama.pdf` sub-package. All source code lives under `src/gamagama/pdf/`.

### Entry Point

`main.py:run()` builds an argparse parser with subcommands and dispatches to handler functions. The console script `gg-pdf` calls `gamagama.pdf.main:run`.

### Subcommands

- `convert` — convert a PDF into `.md` and `.json` using docling. Uses `TableFormerMode.ACCURATE` for table extraction, `ImageRefMode.PLACEHOLDER` for images. Options: `--ocr` (enable OCR, off by default), `--pages 1-50` (page range), `--force` (overwrite existing outputs), `--heading-strategy {auto,filtered,numbering,none}` (control heading hierarchy post-processing; default `auto`). Prints OCR hint when pages have no extractable text.
- `split-md` — split a markdown file into per-chapter files
- `extract-tables` — extract table data from docling JSON into simpler JSON

### Adding a New Subcommand

1. Add a `handle_<name>` function in `main.py`
2. Add a subparser in `build_parser()` with arguments and `set_defaults(func=handle_<name>)`
3. Add tests in `tests/test_main.py`
