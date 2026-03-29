import json
import re
from pathlib import Path

from .extraction import _normalize_title


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


def _assign_filenames(tables):
    """Sort tables by page and assign table-pNNN-SS.json filenames in place."""
    tables.sort(key=lambda t: t["page"])
    page_seqs = {}
    for table in tables:
        page = table["page"]
        seq = page_seqs.get(page, 0) + 1
        page_seqs[page] = seq
        table["filename"] = f"table-p{page:03d}-{seq:02d}.json"


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
