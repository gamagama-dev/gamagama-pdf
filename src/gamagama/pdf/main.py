import argparse
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


def handle_convert(args):
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.base_models import InputFormat, ConversionStatus
    from docling.datamodel.pipeline_options import (
        PdfPipelineOptions,
        TableStructureOptions,
        TableFormerMode,
    )
    from docling_core.types.doc.base import ImageRefMode

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
    print("split-md: not yet implemented")


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
