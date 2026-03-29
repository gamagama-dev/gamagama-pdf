import bisect
import re


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
