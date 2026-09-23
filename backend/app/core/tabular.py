"""Read a table out of text a user pasted in.

When a chapter needs a list rather than a figure, the user either writes SQL or
pastes what they already have — a block copied out of a spreadsheet, a few
``指标：数值`` lines, a Markdown table from another document. This turns any of
those into the same ``columns``/``rows`` a SQL supplement produces, so the
chapter writer sees one shape regardless of where the data came from.

Parsing lives here, on its own, for two reasons: the preview the user checks
before submitting and the parse that actually lands in the report must be the
same code, and nothing here touches the model — a pasted table is read by
rules, so what the user saw is what gets recorded.
"""

from __future__ import annotations

import csv
import io
import re

from pydantic import BaseModel, Field

#: What a supplement may carry into a chapter prompt, matching the cap on a
#: SQL-supplied detail table.
MAX_ROWS = 100

#: ``指标：数值`` and its ASCII and full-width spellings. Anchored so a colon
#: inside the value (a time, a ratio written 1:2) does not split the line
#: twice.
_PAIR = re.compile(r"^\s*([^:：=\t]{1,80}?)\s*[:：=]\s*(.+?)\s*$")

#: Two or more spaces, which is how a pasted fixed-width block separates its
#: columns. A single space is left alone: metric names have spaces in them.
_GAP = re.compile(r"\s{2,}")

#: A Markdown table's rule row: |---|:--:|
_RULE = re.compile(r"^\s*\|?[\s:|-]+\|[\s:|-]*$")


class ParsedTable(BaseModel):
    """What a paste was read as, and anything the reader should know about it."""

    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, str]] = Field(default_factory=list)
    row_count: int = 0
    #: True when the paste held more rows than a supplement may carry.
    truncated: bool = False
    #: How the text was read — shown to the user, because "read as 指标/取值
    #: pairs" and "read as a tab-separated table" are different claims about
    #: what they pasted.
    format: str = ""
    warnings: list[str] = Field(default_factory=list)


class TableParseError(ValueError):
    """The text is not a table, with the reason phrased for the person who
    pasted it."""


def parse_table(text: str, max_rows: int = MAX_ROWS) -> ParsedTable:
    """Read ``text`` as a table.

    Recognised, in order: a Markdown table, tab-separated cells (what copying
    out of Excel produces), ``指标：数值`` lines, comma-separated cells, and
    columns separated by runs of spaces. The first row is the header in every
    form but the pairs one, which names its own two columns.
    """
    lines = [line for line in (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    lines = [line for line in lines if line.strip()]
    if not lines:
        raise TableParseError("没有可解析的内容，请粘贴明细数据")

    warnings: list[str] = []
    if any("|" in line for line in lines) and _looks_markdown(lines):
        header, records, label = _from_markdown(lines)
    elif any("\t" in line for line in lines):
        header, records = _split_on(lines, _tab_cells)
        label = "制表符分隔"
    elif all(_PAIR.match(line) for line in lines):
        header, records, label = _from_pairs(lines)
    elif _consistent(lines, _csv_cells):
        header, records = _split_on(lines, _csv_cells)
        label = "逗号分隔"
    elif _consistent(lines, _gap_cells):
        header, records = _split_on(lines, _gap_cells)
        label = "空格分隔"
    else:
        raise TableParseError(
            "认不出这段内容的表格结构。可以从 Excel 直接复制粘贴，"
            "或者每行写成「指标名：数值」，也支持 Markdown 表格和逗号分隔"
        )

    if not records:
        raise TableParseError("只读到了表头，没有数据行。第一行会被当作表头，请一并粘贴数据")

    columns = _name_columns(header)
    rows: list[dict[str, str]] = []
    ragged = 0
    for record in records:
        if len(record) != len(columns):
            ragged += 1
        cells = list(record[: len(columns)]) + [""] * max(0, len(columns) - len(record))
        rows.append({column: cells[index].strip() for index, column in enumerate(columns)})

    if ragged:
        warnings.append(
            f"有 {ragged} 行的列数与表头不一致，已按表头的 {len(columns)} 列对齐"
            "（多出的列被丢弃，缺少的列按空值处理），请检查预览"
        )
    truncated = len(rows) > max_rows
    if truncated:
        warnings.append(f"共 {len(rows)} 行，只会取前 {max_rows} 行写进报告")
        rows = rows[:max_rows]

    return ParsedTable(
        columns=columns,
        rows=rows,
        row_count=len(rows),
        truncated=truncated,
        format=label,
        warnings=warnings,
    )


def _looks_markdown(lines: list[str]) -> bool:
    """A Markdown table is a pipe table with a rule under its header."""
    return len(lines) >= 2 and bool(_RULE.match(lines[1])) and "|" in lines[0]


def _from_markdown(lines: list[str]) -> tuple[list[str], list[list[str]], str]:
    body = [line for index, line in enumerate(lines) if index != 1 and not _RULE.match(line)]
    cells = [_pipe_cells(line) for line in body]
    return cells[0], cells[1:], "Markdown 表格"


def _pipe_cells(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def _from_pairs(lines: list[str]) -> tuple[list[str], list[list[str]], str]:
    """``指标：数值`` lines, which is how several figures get supplied at once."""
    records = []
    for line in lines:
        match = _PAIR.match(line)
        assert match is not None  # guarded by the caller
        records.append([match.group(1).strip(), match.group(2).strip()])
    return ["指标", "取值"], records, "指标：数值"


def _tab_cells(line: str) -> list[str]:
    return line.split("\t")


def _csv_cells(line: str) -> list[str]:
    return next(csv.reader(io.StringIO(line)), [])


def _gap_cells(line: str) -> list[str]:
    return _GAP.split(line.strip())


def _consistent(lines: list[str], split) -> bool:
    """True when every line splits into the same number of cells, more than one.

    A paste where one line has three cells and the next has one is not a table
    in this format — it is more likely a different format read wrongly, so the
    caller should keep looking rather than produce a table nobody meant.
    """
    counts = {len(split(line)) for line in lines}
    return len(counts) == 1 and counts.pop() > 1


def _split_on(lines: list[str], split) -> tuple[list[str], list[list[str]]]:
    cells = [[cell.strip() for cell in split(line)] for line in lines]
    return cells[0], cells[1:]


def _name_columns(header: list[str]) -> list[str]:
    """Header cells as usable, distinct column names."""
    names: list[str] = []
    seen: dict[str, int] = {}
    for index, cell in enumerate(header, start=1):
        name = (cell or "").strip() or f"column_{index}"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 1
        names.append(name)
    return names
