import argparse
import re
import sys
from pathlib import Path


def parse_page_range(value):
    """Parse '10-50' into (10, 50) tuple. Returns default if value is None."""
    if value is None:
        return (1, sys.maxsize)
    parts = value.split("-")
    if len(parts) == 1:
        n = int(parts[0])
        return (n, n)
    return (int(parts[0]), int(parts[1]))


def slugify(text, max_length=80):
    """Convert heading text to a filename-safe slug.

    Truncates at a hyphen boundary if the slug exceeds max_length.
    Pass max_length=None to disable truncation.
    """
    # Strip common chapter/section prefixes
    text = re.sub(
        r"^(chapter|part|section|appendix)\s+[\dIVXLCDMivxlcdm]+[:\-\.\s]\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    text = text or "untitled"
    if max_length is not None and len(text) > max_length:
        text = text[:max_length].rsplit("-", 1)[0]
    return text


def split_markdown(text, level=2):
    """Split markdown text on headings of the given level.

    Returns a list of (heading_text, body) tuples. The first tuple has an
    empty heading string for any preamble content before the first heading.
    """
    pattern = re.compile(
        r"^(#{" + str(level) + r"})(?!#)\s+(.+)$", re.MULTILINE
    )
    sections = []
    last_end = 0
    last_heading = ""

    for match in pattern.finditer(text):
        body = text[last_end : match.start()]
        sections.append((last_heading, body))
        last_heading = match.group(2)
        last_end = match.end()

    # Remaining text after last heading
    sections.append((last_heading, text[last_end:]))
    return sections


def strip_image_placeholders(text):
    """Remove docling image placeholder lines and collapse excess blank lines."""
    text = re.sub(r"^!\[.*?\]\(image://.*?\)\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def handle_convert(args):
    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    stem = input_path.stem

    # Validate input exists
    if not input_path.is_file():
        print(f"Error: {input_path} not found or is not a file.", file=sys.stderr)
        sys.exit(1)

    # Check output files don't already exist (unless --force)
    md_path = output_dir / f"{stem}.md"
    json_path = output_dir / f"{stem}.json"
    existing = [p for p in (md_path, json_path) if p.exists()]
    if existing and not args.force:
        for p in existing:
            print(f"Error: {p} already exists. Use --force to overwrite.", file=sys.stderr)
        sys.exit(1)

    # Create output dir if needed
    output_dir.mkdir(parents=True, exist_ok=True)

    # Heavy imports deferred until after cheap validation checks
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.base_models import InputFormat, ConversionStatus
    from docling.datamodel.pipeline_options import (
        PdfPipelineOptions,
        TableStructureOptions,
        TableFormerMode,
    )
    from docling_core.types.doc.base import ImageRefMode

    # Configure pipeline
    pipeline_options = PdfPipelineOptions(
        do_table_structure=True,
        table_structure_options=TableStructureOptions(
            mode=TableFormerMode.ACCURATE,
        ),
        do_ocr=args.ocr,
        generate_page_images=False,
        generate_picture_images=False,
    )
    converter = DocumentConverter(
        allowed_formats=[InputFormat.PDF],
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=pipeline_options,
            ),
        },
    )

    # Convert
    print(f"Converting {input_path.name}...")
    page_range = parse_page_range(args.pages)
    result = converter.convert(
        str(input_path),
        raises_on_error=False,
        page_range=page_range,
    )

    # Check status
    if result.status == ConversionStatus.FAILURE:
        print("Error: conversion failed.", file=sys.stderr)
        for err in result.errors:
            print(f"  {err.error_message}", file=sys.stderr)
        sys.exit(1)
    if result.status == ConversionStatus.PARTIAL_SUCCESS:
        print("Warning: conversion partially succeeded. Some content may be missing.")
        for err in result.errors:
            print(f"  {err.error_message}", file=sys.stderr)

    doc = result.document

    # Re-check before writing (files may have appeared during long conversion)
    if not args.force:
        existing = [p for p in (md_path, json_path) if p.exists()]
        if existing:
            for p in existing:
                print(f"Error: {p} already exists. Use --force to overwrite.", file=sys.stderr)
            sys.exit(1)

    # Save outputs
    print(f"Writing {md_path}...")
    doc.save_as_markdown(md_path, image_mode=ImageRefMode.PLACEHOLDER)
    print(f"Writing {json_path}...")
    doc.save_as_json(json_path, image_mode=ImageRefMode.PLACEHOLDER)

    # Summary
    num_pages = doc.num_pages()
    num_tables = len(doc.tables)
    print(f"Done: {num_pages} pages, {num_tables} tables -> {md_path.name}, {json_path.name}")

    # OCR hint (only when OCR is off)
    if not args.ocr:
        pages_with_text = set()
        for text_item in doc.texts:
            for prov in text_item.prov:
                pages_with_text.add(prov.page_no)
        all_pages = set(doc.pages.keys())
        empty_pages = sorted(all_pages - pages_with_text)
        if empty_pages:
            n = len(empty_pages)
            print(
                f"Note: {n} page(s) had no extractable text. "
                f"Consider re-running with --ocr."
            )


def handle_split_md(args):
    input_path = Path(args.input)
    output_dir = Path(args.output_dir)

    # Validate input exists
    if not input_path.is_file():
        print(f"Error: {input_path} not found or is not a file.", file=sys.stderr)
        sys.exit(1)

    text = input_path.read_text()
    sections = split_markdown(text, args.level)

    # Build list of (path, content) pairs
    files_to_write = []
    for i, (heading, body) in enumerate(sections):
        body = strip_image_placeholders(body).strip()
        if i == 0:
            if not body:
                continue
            filename = "00-preamble.md"
            content = body + "\n"
        else:
            slug = slugify(heading)
            if slug != slugify(heading, max_length=None):
                preview = heading.strip()[:80]
                print(
                    f"Warning: heading too long, truncated for filename "
                    f"(section {i}): \"{preview}...\"",
                    file=sys.stderr,
                )
            filename = f"{i:02d}-{slug}.md"
            hashes = "#" * args.level
            content = f"{hashes} {heading}\n\n{body}\n"
        files_to_write.append((output_dir / filename, content))

    # Batch overwrite check
    if not args.force:
        existing = [p for p, _ in files_to_write if p.exists()]
        if existing:
            for p in existing:
                print(f"Error: {p} already exists. Use --force to overwrite.", file=sys.stderr)
            sys.exit(1)

    # Write files
    output_dir.mkdir(parents=True, exist_ok=True)
    for path, content in files_to_write:
        path.write_text(content)

    # Summary
    print(f"Split {input_path.name} into {len(files_to_write)} files in {output_dir}/")
    for path, _ in files_to_write:
        print(f"  {path.name}")


def handle_extract_tables(args):
    print("extract-tables: not yet implemented")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="gg-pdf",
        description="Process RPG rulebook PDFs into AI-friendly markdown and structured JSON.",
    )
    subparsers = parser.add_subparsers(dest="command")

    # convert
    convert_parser = subparsers.add_parser(
        "convert", help="Convert a PDF to markdown and JSON."
    )
    convert_parser.add_argument("input", help="Path to the input PDF file.")
    convert_parser.add_argument(
        "-o",
        "--output-dir",
        default=".",
        help="Output directory (defaults to current directory).",
    )
    convert_parser.add_argument(
        "--ocr",
        action="store_true",
        help="Enable OCR for scanned pages.",
    )
    convert_parser.add_argument(
        "--pages",
        default=None,
        help="Page range to convert (e.g. '1-50' or '5').",
    )
    convert_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing output files.",
    )
    convert_parser.set_defaults(func=handle_convert)

    # split-md
    split_md_parser = subparsers.add_parser(
        "split-md", help="Split a markdown file into per-chapter files."
    )
    split_md_parser.add_argument("input", help="Path to the input markdown file.")
    split_md_parser.add_argument(
        "-o",
        "--output-dir",
        default=".",
        help="Output directory (defaults to current directory).",
    )
    split_md_parser.add_argument(
        "--level",
        type=int,
        default=2,
        help="Heading level to split on (default: 2).",
    )
    split_md_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing output files.",
    )
    split_md_parser.set_defaults(func=handle_split_md)

    # extract-tables
    extract_tables_parser = subparsers.add_parser(
        "extract-tables", help="Extract table data from docling JSON into simpler JSON."
    )
    extract_tables_parser.add_argument("input", help="Path to the input JSON file.")
    extract_tables_parser.add_argument(
        "-o",
        "--output-dir",
        default=".",
        help="Output directory (defaults to current directory).",
    )
    extract_tables_parser.set_defaults(func=handle_extract_tables)

    return parser


def run():
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    args.func(args)
