import argparse
import sys


def handle_convert(args):
    print("convert: not yet implemented")


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
