from .extraction import _normalize_title, _normalize_cell


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
