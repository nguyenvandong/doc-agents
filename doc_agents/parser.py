from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO

from docx import Document
from docx.table import Table as DocxTable
from docx.text.paragraph import Paragraph
import mammoth


@dataclass(frozen=True)
class ParsedBlock:
    kind: str
    text: str
    markdown: str
    style_name: str | None = None


@dataclass(frozen=True)
class ParsedDocument:
    blocks: list[ParsedBlock]
    semantic_html: str
    mammoth_messages: list[str] = field(default_factory=list)


class DocxParser:
    def parse_bytes(self, payload: bytes) -> ParsedDocument:
        document = Document(BytesIO(payload))
        blocks: list[ParsedBlock] = []

        for block in document.iter_inner_content():
            if isinstance(block, Paragraph):
                text = block.text.strip()
                if not text:
                    continue
                blocks.append(
                    ParsedBlock(
                        kind="paragraph",
                        text=text,
                        markdown=text,
                        style_name=block.style.name if block.style is not None else None,
                    )
                )
            elif isinstance(block, DocxTable):
                markdown = self._table_to_markdown(block)
                blocks.append(
                    ParsedBlock(
                        kind="table",
                        text=markdown,
                        markdown=markdown,
                        style_name=None,
                    )
                )

        mammoth_result = mammoth.convert_to_html(BytesIO(payload))
        return ParsedDocument(
            blocks=blocks,
            semantic_html=mammoth_result.value,
            mammoth_messages=[str(message) for message in mammoth_result.messages],
        )

    def _table_to_markdown(self, table: DocxTable) -> str:
        rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
        if not rows:
            return ""

        column_count = max(len(row) for row in rows)
        normalized = [row + [""] * (column_count - len(row)) for row in rows]
        header = normalized[0]
        divider = ["---"] * column_count
        body = normalized[1:] or [[""] * column_count]

        lines = [
            self._markdown_row(header),
            self._markdown_row(divider),
        ]
        lines.extend(self._markdown_row(row) for row in body)
        return "\n".join(lines)

    @staticmethod
    def _markdown_row(cells: list[str]) -> str:
        return "| " + " | ".join(cells) + " |"
