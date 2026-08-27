from __future__ import annotations

from io import BytesIO
from pathlib import Path
import re
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from ..core.reports import ReportTemplate, ReportTemplateSection


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

    def _parse_text(self, content: bytes) -> tuple[str | None, list[tuple[int, str, bool]]]:
        text = content.decode("utf-8-sig", errors="replace")
        blocks: list[tuple[int, str, bool]] = []
        title: str | None = None
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            markdown_heading = re.match(r"^(#{1,6})\s+(.+)$", line)
            numbered_heading = re.match(r"^((?:\d+\.)+|[一二三四五六七八九十]+[、.])\s*(.+)$", line)
            if markdown_heading:
                level = len(markdown_heading.group(1))
                value = markdown_heading.group(2).strip()
                if level == 1 and title is None:
                    title = value
                else:
                    blocks.append((level, value, True))
            elif numbered_heading:
                level = numbered_heading.group(1).count(".") or 1
                blocks.append((level, line, True))
            else:
                if title is None:
                    title = line
                blocks.append((1, line, False))
        return title, blocks

    def _parse_docx(self, content: bytes) -> tuple[str | None, list[tuple[int, str, bool]]]:
        try:
            with ZipFile(BytesIO(content)) as archive:
                document_xml = archive.read("word/document.xml")
        except (BadZipFile, KeyError) as exc:
            raise TemplateParseError("Invalid DOCX template") from exc

        namespace = {"w": self._word_namespace}
        root = ElementTree.fromstring(document_xml)
        title: str | None = None
        blocks: list[tuple[int, str, bool]] = []
        for paragraph in root.findall(".//w:body/w:p", namespace):
            value = "".join(node.text or "" for node in paragraph.findall(".//w:t", namespace)).strip()
            if not value:
                continue
            style_node = paragraph.find("./w:pPr/w:pStyle", namespace)
            style = ""
            if style_node is not None:
                style = style_node.attrib.get(f"{{{self._word_namespace}}}val", "")
            normalized_style = style.lower().replace(" ", "")
            heading_match = re.search(r"(?:heading|标题)([1-6])", normalized_style)
            if normalized_style in {"title", "标题"} and title is None:
                title = value
            elif heading_match:
                blocks.append((int(heading_match.group(1)), value, True))
            else:
                if title is None:
                    title = value
                blocks.append((1, value, False))
        return title, blocks

    @staticmethod
    def _build_sections(blocks: list[tuple[int, str, bool]]) -> list[ReportTemplateSection]:
        sections: list[ReportTemplateSection] = []
        current: ReportTemplateSection | None = None
        body: list[str] = []

        def finish_current() -> None:
            nonlocal current, body
            if current is not None:
                current.example_content = "\n".join(body).strip() or None
                current.template_text = "\n".join(
                    [current.title, *body]
                ).strip()
                current.template_blocks = [
                    {"type": "heading", "level": current.level, "text": current.title},
                    *({"type": "paragraph", "text": paragraph} for paragraph in body),
                ]
                sections.append(current)
            body = []

        for level, value, is_heading in blocks:
            if is_heading:
                finish_current()
                current = ReportTemplateSection(
                    section_id=f"section_{len(sections) + 1}",
                    title=value,
                    level=level,
                    order=len(sections),
                )
            else:
                if current is None:
                    current = ReportTemplateSection(
                        section_id="section_1",
                        title="正文",
                        level=1,
                        order=0,
                    )
                body.append(value)
        finish_current()

        if not sections:
            sections.append(ReportTemplateSection(section_id="section_1", title="正文", order=0))
        return sections
