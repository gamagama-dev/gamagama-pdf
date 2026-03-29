from io import BytesIO


def drop_redundant_bookmarks(toc):
    """Remove redundant bookmark entries from a PyMuPDF TOC.

    A leaf entry (one not followed by a deeper entry) is redundant if its page
    falls within the page span of a non-leaf sibling under the same parent.
    This catches index-style entries (e.g. "Sword, Long p.140") that point
    into the middle of a structural chapter.

    Two checks determine redundancy:
    - Bounded span: page falls in [start, next_non_leaf_sibling_page)
    - Content span: page falls in [start, max_descendant_page)

    Args:
        toc: List of [level, title, page] entries from doc.get_toc().

    Returns:
        Filtered TOC list with redundant entries removed.
    """
    if not toc:
        return []

    n = len(toc)

    # 1. Classify each entry as leaf or non-leaf
    is_leaf = [True] * n
    for i in range(n - 1):
        if toc[i + 1][0] > toc[i][0]:
            is_leaf[i] = False

    # 2. Build parent mapping via a stack
    parent = [-1] * n
    stack = []  # stack of indices
    for i in range(n):
        level = toc[i][0]
        while stack and toc[stack[-1]][0] >= level:
            stack.pop()
        if stack:
            parent[i] = stack[-1]
        stack.append(i)

    # 3a. Compute bounded_end for each non-leaf entry:
    #     page of the next non-leaf sibling (same parent) in TOC order
    bounded_end = [None] * n
    for i in range(n):
        if is_leaf[i]:
            continue
        p = parent[i]
        level = toc[i][0]
        for j in range(i + 1, n):
            if parent[j] == p and toc[j][0] == level and not is_leaf[j]:
                bounded_end[i] = toc[j][2]
                break

    # 3b. Compute max_desc_page for each non-leaf entry:
    #     max page among all descendants (propagated bottom-up)
    max_desc_page = [toc[i][2] for i in range(n)]
    for i in range(n - 1, -1, -1):
        if parent[i] != -1:
            p = parent[i]
            if max_desc_page[i] > max_desc_page[p]:
                max_desc_page[p] = max_desc_page[i]

    # 4. For each leaf, check if its page falls within a non-leaf sibling's span
    redundant = set()
    for i in range(n):
        if not is_leaf[i]:
            continue
        page = toc[i][2]
        p = parent[i]
        for j in range(n):
            if j == i or is_leaf[j] or parent[j] != p:
                continue
            start = toc[j][2]
            # Check bounded span [start, bounded_end)
            end = bounded_end[j]
            if end is not None and start <= page < end:
                redundant.add(i)
                break
            # Check content span [start, max_desc_page)
            mdp = max_desc_page[j]
            if start <= page < mdp:
                redundant.add(i)
                break

    # 5. Structural-leaf heuristic: at root level, if both leaf and
    #    non-leaf entries exist, leaf entries are index-style and redundant
    root_has_nonleaf = any(not is_leaf[i] for i in range(n) if parent[i] == -1)
    if root_has_nonleaf:
        for i in range(n):
            if parent[i] == -1 and is_leaf[i]:
                redundant.add(i)

    return [toc[i] for i in range(n) if i not in redundant]


def _prepare_heading_source(input_path, strategy, drop_empty=True, fuzzy_match=True,
                            conv_result=None):
    """Prepare the source argument for ResultPostprocessor based on strategy.

    Returns:
        (source, title_map) tuple where source is None for "none",
        BytesIO for "bookmarks"/"numbering", and title_map is a dict
        mapping normalized keys to original bookmark titles (empty for
        non-bookmarks strategies).
    """
    if strategy == "none":
        return (None, {})
    if strategy == "numbering":
        import fitz
        doc = fitz.open(str(input_path))
        doc.set_toc([])
        buf = BytesIO()
        doc.save(buf)
        doc.close()
        buf.seek(0)
        return (buf, {})
    # bookmarks strategy
    import fitz
    doc = fitz.open(str(input_path))
    toc = doc.get_toc()
    if drop_empty:
        toc = drop_redundant_bookmarks(toc)
    title_map = _build_title_map(toc)
    if fuzzy_match and conv_result is not None:
        toc = normalize_toc_titles(toc, conv_result)
    doc.set_toc(toc)
    buf = BytesIO()
    doc.save(buf)
    doc.close()
    buf.seek(0)
    return (buf, title_map)


def _build_title_map(toc):
    """Build a normalized-key → original-title map from a TOC.

    Used to restore clean bookmark casing after the postprocessor has
    matched headings using docling's (possibly garbled) content text.

    Args:
        toc: List of [level, title, page] entries (after redundancy filtering,
             before fuzzy normalization).

    Returns:
        Dict mapping normalize_key(title) → title.
    """
    import re

    def normalize_key(text):
        return re.sub(r"[^a-z0-9]", "", text.lower())

    result = {}
    for entry in toc:
        title = " ".join(entry[1].split())  # collapse newlines/whitespace
        key = normalize_key(title)
        if key and key not in result:
            result[key] = title
    return result


def restore_bookmark_casing(conv_result, title_map):
    """Replace heading text with original bookmark titles for clean casing.

    After the hierarchical postprocessor sets heading levels by matching
    TOC titles to docling content, the heading text may have garbled casing
    from docling's extraction (e.g. small-caps "avinaRcs"). This function
    replaces each SectionHeaderItem's text with the clean bookmark title.

    Args:
        conv_result: A docling ConversionResult with .document.texts.
        title_map: Dict from normalize_key(title) → original bookmark title.
    """
    import re
    from docling_core.types.doc.document import SectionHeaderItem

    def normalize_key(text):
        return re.sub(r"[^a-z0-9]", "", text.lower())

    for item in conv_result.document.texts:
        if isinstance(item, SectionHeaderItem):
            key = normalize_key(item.text)
            if key in title_map:
                item.text = title_map[key]
                item.orig = title_map[key]
            elif key:
                # Prefix match for truncated headings (e.g. docling extracts
                # "Part I:" but bookmark is "Part I: Character Law").
                # Use original text comparison to preserve word boundaries.
                heading_lower = item.text.strip().lower()
                candidates = [v for v in title_map.values()
                              if v.strip().lower().startswith(heading_lower)]
                if len(candidates) == 1:
                    item.text = candidates[0]
                    item.orig = candidates[0]


def normalize_toc_titles(toc, conv_result):
    """Rewrite TOC titles to match docling content text for fuzzy matching.

    Builds a case-insensitive lookup from the docling result's text items,
    then rewrites each TOC entry's title to the exact text found in the
    document content. This allows the hierarchical postprocessor's
    case-sensitive comparison to succeed.

    Args:
        toc: List of [level, title, page] entries.
        conv_result: A docling ConversionResult with .document.texts.

    Returns:
        Modified TOC list with titles rewritten where matches are found.
    """
    import re

    def normalize_key(text):
        return re.sub(r"[^a-z0-9]", "", text.lower())

    # Build lookup from document text items
    lookup = {}
    for text_item in conv_result.document.texts:
        orig = text_item.text
        key = normalize_key(orig)
        if key and key not in lookup:
            lookup[key] = orig

    # Rewrite TOC titles
    result = []
    for entry in toc:
        level, title, page = entry[0], entry[1], entry[2]
        key = normalize_key(title)
        if key in lookup:
            result.append([level, lookup[key], page])
        else:
            result.append([level, title, page])
    return result
