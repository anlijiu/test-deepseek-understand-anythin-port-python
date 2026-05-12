"""Markdown parser tests — ported from markdown-parser.test.ts."""

from __future__ import annotations

from understand_anything.plugins.parsers.markdown import MarkdownParser


class TestMarkdownParser:
    """Tests for MarkdownParser."""

    def test_language_ids(self):
        """Parser reports correct language IDs."""
        parser = MarkdownParser()
        assert parser.name == "markdown-parser"
        assert parser.languages == ["markdown"]

    def test_extracts_sections_from_headings(self):
        """Extract heading sections from markdown."""
        content = """# Introduction
Some text here.

## Getting Started
More text.

### Prerequisites
Details.

## API Reference
API docs."""
        parser = MarkdownParser()
        result = parser.analyze_file("test.md", content)

        assert len(result.sections) == 4
        assert result.sections[0].name == "Introduction"
        assert result.sections[0].level == 1
        assert result.sections[1].name == "Getting Started"
        assert result.sections[1].level == 2
        assert result.sections[2].name == "Prerequisites"
        assert result.sections[2].level == 3
        assert result.sections[3].name == "API Reference"
        assert result.sections[3].level == 2
        # Verify line ranges
        assert result.sections[0].line_range[1] >= result.sections[0].line_range[0]
        assert result.sections[1].line_range[0] > result.sections[0].line_range[0]

    def test_section_line_range_extends_to_next_heading(self):
        """Section lineRange end extends to next heading (or EOF)."""
        content = "# Title\n\ncontent\n\n## Section 2\n"
        parser = MarkdownParser()
        result = parser.analyze_file("test.md", content)

        assert len(result.sections) == 2
        # First section should end at the line before second heading
        assert result.sections[0].line_range[1] == result.sections[1].line_range[0] - 1
        # Second section should reach EOF (line 5 with trailing newline)
        assert result.sections[1].line_range[1] >= 4

    def test_skips_headings_inside_fenced_code_blocks(self):
        """Headings inside fenced code blocks are ignored."""
        content = """# Real Section

```
# This is not a real heading
```

## Another Section

~~~
# Also not a heading inside tildes
~~~
"""
        parser = MarkdownParser()
        result = parser.analyze_file("test.md", content)

        assert len(result.sections) == 2
        assert result.sections[0].name == "Real Section"
        assert result.sections[1].name == "Another Section"

    def test_extracts_local_file_references(self):
        """Extract local file and image references from links."""
        content = """# Docs

See the [guide](./guide.md) for more.
![screenshot](./images/screen.png)
External: [google](https://google.com)
Other: [readme](../README.md)
"""
        parser = MarkdownParser()
        refs = parser.extract_references("docs/readme.md", content)

        # Should skip external URL
        local_refs = [r for r in refs if r.target != "https://google.com"]
        assert len(local_refs) >= 2

        targets = [r.target for r in refs]
        types = [r.reference_type for r in refs]
        assert "./guide.md" in targets
        assert "./images/screen.png" in targets
        assert "../README.md" in targets
        # Image should have "image" type
        img_ref = [r for r in refs if r.target == "./images/screen.png"][0]
        assert img_ref.reference_type == "image"

    def test_empty_fields_are_empty_lists(self):
        """Code-only fields are empty lists for non-code parsers."""
        parser = MarkdownParser()
        result = parser.analyze_file("test.md", "# Hello")
        assert result.functions == []
        assert result.classes == []
        assert result.imports == []
        assert result.exports == []
