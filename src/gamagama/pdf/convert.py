import sys
from io import BytesIO
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

    # Infer heading hierarchy from PDF bookmarks, numbering, or font styles
    strategy = args.heading_strategy
    drop_empty = not getattr(args, "no_drop_empty_bookmarks", False)
    fuzzy_match = not getattr(args, "no_fuzzy_match", False)
    source, title_map = _prepare_heading_source(
        input_path, strategy,
        drop_empty=drop_empty, fuzzy_match=fuzzy_match,
        conv_result=result,
    )
    if source is not None:
        from hierarchical.postprocessor import ResultPostprocessor
        ResultPostprocessor(result, source=source).process()
    if title_map:
        restore_bookmark_casing(result, title_map)

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
