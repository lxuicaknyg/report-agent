from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
import re
from typing import Literal
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from ..core.reports import ReportTemplate, ReportTemplateSection


@dataclass(frozen=True)
class _Block:
    """One parsed piece of a template, in document order.

    Tables are kept as structured cells rather than flattened text so the
    chapter writer receives the template's own table layout to reproduce.
    """

    kind: Literal["heading", "paragraph", "table"]
    level: int = 1
    text: str = ""
    header: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)


def table_markdown(header: list[str], rows: list[list[str]]) -> str:
    """Render parsed table cells as a Markdown table."""
    width = max([len(header), *(len(row) for row in rows)] or [0])
    if width == 0:
        return ""

    def line(cells: list[str]) -> str:
        padded = [*cells, *([""] * (width - len(cells)))]
        return "| " + " | ".join(padded) + " |"

    return "\n".join([line(header), "| " + " | ".join(["---"] * width) + " |", *(line(row) for row in rows)])


class TemplateParseError(ValueError):
    pass


class ReportTemplateParser:
    """Parse an uploaded document into a report structure.

    The first implementation intentionally focuses on semantic structure. It
    extracts titles, headings and example paragraphs while leaving precise
    style cloning to a future DOCX renderer.
    """

    _word_namespace = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

    def parse(
        self,
        template_id: str,
        filename: str,
        content: bytes,
        content_type: str | None = None,
    ) -> ReportTemplate:
        suffix = Path(filename).suffix.lower()
        if suffix == ".docx":
            title, blocks = self._parse_docx(content)
        elif suffix in {".md", ".markdown", ".txt"}:
            title, blocks = self._parse_text(content)
        else:
            raise TemplateParseError("Supported template formats are .docx, .md and .txt")

        sections = self._build_sections(blocks)
        return ReportTemplate(
            template_id=template_id,
            filename=filename,
            title=title or Path(filename).stem,
            content_type=content_type,
            sections=sections,
            assembly_rules={"preserve_section_order": True, "source_format": suffix.lstrip(".")},
            metadata={"paragraph_count": len(blocks)},
        )

    def _parse_text(self, content: bytes) -> tuple[str | None, list[_Block]]:
        lines = content.decode("utf-8-sig", errors="replace").splitlines()
        blocks: list[_Block] = []
        title: str | None = None
        index = 0
        while index < len(lines):
            line = lines[index].strip()
            if not line:
                index += 1
                continue

            table, consumed = self._read_markdown_table(lines, index)
            if table is not None:
                blocks.append(table)
                index += consumed
                continue

            markdown_heading = re.match(r"^(#{1,6})\s+(.+)$", line)
            numbered_heading = re.match(r"^((?:\d+\.)+|[一二三四五六七八九十]+[、.])\s*(.+)$", line)
            if markdown_heading:
                level = len(markdown_heading.group(1))
                value = markdown_heading.group(2).strip()
                if level == 1 and title is None:
                    title = value
                else:
                    blocks.append(_Block(kind="heading", level=level, text=value))
            elif numbered_heading:
                level = numbered_heading.group(1).count(".") or 1
                blocks.append(_Block(kind="heading", level=level, text=line))
            else:
                if title is None:
                    title = line
                blocks.append(_Block(kind="paragraph", text=line))
            index += 1
        return title, blocks

    @staticmethod
    def _read_markdown_table(lines: list[str], start: int) -> tuple[_Block | None, int]:
        """Read a pipe table at ``start``; returns the block and lines consumed."""
        def cells(raw: str) -> list[str]:
            return [cell.strip() for cell in raw.strip().strip("|").split("|")]

        first = lines[start].strip()
        separator = lines[start + 1].strip() if start + 1 < len(lines) else ""
        if not first.startswith("|") or not re.fullmatch(r"\|[\s:|-]+\|", separator or ""):
            return None, 0

        header = cells(first)
        rows: list[list[str]] = []
        index = start + 2
        while index < len(lines) and lines[index].strip().startswith("|"):
            rows.append(cells(lines[index]))
            index += 1
        return _Block(kind="table", header=header, rows=rows), index - start

    def _parse_docx(self, content: bytes) -> tuple[str | None, list[_Block]]:
        try:
            with ZipFile(BytesIO(content)) as archive:
                document_xml = archive.read("word/document.xml")
        except (BadZipFile, KeyError) as exc:
            raise TemplateParseError("Invalid DOCX template") from exc

        namespace = {"w": self._word_namespace}
        root = ElementTree.fromstring(document_xml)
        body = root.find("w:body", namespace)
        if body is None:
            return None, []

        title: str | None = None
        blocks: list[_Block] = []
        # Walk the body's own children in document order: a table is a sibling
        # of the paragraphs around it, not a paragraph, so iterating only w:p
        # drops it — and its cell text with it.
        for element in body:
            tag = element.tag.split("}")[-1]
            if tag == "tbl":
                table = self._read_docx_table(element, namespace)
                if table is not None:
                    blocks.append(table)
                continue
            if tag != "p":
                continue
            value = "".join(node.text or "" for node in element.findall(".//w:t", namespace)).strip()
            if not value:
                continue
            style_node = element.find("./w:pPr/w:pStyle", namespace)
            style = ""
            if style_node is not None:
                style = style_node.attrib.get(f"{{{self._word_namespace}}}val", "")
            normalized_style = style.lower().replace(" ", "")
            heading_match = re.search(r"(?:heading|标题)([1-6])", normalized_style)
            if normalized_style in {"title", "标题"} and title is None:
                title = value
            elif heading_match:
                blocks.append(_Block(kind="heading", level=int(heading_match.group(1)), text=value))
            else:
                if title is None:
                    title = value
                blocks.append(_Block(kind="paragraph", text=value))
        return title, blocks

    @staticmethod
    def _read_docx_table(table_element, namespace: dict[str, str]) -> _Block | None:
        rows: list[list[str]] = []
        for row in table_element.findall("./w:tr", namespace):
            cells = [
                "".join(node.text or "" for node in cell.findall(".//w:t", namespace)).strip()
                for cell in row.findall("./w:tc", namespace)
            ]
            if any(cells):
                rows.append(cells)
        if not rows:
            return None
        return _Block(kind="table", header=rows[0], rows=rows[1:])

    @staticmethod
    def _build_sections(blocks: list[_Block]) -> list[ReportTemplateSection]:
        sections: list[ReportTemplateSection] = []
        current: ReportTemplateSection | None = None
        body: list[_Block] = []

        def finish_current() -> None:
            nonlocal current, body
            if current is not None:
                rendered = [
                    table_markdown(item.header, item.rows) if item.kind == "table" else item.text
                    for item in body
                ]
                rendered = [text for text in rendered if text]
                current.example_content = "\n".join(rendered).strip() or None
                current.template_text = "\n".join([current.title, *rendered]).strip()
                current.template_blocks = [
                    {"type": "heading", "level": current.level, "text": current.title},
                    *(
                        {"type": "table", "header": item.header, "rows": item.rows}
                        if item.kind == "table"
                        else {"type": "paragraph", "text": item.text}
                        for item in body
                    ),
                ]
                sections.append(current)
            body = []

        for block in blocks:
            if block.kind == "heading":
                finish_current()
                current = ReportTemplateSection(
                    section_id=f"section_{len(sections) + 1}",
                    title=block.text,
                    level=block.level,
                    order=len(sections),
                )
            else:
                if current is None:
                    current = ReportTemplateSection(
                        section_id="section_1",
                        title="正文",
                        level=1,
                        order=0,
                        metadata={"preamble": True},
                    )
                body.append(block)
        finish_current()

        if not sections:
            sections.append(
                ReportTemplateSection(section_id="section_1", title="正文", order=0, metadata={"preamble": True})
            )
        return sections
