import argparse
import sys

from gamagama.pdf.convert import handle_convert
from gamagama.pdf.extract_tables import handle_extract_tables
from gamagama.pdf.split_md import handle_split_md


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
    convert_parser.add_argument(
        "--heading-strategy",
        choices=["auto", "filtered", "numbering", "none"],
        default="auto",
        help=(
            "Strategy for heading hierarchy post-processing (default: auto). "
            "'auto' uses bookmarks, numbering, then font styles. "
            "'filtered' strips childless L1 bookmarks (index entries). "
            "'numbering' skips bookmarks entirely. "
            "'none' disables heading post-processing."
        ),
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
