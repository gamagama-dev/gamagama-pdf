import re
import sys
from pathlib import Path


def slugify(text, max_length=80):
    """Convert heading text to a filename-safe slug.

    Truncates at a hyphen boundary if the slug exceeds max_length.
    Pass max_length=None to disable truncation.
    """
    # Strip common chapter/section prefixes
    text = re.sub(
        r"^(chapter|part|section|appendix)\s+[\dA-Za-z]+[:\-\.\s]\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    text = text or "untitled"
    if max_length is not None and len(text) > max_length:
        text = text[:max_length].rsplit("-", 1)[0]
    return text


def split_markdown(text, level=2):
    """Split markdown text on headings of the given level.

    Returns a list of (heading_text, body) tuples. The first tuple has an
    empty heading string for any preamble content before the first heading.
    """
    pattern = re.compile(
        r"^(#{" + str(level) + r"})(?!#)\s+(.+)$", re.MULTILINE
    )
    sections = []
    last_end = 0
    last_heading = ""

    for match in pattern.finditer(text):
        body = text[last_end : match.start()]
        sections.append((last_heading, body))
        last_heading = match.group(2)
        last_end = match.end()

    # Remaining text after last heading
    sections.append((last_heading, text[last_end:]))
    return sections


def strip_image_placeholders(text):
    """Remove docling image placeholder lines and collapse excess blank lines."""
    text = re.sub(r"^!\[.*?\]\(image://.*?\)\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def handle_split_md(args):
    input_path = Path(args.input)
    output_dir = Path(args.output_dir)

    # Validate input exists
    if not input_path.is_file():
        print(f"Error: {input_path} not found or is not a file.", file=sys.stderr)
        sys.exit(1)

    text = input_path.read_text()
    sections = split_markdown(text, args.level)

    # Build list of (path, content) pairs
    files_to_write = []
    for i, (heading, body) in enumerate(sections):
        body = strip_image_placeholders(body).strip()
        if i == 0:
            if not body:
                continue
            filename = "00-preamble.md"
            content = body + "\n"
        else:
            slug = slugify(heading)
            if slug != slugify(heading, max_length=None):
                preview = heading.strip()[:80]
                print(
                    f"Warning: heading too long, truncated for filename "
                    f"(section {i}): \"{preview}...\"",
                    file=sys.stderr,
                )
            filename = f"{i:02d}-{slug}.md"
            hashes = "#" * args.level
            content = f"{hashes} {heading}\n\n{body}\n"
        files_to_write.append((output_dir / filename, content))

    # Batch overwrite check
    if not args.force:
        existing = [p for p, _ in files_to_write if p.exists()]
        if existing:
            for p in existing:
                print(f"Error: {p} already exists. Use --force to overwrite.", file=sys.stderr)
            sys.exit(1)

    # Write files
    output_dir.mkdir(parents=True, exist_ok=True)
    for path, content in files_to_write:
        path.write_text(content)

    # Summary
    print(f"Split {input_path.name} into {len(files_to_write)} files in {output_dir}/")
    for path, _ in files_to_write:
        print(f"  {path.name}")
