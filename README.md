# gamagama-pdf

`gamagama-pdf` (Game Master Game Manager — PDF) processes RPG rulebook PDFs into AI-friendly markdown and structured JSON for table extraction.

The core of this repo is a command-line tool called `gg-pdf`. It operates as a pipeline with three subcommands:

1. `convert` — process a PDF, emit both `.md` and `.json`
2. `split-md` — split a markdown file into per-chapter files
3. `extract-tables` — extract table data from docling JSON into simpler JSON

## Installation

The recommended way to install `gamagama-pdf` is using `pipx`, which automatically handles virtual environments.

1.  **Install pipx**: If you don't have it, install `pipx` first.
    ```bash
    python3 -m pip install --user pipx
    python3 -m pipx ensurepath
    ```
    You may need to open a new terminal for the path changes to take effect.

2.  **Install gamagama-pdf**: From the project's root directory, run:
    ```bash
    pipx install .
    ```

This installs the tool in an isolated environment and makes the `gg-pdf` command available system-wide.

## Usage

After installation, you can run the tool using `gg-pdf`.

To see available options, use the `--help` flag:

```bash
gg-pdf --help
```

Convert a PDF to markdown and JSON:

```bash
gg-pdf convert rulebook.pdf -o output/
```

Split a converted markdown file into per-chapter files:

```bash
gg-pdf split-md output/rulebook.md -o chapters/
```

Extract tables from docling JSON into simpler JSON:

```bash
gg-pdf extract-tables output/rulebook.json -o tables/
```

## Uninstallation

If you installed the project with `pipx`, run:

```bash
pipx uninstall gamagama-pdf
```

## Contributing

For instructions on how to set up a development environment and run tests, please see [DEVELOPMENT.md](DEVELOPMENT.md).
