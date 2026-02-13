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


def filter_toc(toc, strategy):
    """Filter a PyMuPDF TOC list based on the heading strategy.

    Args:
        toc: List of [level, title, page] entries from doc.get_toc().
        strategy: "filtered" removes childless L1 entries; "numbering" empties entirely.

    Returns:
        Filtered TOC list.
    """
    if strategy == "numbering":
        return []
    if strategy == "filtered":
        filtered = []
        for i, entry in enumerate(toc):
            level = entry[0]
            if level == 1:
                # Keep L1 only if the next entry is a child (level > 1)
                next_entry = toc[i + 1] if i + 1 < len(toc) else None
                if next_entry is not None and next_entry[0] > 1:
                    filtered.append(entry)
            else:
                filtered.append(entry)
        return filtered
    return toc


def _prepare_heading_source(input_path, strategy):
    """Prepare the source argument for ResultPostprocessor based on strategy.

    Returns:
        str path for "auto", None for "none", BytesIO for "filtered"/"numbering".
    """
    if strategy == "auto":
        return str(input_path)
    if strategy == "none":
        return None
    # filtered or numbering: rewrite TOC in-memory
    import fitz

    doc = fitz.open(str(input_path))
    toc = doc.get_toc()
    doc.set_toc(filter_toc(toc, strategy))
    buf = BytesIO()
    doc.save(buf)
    doc.close()
    buf.seek(0)
    return buf


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
    source = _prepare_heading_source(input_path, strategy)
    if source is not None:
        from hierarchical.postprocessor import ResultPostprocessor
        ResultPostprocessor(result, source=source).process()

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
