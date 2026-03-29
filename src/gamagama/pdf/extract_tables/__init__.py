import json
import sys
from pathlib import Path

from .extraction import (
    _source_from_stem,
    _build_text_lookup,
    _build_section_header_index,
    _extract_title_and_heading,
    _extract_grid_data,
)
from .dedup import _deduplicate_within_book, _resolve_conflicts
from .index import _assign_filenames, _save_json, _update_cross_index


def handle_extract_tables(args):
    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    force = getattr(args, "force", False)

    # Derive source from stem
    stem = input_path.stem
    source = _source_from_stem(stem)

    # Check output directory
    book_dir = output_dir / source
    if book_dir.exists() and not force:
        print(
            f"Error: output directory '{book_dir}' already exists. "
            "Use --force to overwrite.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Load docling JSON
    with open(input_path) as f:
        doc = json.load(f)

    # Build lookups
    text_by_ref = _build_text_lookup(doc)
    texts_list = doc.get("texts", [])
    section_headers = _build_section_header_index(texts_list)

    # Extract raw table records
    raw_tables = []
    for table_dict in doc.get("tables", []):
        if table_dict["data"]["num_rows"] == 0 or table_dict["data"]["num_cols"] == 0:
            continue
        page = table_dict["prov"][0]["page_no"]
        title, heading, title_row_idx = _extract_title_and_heading(
            table_dict, text_by_ref, section_headers
        )
        col_headers, row_headers, rows = _extract_grid_data(table_dict, title_row_idx)
        raw_tables.append(
            {
                "source": source,
                "page": page,
                "heading": heading,
                "title": title,
                "col_headers": col_headers,
                "row_headers": row_headers,
                "rows": rows,
            }
        )

    # Deduplicate within book
    unique, conflicts, dupe_count = _deduplicate_within_book(raw_tables)

    # Resolve conflicts interactively
    if conflicts:
        resolved = _resolve_conflicts(conflicts)
        unique.extend(resolved)

    # Assign filenames (sorts by page in place)
    _assign_filenames(unique)

    # Create output directory
    book_dir.mkdir(parents=True, exist_ok=True)

    # Write per-table JSON files
    for table in unique:
        table_data = {
            "source": table["source"],
            "page": table["page"],
            "heading": table["heading"],
            "title": table["title"],
            "col_headers": table["col_headers"],
            "row_headers": table["row_headers"],
            "rows": table["rows"],
        }
        _save_json(table_data, book_dir / table["filename"])

    # Write per-book index.json
    book_index = {
        "source": source,
        "tables": [
            {
                "file": t["filename"],
                "page": t["page"],
                "title": t["title"],
                "heading": t["heading"],
                "rows": len(t["rows"]),
                "cols": len(t["col_headers"]) if t["col_headers"] else 0,
            }
            for t in unique
        ],
    }
    _save_json(book_index, book_dir / "index.json")

    # Update cross-book index
    output_dir.mkdir(parents=True, exist_ok=True)
    _update_cross_index(output_dir, source, unique)

    # Summary
    num_written = len(unique)
    num_conflicts = len(conflicts)
    print(
        f"{num_written} tables written to {book_dir} "
        f"({dupe_count} duplicates skipped, {num_conflicts} conflicts resolved)"
    )
