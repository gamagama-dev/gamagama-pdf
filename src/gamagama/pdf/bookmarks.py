import sys
from pathlib import Path

from gamagama.pdf.convert import drop_redundant_bookmarks


def format_toc_tree(toc):
    """Format a PyMuPDF TOC into an indented tree with dot-leaders.

    Args:
        toc: List of [level, title, page] entries from doc.get_toc().

    Returns:
        Formatted string with indented tree and summary line.
    """
    if not toc:
        return None

    kept = drop_redundant_bookmarks(toc)
    kept_set = {(e[0], e[1], e[2]) for e in kept}

    lines = []
    max_level = 0
    for entry in toc:
        level, title, page = entry[0], entry[1], entry[2]
        max_level = max(max_level, level)
        indent = "  " * (level - 1)
        label = f"L{level}"
        prefix = f"{indent}{label}  {title} "
        suffix = f" p.{page}"
        # Pad with dots to ~60 chars
        total = 60
        dots_needed = total - len(prefix) - len(suffix)
        if dots_needed < 2:
            dots_needed = 2
        dots = "." * dots_needed
        line = f"{prefix}{dots}{suffix}"
        if (level, title, page) not in kept_set:
            line += "  [redundant — dropped by default]"
        lines.append(line)

    lines.append("")
    lines.append(f"{max_level} levels, {len(toc)} entries")
    return "\n".join(lines)


def handle_bookmarks(args):
    input_path = Path(args.input)

    if not input_path.is_file():
        print(f"Error: {input_path} not found or is not a file.", file=sys.stderr)
        sys.exit(1)

    import fitz

    doc = fitz.open(str(input_path))
    toc = doc.get_toc()
    doc.close()

    if not toc:
        print("No bookmarks found in this PDF.")
        print("Consider using --heading-strategy numbering or none with gg-pdf convert.")
        return

    print(format_toc_tree(toc))
