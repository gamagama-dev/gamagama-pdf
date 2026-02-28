import bisect
import json
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _source_from_stem(stem: str) -> str:
    m = re.match(r"^(gcp-rmu-\d+)", stem)
    return m.group(1) if m else stem


def _normalize_title(title: str) -> str:
    title = title.lower()
    title = re.sub(r"[^\w\s]", " ", title)
    title = re.sub(r"\s+", " ", title).strip()
    return title


def _normalize_cell(text: str) -> str:
    return _normalize_title(text)


def _build_text_lookup(doc: dict) -> dict:
    return {item["self_ref"]: item for item in doc.get("texts", [])}


def _build_section_header_index(texts_list: list) -> list:
    """Return sorted list of (page_no, text_item) for section_header items."""
    headers = []
    for item in texts_list:
        if item.get("label") == "section_header":
            prov = item.get("prov", [])
            if prov:
                headers.append((prov[0]["page_no"], item))
    headers.sort(key=lambda x: x[0])
    return headers


def _find_section_header_before(section_headers: list, page: int):
    """Find the most recent section_header on or before page using bisect."""
    if not section_headers:
        return None
    pages = [h[0] for h in section_headers]
    idx = bisect.bisect_right(pages, page) - 1
    if idx >= 0:
        return section_headers[idx][1]
    return None


def _extract_title_and_heading(table_dict, text_by_ref, section_headers):
    page = table_dict["prov"][0]["page_no"]
    cells = table_dict["data"]["table_cells"]
    num_cols = table_dict["data"]["num_cols"]

    # --- Title detection: row-0 cell with largest col_span >= num_cols / 2 ---
    title = None
    title_row_idx = None
    best_span = -1
    for c in cells:
        if c["start_row_offset_idx"] == 0 and c["col_span"] >= num_cols / 2:
            if c["col_span"] > best_span:
                best_span = c["col_span"]
                title = c["text"].strip()
                title_row_idx = 0

    # Fallback: parent text item
    if not title:
        parent_ref = table_dict.get("parent", {}).get("$ref", "")
        parent_item = text_by_ref.get(parent_ref)
        if parent_item:
            title = parent_item.get("text", "").strip()

    # Final fallback
    if not title:
        title = f"p{page}-table"

    # --- Heading detection ---
    heading = ""
    parent_ref = table_dict.get("parent", {}).get("$ref", "")
    parent_item = text_by_ref.get(parent_ref)

    if parent_item and parent_item.get("label") == "section_header":
        heading = parent_item.get("text", "").strip()
    else:
        sh = _find_section_header_before(section_headers, page)
        if sh:
            heading = sh.get("text", "").strip()

    return title, heading, title_row_idx


def _extract_grid_data(table_dict, title_row_idx):
    cells = table_dict["data"]["table_cells"]
    grid = table_dict["data"]["grid"]
    num_rows = table_dict["data"]["num_rows"]

    # Which rows are column_header rows
    col_header_rows = set()
    for c in cells:
        if c.get("column_header"):
            col_header_rows.add(c["start_row_offset_idx"])

    # Exclude title row from header rows for col_headers extraction
    header_rows_no_title = col_header_rows - (
        {title_row_idx} if title_row_idx is not None else set()
    )

    # Last header row gives column labels
    col_headers = None
    if header_rows_no_title:
        last_hdr_row = max(header_rows_no_title)
        col_headers = [cell["text"] for cell in grid[last_hdr_row]]

    # Row header lookup: row_idx -> text
    row_header_by_row = {}
    for c in cells:
        if c.get("row_header"):
            row_header_by_row[c["start_row_offset_idx"]] = c["text"]

    # Excluded rows: title + all header rows
    excluded = col_header_rows.copy()
    if title_row_idx is not None:
        excluded.add(title_row_idx)

    has_row_headers = bool(row_header_by_row)
    rows = []
    row_headers_list = []

    for row_idx in range(num_rows):
        if row_idx in excluded:
            continue
        row_data = [cell["text"] for cell in grid[row_idx]]
        # Skip empty rows
        if all(t == "" for t in row_data):
            continue
        rows.append(row_data)
        if has_row_headers:
            row_headers_list.append(row_header_by_row.get(row_idx, ""))

    row_headers = row_headers_list if has_row_headers else None
    return col_headers, row_headers, rows


def _tables_content_equal(rows1, col_headers1, rows2, col_headers2):
    # Compare col_headers
    if (col_headers1 is None) != (col_headers2 is None):
        return False
    if col_headers1 is not None:
        if len(col_headers1) != len(col_headers2):
            return False
        if any(
            _normalize_cell(a) != _normalize_cell(b)
            for a, b in zip(col_headers1, col_headers2)
        ):
            return False
    # Compare rows
    if len(rows1) != len(rows2):
        return False
    for r1, r2 in zip(rows1, rows2):
        if len(r1) != len(r2):
            return False
        if any(
            _normalize_cell(a) != _normalize_cell(b) for a, b in zip(r1, r2)
        ):
            return False
    return True


def _deduplicate_within_book(raw_tables):
    """
    Returns (unique, conflicts, dupe_count) where:
    - unique: list of non-conflicting tables
    - conflicts: list of {'norm_title': str, 'versions': [table, ...]} dicts
    - dupe_count: number of tables silently skipped (identical content)
    """
    seen = {}  # normalized_title -> first table_dict
    unique = []
    conflict_norms = set()
    conflicts_dict = {}
    dupe_count = 0

    for table in raw_tables:
        norm = _normalize_title(table["title"])

        if norm not in seen:
            seen[norm] = table
            unique.append(table)
        elif norm in conflict_norms:
            # Already a known conflict: check if this version is identical to first
            first = conflicts_dict[norm][0]
            if _tables_content_equal(
                first["rows"], first["col_headers"],
                table["rows"], table["col_headers"],
            ):
                dupe_count += 1
            else:
                conflicts_dict[norm].append(table)
        else:
            existing = seen[norm]
            if _tables_content_equal(
                existing["rows"], existing["col_headers"],
                table["rows"], table["col_headers"],
            ):
                dupe_count += 1
            else:
                # New conflict: remove first occurrence from unique
                unique.remove(existing)
                conflict_norms.add(norm)
                conflicts_dict[norm] = [existing, table]

    conflict_list = [
        {"norm_title": k, "versions": v} for k, v in conflicts_dict.items()
    ]
    return unique, conflict_list, dupe_count


def _resolve_conflicts(conflicts):
    """Interactively resolve conflicts. Returns list of tables to keep."""
    kept = []
    for conflict in conflicts:
        versions = conflict["versions"]
        title = versions[0]["title"]
        print(f'\nConflict: "{title}" appears on multiple pages with different content.')
        for i, v in enumerate(versions, 1):
            r = len(v["rows"])
            c = len(v["col_headers"]) if v["col_headers"] else 0
            print(f"  [{i}] page {v['page']}  — {r} rows x {c} cols")
        choices = "/".join(str(i) for i in range(1, len(versions) + 1))
        prompt = f"Keep which? [{choices}/both/skip]: "
        response = input(prompt).strip().lower()
        if response == "both":
            kept.extend(versions)
        elif response == "skip":
            pass
        else:
            try:
                idx = int(response) - 1
                if 0 <= idx < len(versions):
                    kept.append(versions[idx])
            except ValueError:
                pass
    return kept


def _assign_filenames(tables):
    """Sort tables by page and assign table-pNNN-SS.json filenames in place."""
    tables.sort(key=lambda t: t["page"])
    page_seqs = {}
    for table in tables:
        page = table["page"]
        seq = page_seqs.get(page, 0) + 1
        page_seqs[page] = seq
        table["filename"] = f"table-p{page:03d}-{seq:02d}.json"


def _load_json(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def _save_json(data, path: Path):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def _source_sort_key(source: str) -> int:
    m = re.search(r"gcp-rmu-(\d+)", source)
    return int(m.group(1)) if m else 0


def _update_cross_index(output_dir: Path, source: str, book_tables: list):
    index_path = output_dir / "index.json"

    if index_path.exists():
        cross_index = _load_json(index_path)
    else:
        cross_index = {"tables": []}

    # Remove all entries where any version belongs to current source
    cross_index["tables"] = [
        entry
        for entry in cross_index["tables"]
        if not any(v["source"] == source for v in entry.get("versions", []))
    ]

    # Build lookup by normalized_title for existing entries
    entries_by_norm = {entry["normalized_title"]: entry for entry in cross_index["tables"]}

    # Add new entries from book_tables
    for table in book_tables:
        norm = _normalize_title(table["title"])
        version = {
            "source": source,
            "file": f"{source}/{table['filename']}",
            "page": table["page"],
            "title": table["title"],
        }
        if norm in entries_by_norm:
            entries_by_norm[norm]["versions"].append(version)
        else:
            entry = {
                "normalized_title": norm,
                "versions": [version],
            }
            entries_by_norm[norm] = entry
            cross_index["tables"].append(entry)

    # Set canonical = version from highest gcp-rmu-NNN source
    for entry in cross_index["tables"]:
        versions = entry["versions"]
        canonical_v = max(versions, key=lambda v: _source_sort_key(v["source"]))
        entry["canonical"] = {
            "source": canonical_v["source"],
            "file": canonical_v["file"],
        }

    _save_json(cross_index, index_path)


# ---------------------------------------------------------------------------
# Main handler
# ---------------------------------------------------------------------------


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
