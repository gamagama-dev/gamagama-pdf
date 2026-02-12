from unittest.mock import MagicMock

import pytest

from gamagama.pdf.split_md import (
    slugify,
    split_markdown,
    strip_image_placeholders,
    handle_split_md,
)


# --- slugify tests ---


def test_slugify_basic():
    assert slugify("Core Rules") == "core-rules"


def test_slugify_chapter_prefix():
    assert slugify("Chapter 1: Core Rules") == "core-rules"


def test_slugify_chapter_prefix_dash():
    assert slugify("Chapter 3 - Combat") == "combat"


def test_slugify_part_roman_numeral():
    assert slugify("Part III: Advanced Topics") == "advanced-topics"


def test_slugify_section_prefix():
    assert slugify("Section 5: Magic") == "magic"


def test_slugify_appendix_prefix():
    assert slugify("Appendix A: Tables") == "tables"


def test_slugify_special_chars():
    assert slugify("Hello, World! (2024)") == "hello-world-2024"


def test_slugify_empty_result():
    assert slugify("Chapter 1:") == "untitled"


def test_slugify_truncates_long_heading():
    long_heading = " ".join(f"Word{i}" for i in range(50))
    slug = slugify(long_heading)
    assert len(slug) <= 80


def test_slugify_truncates_at_hyphen_boundary():
    # 'aaa-bbb-ccc-...' pattern where truncation should not leave a partial word
    long_heading = "-".join(["abcdefgh"] * 20)
    slug = slugify(long_heading)
    assert len(slug) <= 80
    assert not slug.endswith("-")


def test_slugify_no_truncation_when_short():
    result = slugify("Short Heading")
    assert result == "short-heading"
    # Same as unlimited
    assert result == slugify("Short Heading", max_length=None)


def test_slugify_max_length_none_disables_truncation():
    long_heading = " ".join(f"Word{i}" for i in range(50))
    slug = slugify(long_heading, max_length=None)
    assert len(slug) > 80


# --- split_markdown tests ---


def test_split_markdown_basic():
    text = "preamble\n\n## Chapter 1\n\nbody 1\n\n## Chapter 2\n\nbody 2\n"
    sections = split_markdown(text)
    assert len(sections) == 3
    assert sections[0][0] == ""
    assert "preamble" in sections[0][1]
    assert sections[1][0] == "Chapter 1"
    assert "body 1" in sections[1][1]
    assert sections[2][0] == "Chapter 2"
    assert "body 2" in sections[2][1]


def test_split_markdown_no_preamble():
    text = "## First\n\ncontent\n"
    sections = split_markdown(text)
    assert len(sections) == 2
    assert sections[0][0] == ""
    assert sections[0][1].strip() == ""
    assert sections[1][0] == "First"


def test_split_markdown_level_3():
    text = "## Keep Together\n\n### Sub A\n\nsub body\n\n### Sub B\n\nsub body 2\n"
    sections = split_markdown(text, level=3)
    assert len(sections) == 3
    assert sections[0][0] == ""
    assert "Keep Together" in sections[0][1]
    assert sections[1][0] == "Sub A"
    assert sections[2][0] == "Sub B"


def test_split_markdown_ignores_subheadings():
    text = "## Main\n\n### Sub\n\nbody\n"
    sections = split_markdown(text, level=2)
    assert len(sections) == 2
    assert sections[1][0] == "Main"
    assert "### Sub" in sections[1][1]


def test_split_markdown_no_headings():
    text = "Just some text\nwith no headings.\n"
    sections = split_markdown(text)
    assert len(sections) == 1
    assert sections[0][0] == ""
    assert "Just some text" in sections[0][1]


# --- strip_image_placeholders tests ---


def test_strip_image_placeholders_single():
    text = "before\n\n![img](image://abc123)\n\nafter\n"
    result = strip_image_placeholders(text)
    assert "image://" not in result
    assert "before" in result
    assert "after" in result


def test_strip_image_placeholders_multiple():
    text = "text\n\n![a](image://1)\n\n![b](image://2)\n\n![c](image://3)\n\nmore\n"
    result = strip_image_placeholders(text)
    assert "image://" not in result
    assert "text" in result
    assert "more" in result


def test_strip_image_placeholders_preserves_normal_images():
    text = "![photo](https://example.com/photo.jpg)\n"
    result = strip_image_placeholders(text)
    assert "![photo](https://example.com/photo.jpg)" in result


# --- handle_split_md tests ---


def test_handle_split_md_basic(tmp_path, capsys):
    """End-to-end: split a markdown file and verify output files."""
    md_content = (
        "# Title\n\nIntro paragraph.\n\n"
        "## Chapter 1: Core Rules\n\nRules content here.\n\n"
        "## Chapter 2: Equipment\n\nEquipment content.\n"
    )
    input_file = tmp_path / "book.md"
    input_file.write_text(md_content)
    output_dir = tmp_path / "output"

    args = MagicMock()
    args.input = str(input_file)
    args.output_dir = str(output_dir)
    args.level = 2
    args.force = False

    handle_split_md(args)

    assert (output_dir / "00-preamble.md").exists()
    assert (output_dir / "01-core-rules.md").exists()
    assert (output_dir / "02-equipment.md").exists()

    # Preamble contains the title
    preamble = (output_dir / "00-preamble.md").read_text()
    assert "Title" in preamble

    # Chapter files re-add the heading
    ch1 = (output_dir / "01-core-rules.md").read_text()
    assert ch1.startswith("## Chapter 1: Core Rules")
    assert "Rules content here." in ch1

    # Summary printed
    captured = capsys.readouterr()
    assert "3 files" in captured.out


def test_handle_split_md_input_not_found(tmp_path):
    args = MagicMock()
    args.input = str(tmp_path / "nonexistent.md")
    args.output_dir = str(tmp_path)
    args.level = 2
    args.force = False

    with pytest.raises(SystemExit) as exc_info:
        handle_split_md(args)
    assert exc_info.value.code == 1


def test_handle_split_md_warns_on_long_heading(tmp_path, capsys):
    """When a heading is too long and gets truncated, warn on stderr."""
    long_title = " ".join(f"Word{i}" for i in range(50))
    md_content = f"## {long_title}\n\ncontent\n"
    input_file = tmp_path / "book.md"
    input_file.write_text(md_content)
    output_dir = tmp_path / "output"

    args = MagicMock()
    args.input = str(input_file)
    args.output_dir = str(output_dir)
    args.level = 2
    args.force = False

    handle_split_md(args)

    captured = capsys.readouterr()
    assert "Warning" in captured.err
    assert "truncated" in captured.err
    # Warning should include a preview of the heading to help find it
    assert "Word0" in captured.err

    # File should still be created with a truncated name
    files = list(output_dir.glob("*.md"))
    assert len(files) == 1
    assert len(files[0].name) <= 255


def test_handle_split_md_refuses_overwrite(tmp_path):
    md_content = "## Chapter 1\n\ncontent\n"
    input_file = tmp_path / "book.md"
    input_file.write_text(md_content)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "01-chapter-1.md").write_text("old")

    args = MagicMock()
    args.input = str(input_file)
    args.output_dir = str(output_dir)
    args.level = 2
    args.force = False

    with pytest.raises(SystemExit) as exc_info:
        handle_split_md(args)
    assert exc_info.value.code == 1
