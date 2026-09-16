"""Template tables must reach the chapter writer instead of being dropped."""

import asyncio
from pathlib import Path

from app.reporting.chapter_writer_agent import ChapterWriterAgent
from app.reporting.template_parser import ReportTemplateParser, table_markdown

EXAMPLE_DOCX = Path(__file__).resolve().parents[1] / "example" / "report_template.docx"

MARKDOWN_TEMPLATE = """# 经营分析报告

## 一、客户交易明细

本章展示交易明细。

| 客户名称 | 交易日期 | 区域 | 交易金额 |
| --- | --- | --- | --- |
| {{客户名称}} | {{交易日期}} | {{区域}} | {{交易金额}} |

## 二、说明
说明正文
""".encode()


def parse(filename: str, content: bytes, content_type: str | None = None):
    return ReportTemplateParser().parse("t", filename, content, content_type)


def table_blocks(section):
    return [block for block in section.template_blocks if block["type"] == "table"]


def test_docx_table_survives_parsing():
    template = parse("report_template.docx", EXAMPLE_DOCX.read_bytes())
    section = next(item for item in template.sections if "交易明细" in item.title)

    tables = table_blocks(section)
    assert len(tables) == 1
    assert tables[0]["header"] == ["客户名称", "交易日期", "区域", "交易金额"]
    assert tables[0]["rows"] == [["{{客户名称}}", "{{交易日期}}", "{{区域}}", "{{交易金额}}"]]


def test_docx_table_is_rendered_into_the_text_the_model_reads():
    template = parse("report_template.docx", EXAMPLE_DOCX.read_bytes())
    section = next(item for item in template.sections if "交易明细" in item.title)

    assert "| 客户名称 | 交易日期 | 区域 | 交易金额 |" in section.template_text
    assert "{{交易金额}}" in section.template_text


def test_markdown_pipe_table_survives_parsing():
    template = parse("t.md", MARKDOWN_TEMPLATE, "text/markdown")
    section = next(item for item in template.sections if "交易明细" in item.title)

    tables = table_blocks(section)
    assert len(tables) == 1
    assert tables[0]["header"] == ["客户名称", "交易日期", "区域", "交易金额"]
    # The separator row is structure, not data.
    assert tables[0]["rows"] == [["{{客户名称}}", "{{交易日期}}", "{{区域}}", "{{交易金额}}"]]
    # Text around the table is still ordinary paragraph content.
    assert any(block["type"] == "paragraph" for block in section.template_blocks)


def test_a_table_does_not_leak_into_the_next_section():
    template = parse("t.md", MARKDOWN_TEMPLATE, "text/markdown")
    section = next(item for item in template.sections if item.title == "二、说明")
    assert table_blocks(section) == []


def test_ragged_rows_are_padded_to_the_header_width():
    assert table_markdown(["a", "b", "c"], [["1"]]) == (
        "| a | b | c |\n| --- | --- | --- |\n| 1 |  |  |"
    )


def test_the_writer_is_told_to_keep_tables_inside_content():
    prompt = ChapterWriterAgent._composition_system_prompt()
    # A table returned in its own field would be silently discarded by the
    # renderer, so the prompt must not offer that option.
    assert "tables" not in prompt
    assert "Markdown" in prompt and "content 之外的字段会丢失" in prompt
    assert "返回 JSON：status、content、assumptions、questions。" in prompt


def test_the_writer_is_told_not_to_narrate_its_own_instructions():
    prompt = ChapterWriterAgent._composition_system_prompt()
    # assumptions is printed in the report, so it must not echo the prompt.
    assert "不要复述本提示词" in prompt


def test_the_writer_is_told_to_name_the_metric_it_is_missing():
    prompt = ChapterWriterAgent._composition_system_prompt()
    # Missing data must become a named question, not a hedge in the prose.
    assert "metric" in prompt and "expected" in prompt
    assert "findings 里已经给出的指标不得再声称缺失" in prompt


def test_narrative_chapters_are_not_expected_to_demand_data():
    prompt = ChapterWriterAgent._composition_system_prompt()
    # The plan already decided which chapters carry metrics; one that carries
    # none must not stall the run asking for data it was never meant to use.
    assert "metrics 为空时" in prompt
    assert "不要因为缺数据而提问" in prompt


def test_the_writer_is_told_the_template_carries_no_usable_data():
    prompt = ChapterWriterAgent._composition_system_prompt()
    # A finished report used as a template must contribute structure only:
    # its figures and its conclusions both belong to the previous period.
    assert "属于历史期间" in prompt
    assert "不得引用、不得沿用" in prompt
    assert "都必须整行替换为本期数据" in prompt


def test_the_metric_prompt_hands_every_calculation_to_the_tool():
    prompt = ChapterWriterAgent._metric_system_prompt()
    # Adding six monthly figures up in its head is where the model lost a
    # customer, so the arithmetic is the tool's, not the model's.
    assert "aggregate_dataset" in prompt
    assert "你不做任何算术" in prompt
    assert "count_distinct" in prompt
    # Free-form SQL would hand the calculation straight back.
    assert "SQL" not in prompt and "query_dataset" not in prompt
    # read_dataset survives for verbatim table rows and must stay out of totals.
    assert "任何汇总数字都不许由它得出" in prompt


def test_the_writer_must_quote_settled_values_instead_of_recomputing():
    prompt = ChapterWriterAgent._composition_system_prompt()
    # The prose and the table used to compute the same quantity separately and
    # disagree by 12%; both must now quote the value research settled.
    assert "findings" in prompt
    assert "不得重新计算" in prompt
    assert "不得让正文与表格对同一个量给出不同的值" in prompt


def test_the_metric_prompt_requires_a_value_not_rows():
    prompt = ChapterWriterAgent._metric_system_prompt()
    assert '\\"value\\"' in prompt or '"value"' in prompt
    assert "value 里的每一个数字都必须原样抄自工具返回" in prompt


def test_the_planner_is_told_not_to_inherit_the_template_period():
    from app.reporting.planner import ReportPlanner

    prompt = ReportPlanner._system_prompt()
    # A finished report used as a template carries last period's dates; taking
    # them literally regenerates last period's report.
    assert "绝不能沿用模板里的历史期间" in prompt
    # The period must come from the data's own values, not from a guess: the
    # planner previously invented "2025年度" for data that held two half-years.
    assert "value_enums" in prompt
    assert "最新的一个完整期间" in prompt


def test_the_metric_prompt_treats_the_report_period_as_given():
    prompt = ChapterWriterAgent._metric_system_prompt()
    # One metric burned its whole budget re-checking which months the period
    # covered instead of computing anything.
    assert "已经确定的报告期间" in prompt
    assert "不要为核实数据是否覆盖该期间而反复试探" in prompt


def test_the_planner_is_pointed_at_the_enumerated_values():
    from app.reporting.planner import ReportPlanner

    prompt = ReportPlanner._system_prompt()
    # Five sample rows off the top of one sheet all carried the same month and
    # hid both the data's reach and which dimension values existed.
    assert "value_enums" in prompt and "value_ranges" in prompt
    assert "全局维度的取值必须来自 value_enums" in prompt


def test_a_template_table_reaches_writing_as_columns_without_its_old_rows():
    """Last period's rows are answers to last period's question."""
    from app.core.reports import ReportTemplateSection
    from app.reporting.chapter_writer_agent import ChapterWriterAgent

    section = ReportTemplateSection(
        section_id="s1", title="区域分布", order=0,
        template_blocks=[
            {"type": "heading", "level": 1, "text": "区域分布"},
            {"type": "paragraph", "text": "按区域拆解。"},
            {"type": "table", "header": ["区域", "交易金额"],
             "rows": [["西南", "52,803,000"], ["华北", "40,025,000"]]},
        ],
    )
    blocks = ChapterWriterAgent._writable_blocks(section)

    table = next(b for b in blocks if b["type"] == "table")
    assert table["header"] == ["区域", "交易金额"]
    assert "rows" not in table
    assert table["example_row_count"] == 2
    # The heading is added by the renderer, so it is not part of the body.
    assert all(b["type"] != "heading" for b in blocks)


def test_metric_requests_share_a_stable_prefix_for_prompt_caching():
    """Cache hits are billed at a fraction of fresh input, and the prefix is
    only reusable when the varying field comes last."""
    import json

    from app.core.reports import (ChapterWriterInput, DataSourceMetadata,
                                  ReportGlobalContext, ReportTemplateSection)
    from app.reporting.chapter_writer_agent import ChapterWriterAgent

    inp = ChapterWriterInput(
        section=ReportTemplateSection(section_id="s1", title="一、经营概况", order=0),
        global_context=ReportGlobalContext(report_period="2026年上半年"),
        data_sources=[DataSourceMetadata(dataset_id="d", name="bank.xlsx", source_type="excel",
                                         sheets=[{"sheet_name": "月度汇总", "row_count": 48}])],
    )
    a = json.dumps(ChapterWriterAgent._metric_request("累计交易金额", inp), ensure_ascii=False)
    b = json.dumps(ChapterWriterAgent._metric_request("交易笔数", inp), ensure_ascii=False)

    shared = 0
    for x, y in zip(a, b):
        if x != y:
            break
        shared += 1
    assert shared / len(a) > 0.9
    assert list(json.loads(a))[-1] == "metric"
