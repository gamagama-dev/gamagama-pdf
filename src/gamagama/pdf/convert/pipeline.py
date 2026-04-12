import re
import sys
from pathlib import Path

from .headings import (
    _prepare_heading_source,
    restore_bookmark_casing,
)


def _repair_hierarchy_error(doc, error_str):
    """
    Parse a docling ValidationError about inconsistent table hierarchy and repair in-place.

    Docling emits messages like:
        "Document hierarchy is inconsistent. #/tables/20 has cell #/groups/0 with parent #/texts/3"

    For each such entry the referenced cell item has its parent ref corrected to point at
    the containing table.  Returns a list of human-readable repair descriptions (one per fix).
    """
    from docling_core.types.doc import RefItem

    pattern = r"(#/tables/\d+) has cell (#/\S+) with parent (#/\S+)"
    repairs = []
    for match in re.finditer(pattern, error_str):
        table_ref = match.group(1)   # e.g. "#/tables/20"
        cell_ref  = match.group(2)   # e.g. "#/groups/0"
        wrong_ref = match.group(3)   # e.g. "#/texts/3"

        parts = cell_ref.lstrip("#/").split("/")
        if len(parts) != 2:
            continue
        collection_name, idx_str = parts
        try:
            idx = int(idx_str)
        except ValueError:
            continue

        collection = getattr(doc, collection_name, None)
        if collection is None or idx >= len(collection):
            continue

        item = collection[idx]
        item.parent = RefItem(cref=table_ref)
        repairs.append(f"{cell_ref}: parent {wrong_ref} -> {table_ref}")

    return repairs


def _clear_inconsistent_tables(doc, error_str, description):
    """
    Parse a hierarchy inconsistency error, clear the cell data of offending tables,
    and warn.  This is a last-resort fallback — affected tables will be empty in output.
    """
    pattern = r"#/tables/(\d+) has cell"
    indices = sorted({int(m.group(1)) for m in re.finditer(pattern, error_str)})
    for idx in indices:
        if idx >= len(doc.tables):
            continue
        table = doc.tables[idx]
        if hasattr(table, "data") and table.data is not None:
            table.data.table_cells = []
            table.data.num_rows = 0
            table.data.num_cols = 0
        print(
            f"Warning: {description} — table #/tables/{idx} has an inconsistent "
            "hierarchy that could not be repaired; its data has been cleared.",
            file=sys.stderr,
        )


def _save_with_repair(save_fn, doc, description):
    """
    Call save_fn(); on a Pydantic ValidationError about inconsistent hierarchy,
    attempt to repair doc in-place and retry.  Continues as long as each attempt
    makes at least one new repair (progress check).  If no progress can be made,
    clears the offending tables as a last resort and retries.  Warns on stderr;
    never aborts the process — partial output is preferable to no output.
    """
    from pydantic import ValidationError

    all_repairs = []
    saved = False
    last_error_str = None

    # Retry as long as each pass makes at least one repair (i.e. is making progress).
    # If an attempt yields no new repairs we are stuck and fall through to the
    # table-clearing fallback.
    while True:
        try:
            save_fn()
            saved = True
            break
        except ValidationError as exc:
            error_str = str(exc)
            last_error_str = error_str
            if "hierarchy is inconsistent" not in error_str:
                raise
            repairs = _repair_hierarchy_error(doc, error_str)
            if not repairs:
                # No parent-ref fixes are possible; stop retrying.
                break
            all_repairs.extend(repairs)

    if not saved and last_error_str:
        # Last resort: clear the data of each offending table so the serializer
        # has nothing invalid to validate.  The table will appear empty in output.
        _clear_inconsistent_tables(doc, last_error_str, description)
        try:
            save_fn()
            saved = True
        except ValidationError as exc:
            print(
                f"Warning: {description} — document hierarchy could not be repaired "
                "even after clearing offending tables; this file was not written.",
                file=sys.stderr,
            )
            return  # Degrade gracefully — do not abort the whole run.

    if all_repairs:
        print(
            f"Warning: {len(all_repairs)} inconsistent table hierarchy reference(s) were "
            "repaired; affected table content may be imprecise.",
            file=sys.stderr,
        )
        for r in all_repairs:
            print(f"  {r}", file=sys.stderr)


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
        # The hierarchical library indexes result.pages as result.pages[page_no - 1],
        # assuming the PDF starts at page 1. When --pages specifies a range that
        # starts after page 1 (e.g. 26-50), result.pages only has the loaded pages
        # (indices 0-24), but prov.page_no values are absolute (26-50), causing an
        # IndexError. Prepend dummy Page objects so the absolute page_no maps to
        # the correct list index.
        page_start = page_range[0]
        if page_start > 1:
            from docling.datamodel.base_models import Page, PagePredictions
            dummy_pages = [
                Page(page_no=i, predictions=PagePredictions())
                for i in range(1, page_start)
            ]
            result.pages = dummy_pages + result.pages
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
    _save_with_repair(
        lambda: doc.save_as_markdown(md_path, image_mode=ImageRefMode.PLACEHOLDER),
        doc,
        f"saving {md_path.name}",
    )
    if md_path.exists():
        print(f"Written {md_path}")
    _save_with_repair(
        lambda: doc.save_as_json(json_path, image_mode=ImageRefMode.PLACEHOLDER),
        doc,
        f"saving {json_path.name}",
    )
    if json_path.exists():
        print(f"Written {json_path}")

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
