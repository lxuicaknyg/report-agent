"""Generate a larger sample template and dataset for manual backend testing.

Deterministic: the same seed always produces the same files, so results are
comparable across runs.

    python example/make_sample_data.py
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

from openpyxl import Workbook

HERE = Path(__file__).resolve().parent
SEED = 20260101

REGIONS = {
    "华东": ["上海分行", "杭州分行", "南京分行"],
    "华南": ["广州分行", "深圳分行"],
    "华北": ["北京分行", "天津分行"],
    "西南": ["成都分行", "重庆分行"],
}
GRADES = ["A", "B", "C"]
PRODUCTS = ["流动资金贷款", "绿色信贷", "供应链金融", "票据贴现"]
INDUSTRIES = ["制造业", "批发零售", "新能源", "交通运输", "信息技术", "建筑业"]
GREEN_PROJECTS = ["光伏电站", "风电场", "污水处理", "节能改造", "新能源汽车"]

# 2025 与 2026 同期各半年，便于计算同比
MONTHS = [(2025, m) for m in range(1, 7)] + [(2026, m) for m in range(1, 7)]


def build_customers(rng: random.Random) -> list[dict]:
    customers = []
    for index in range(1, 61):
        region = rng.choice(list(REGIONS))
        branch = rng.choice(REGIONS[region])
        customers.append(
            {
                "客户编号": f"C{index:04d}",
                "客户名称": f"{region}{rng.choice(['泰和', '嘉信', '恒远', '联创', '瑞德', '博通'])}"
                f"{rng.choice(['科技', '实业', '能源', '物流', '建材'])}有限公司{index:02d}",
                "客户等级": rng.choices(GRADES, weights=[3, 5, 4])[0],
                "区域": region,
                "分行": branch,
                "所属行业": rng.choice(INDUSTRIES),
                "开户日期": date(rng.randint(2018, 2024), rng.randint(1, 12), rng.randint(1, 28)),
                "授信额度(万元)": rng.randrange(500, 12000, 100),
            }
        )
    return customers


def build_transactions(rng: random.Random, customers: list[dict]) -> list[dict]:
    rows = []
    for year, month in MONTHS:
        # 2026 年整体规模高于 2025 年同期，同比才有意义
        volume = 26 if year == 2026 else 22
        for _ in range(volume):
            customer = rng.choice(customers)
            day = rng.randint(1, 28)
            base = rng.randrange(80_000, 2_400_000, 1_000)
            growth = 1.18 if year == 2026 else 1.0
            rows.append(
                {
                    "交易日期": date(year, month, day),
                    "客户编号": customer["客户编号"],
                    "客户名称": customer["客户名称"],
                    "区域": customer["区域"],
                    "分行": customer["分行"],
                    "客户等级": customer["客户等级"],
                    "产品类型": rng.choices(PRODUCTS, weights=[4, 3, 2, 2])[0],
                    "交易金额(元)": round(base * growth, 2),
                    "交易笔数": rng.randint(1, 9),
                }
            )
    rows.sort(key=lambda item: (item["交易日期"], item["客户编号"]))
    return rows


def build_monthly_summary(transactions: list[dict]) -> list[dict]:
    buckets: dict[tuple[str, str], dict] = {}
    for row in transactions:
        key = (row["交易日期"].strftime("%Y-%m"), row["区域"])
        bucket = buckets.setdefault(
            key,
            {"统计月份": key[0], "区域": key[1], "交易金额(元)": 0.0, "交易笔数": 0, "客户": set(), "绿色信贷金额(元)": 0.0},
        )
        bucket["交易金额(元)"] += row["交易金额(元)"]
        bucket["交易笔数"] += row["交易笔数"]
        bucket["客户"].add(row["客户编号"])
        if row["产品类型"] == "绿色信贷":
            bucket["绿色信贷金额(元)"] += row["交易金额(元)"]
    result = []
    for bucket in buckets.values():
        result.append(
            {
                "统计月份": bucket["统计月份"],
                "区域": bucket["区域"],
                "交易金额(元)": round(bucket["交易金额(元)"], 2),
                "交易笔数": bucket["交易笔数"],
                "交易客户数": len(bucket["客户"]),
                "绿色信贷金额(元)": round(bucket["绿色信贷金额(元)"], 2),
            }
        )
    result.sort(key=lambda item: (item["统计月份"], item["区域"]))
    return result


def build_green_ledger(rng: random.Random, customers: list[dict]) -> list[dict]:
    rows = []
    for index in range(1, 81):
        customer = rng.choice(customers)
        amount = rng.randrange(200, 6000, 50)
        rows.append(
            {
                "项目编号": f"G{index:04d}",
                "客户名称": customer["客户名称"],
                "区域": customer["区域"],
                "分行": customer["分行"],
                "项目类型": rng.choice(GREEN_PROJECTS),
                "投放日期": date(rng.choice([2025, 2026]), rng.randint(1, 6), rng.randint(1, 28)),
                "投放金额(万元)": amount,
                "碳减排量(吨)": round(amount * rng.uniform(0.8, 2.6), 1),
            }
        )
    return rows


def write_excel(path: Path, sheets: dict[str, list[dict]]) -> None:
    workbook = Workbook()
    workbook.remove(workbook.active)
    for name, rows in sheets.items():
        sheet = workbook.create_sheet(name)
        if not rows:
            continue
        headers = list(rows[0])
        sheet.append(headers)
        for row in rows:
            sheet.append([row[header] for header in headers])
        for column, header in enumerate(headers, start=1):
            width = max(len(str(header)) * 2, 14)
            sheet.column_dimensions[sheet.cell(row=1, column=column).column_letter].width = min(width, 32)
    workbook.save(path)


# ── DOCX ────────────────────────────────────────────────────────────────────

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def paragraph(text: str, style: str | None = None) -> str:
    props = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f"<w:p>{props}<w:r><w:t xml:space=\"preserve\">{escape(text)}</w:t></w:r></w:p>"


def table(rows: list[list[str]]) -> str:
    borders = "".join(
        f'<w:{side} w:val="single" w:sz="4" w:space="0" w:color="999999"/>'
        for side in ("top", "left", "bottom", "right", "insideH", "insideV")
    )
    body = ""
    for cells in rows:
        tcs = "".join(
            f'<w:tc><w:tcPr><w:tcW w:w="2000" w:type="dxa"/></w:tcPr>{paragraph(cell)}</w:tc>'
            for cell in cells
        )
        body += f"<w:tr>{tcs}</w:tr>"
    return f'<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/><w:tblBorders>{borders}</w:tblBorders></w:tblPr>{body}</w:tbl>'


def blank_template_blocks() -> list[str]:
    """A skeleton template: instructions and {{placeholders}}, no real figures."""
    return [
        paragraph("公司金融业务经营分析报告（模板）", "Title"),
        paragraph(
            "本模板用于公司金融条线的半年度经营分析。报告需覆盖整体经营规模、区域与客户结构、"
            "绿色信贷专题以及风险情况，并与上年同期进行对比。所有金额单位为人民币元，"
            "除非章节中另有说明。"
        ),
        paragraph("一、经营概况", "Heading1"),
        paragraph("本章概述报告期内的整体经营规模、增长情况和主要驱动因素。"),
        paragraph("1.1 整体交易规模", "Heading2"),
        paragraph(
            "说明报告期内的交易金额、交易笔数和交易客户数，并与上年同期对比，"
            "给出同比增速和主要变化原因。"
        ),
        paragraph("1.2 区域分布", "Heading2"),
        paragraph("按区域拆解交易规模，指出贡献最高和增速最快的区域。"),
        table(
            [
                ["区域", "交易金额(元)", "交易笔数", "交易客户数", "同比增速"],
                ["{{区域}}", "{{交易金额}}", "{{交易笔数}}", "{{交易客户数}}", "{{同比增速}}"],
            ]
        ),
        paragraph("1.3 客户等级结构", "Heading2"),
        paragraph("按 A/B/C 客户等级说明客户数量和交易金额的分布及占比。"),
        paragraph("二、绿色信贷专题", "Heading1"),
        paragraph("本章聚焦绿色信贷业务的投放规模、结构和环境效益。"),
        paragraph("2.1 投放情况", "Heading2"),
        paragraph("说明绿色信贷的投放金额、在总交易金额中的占比及同比变化。"),
        paragraph("2.2 重点项目", "Heading2"),
        paragraph("列示报告期内投放金额较大的绿色信贷项目及其碳减排量。"),
        table(
            [
                ["项目编号", "客户名称", "项目类型", "投放金额(万元)", "碳减排量(吨)"],
                ["{{项目编号}}", "{{客户名称}}", "{{项目类型}}", "{{投放金额}}", "{{碳减排量}}"],
            ]
        ),
        paragraph("三、客户结构分析", "Heading1"),
        paragraph("从行业和分行两个维度分析客户结构，指出集中度风险。"),
        table(
            [
                ["所属行业", "客户数", "授信额度合计(万元)", "交易金额(元)"],
                ["{{所属行业}}", "{{客户数}}", "{{授信额度合计}}", "{{交易金额}}"],
            ]
        ),
        paragraph("四、资产质量", "Heading1"),
        paragraph(
            "说明报告期末的不良贷款余额、不良率和关注类贷款余额，并与上年同期对比，"
            "分析资产质量变化趋势。"
        ),
        paragraph("五、数据来源说明", "Heading1"),
        paragraph("说明本报告使用的数据来源、统计口径和数据截止时间。"),
    ]


def write_docx(path: Path, blocks: list[str]) -> None:
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{W_NS}"><w:body>{"".join(blocks)}'
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/></w:sectPr></w:body></w:document>'
    )

    styles = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:styles xmlns:w="{W_NS}">'
        + "".join(
            f'<w:style w:type="paragraph" w:styleId="{style_id}">'
            f'<w:name w:val="{name}"/>'
            f'<w:pPr><w:outlineLvl w:val="{level}"/></w:pPr>'
            f'<w:rPr><w:b/><w:sz w:val="{size}"/></w:rPr></w:style>'
            for style_id, name, level, size in [
                ("Title", "Title", 0, 40),
                ("Heading1", "heading 1", 0, 32),
                ("Heading2", "heading 2", 1, 28),
                ("Heading3", "heading 3", 2, 24),
            ]
        )
        + "</w:styles>"
    )

    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
        "</Types>"
    )

    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        "</Relationships>"
    )

    doc_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        "</Relationships>"
    )

    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("word/document.xml", document)
        archive.writestr("word/styles.xml", styles)
        archive.writestr("word/_rels/document.xml.rels", doc_rels)


def _fmt(value: float) -> str:
    return f"{value:,.0f}"


def build_history_report(transactions: list[dict], customers: list[dict]) -> list[str]:
    """A finished 2025 H1 report, to be reused as a template for a later period.

    Real templates are often last period's approved report rather than a
    skeleton: every figure is filled in and there is not a placeholder in sight.
    The numbers here are computed from the same dataset, so the historical
    narrative is internally consistent and any figure that survives into a new
    report is unambiguously a copy.
    """
    history = [row for row in transactions if row["交易日期"].year == 2025]
    total = sum(row["交易金额(元)"] for row in history)
    deals = sum(row["交易笔数"] for row in history)
    clients = len({row["客户编号"] for row in history})
    green = sum(row["交易金额(元)"] for row in history if row["产品类型"] == "绿色信贷")

    by_region: dict[str, dict] = {}
    for row in history:
        bucket = by_region.setdefault(row["区域"], {"amount": 0.0, "deals": 0, "clients": set()})
        bucket["amount"] += row["交易金额(元)"]
        bucket["deals"] += row["交易笔数"]
        bucket["clients"].add(row["客户编号"])
    ranked = sorted(by_region.items(), key=lambda item: item[1]["amount"], reverse=True)

    by_grade: dict[str, dict] = {}
    grade_of = {c["客户编号"]: c["客户等级"] for c in customers}
    for row in history:
        bucket = by_grade.setdefault(grade_of[row["客户编号"]], {"amount": 0.0, "clients": set()})
        bucket["amount"] += row["交易金额(元)"]
        bucket["clients"].add(row["客户编号"])

    top_region, top_stats = ranked[0]
    return [
        paragraph("公司金融业务经营分析报告（2025年上半年）", "Title"),
        paragraph(
            f"2025年上半年，公司金融条线累计交易金额 {_fmt(total)} 元，交易 {deals} 笔，"
            f"交易客户 {clients} 户。业务保持平稳，{top_region}继续为第一大贡献区域。"
            "本报告数据截至 2025 年 6 月 30 日。"
        ),
        paragraph("一、经营概况", "Heading1"),
        paragraph(
            f"报告期内整体交易规模 {_fmt(total)} 元，较上年同期基本持平；交易笔数 {deals} 笔，"
            f"户均交易金额约 {_fmt(total / max(clients, 1))} 元。业务增长主要由流动资金贷款和绿色信贷带动。"
        ),
        paragraph("1.1 整体交易规模", "Heading2"),
        paragraph(
            f"上半年累计交易金额 {_fmt(total)} 元，其中绿色信贷 {_fmt(green)} 元，"
            f"占比 {green / total * 100:.1f}%。交易客户 {clients} 户，客户覆盖面较上年同期略有扩大。"
        ),
        paragraph("1.2 区域分布", "Heading2"),
        paragraph(
            f"从区域看，{top_region}交易金额 {_fmt(top_stats['amount'])} 元，"
            f"占全条线 {top_stats['amount'] / total * 100:.1f}%，居首位；"
            f"{ranked[-1][0]}规模最小，为 {_fmt(ranked[-1][1]['amount'])} 元。"
        ),
        table(
            [["区域", "交易金额(元)", "交易笔数", "交易客户数", "占比"]]
            + [
                [
                    region,
                    _fmt(stats["amount"]),
                    str(stats["deals"]),
                    str(len(stats["clients"])),
                    f"{stats['amount'] / total * 100:.1f}%",
                ]
                for region, stats in ranked
            ]
        ),
        paragraph("1.3 客户等级结构", "Heading2"),
        paragraph(
            "、".join(
                f"{grade} 级客户 {len(stats['clients'])} 户、交易金额 {_fmt(stats['amount'])} 元"
                for grade, stats in sorted(by_grade.items())
            )
            + "。客户结构以 A、B 级为主，整体质量稳定。"
        ),
        paragraph("二、绿色信贷专题", "Heading1"),
        paragraph(
            f"上半年绿色信贷投放 {_fmt(green)} 元，占全部交易金额 {green / total * 100:.1f}%，"
            "重点投向光伏电站和污水处理项目，环境效益显著。"
        ),
        paragraph("2.1 投放情况", "Heading2"),
        paragraph(
            f"绿色信贷累计投放 {_fmt(green)} 元，较上年同期增长明显，"
            "在总交易金额中的占比持续提升，已成为公司金融重要增长点。"
        ),
        paragraph("2.2 重点项目", "Heading2"),
        paragraph("上半年投放金额较大的绿色信贷项目如下，合计碳减排量超过 8 万吨。"),
        table(
            [
                ["项目编号", "客户名称", "项目类型", "投放金额(万元)", "碳减排量(吨)"],
                ["G0007", "华东嘉信能源有限公司07", "光伏电站", "5,800", "12,460.0"],
                ["G0021", "华南恒远实业有限公司21", "污水处理", "4,150", "8,930.5"],
                ["G0044", "华北瑞德科技有限公司44", "风电场", "3,600", "9,120.0"],
            ]
        ),
        paragraph("三、客户结构分析", "Heading1"),
        paragraph(
            "从行业看，制造业和新能源客户合计贡献超过六成交易金额，行业集中度偏高；"
            "从分行看，上海分行和深圳分行为主要贡献单位，需关注单一分行依赖风险。"
        ),
        table(
            [
                ["所属行业", "客户数", "授信额度合计(万元)", "交易金额(元)"],
                ["制造业", "18", "96,400", "58,420,000"],
                ["新能源", "12", "71,300", "41,860,000"],
                ["批发零售", "11", "42,800", "23,150,000"],
            ]
        ),
        paragraph("四、资产质量", "Heading1"),
        paragraph(
            "报告期末不良贷款余额 1.24 亿元，不良率 1.08%，较上年末下降 0.12 个百分点；"
            "关注类贷款余额 3.86 亿元，占比 3.36%。资产质量整体可控。"
        ),
        paragraph("五、数据来源说明", "Heading1"),
        paragraph(
            "本报告交易数据取自公司金融业务系统，客户信息取自客户主数据平台，"
            "绿色信贷数据取自绿色金融台账，数据截止 2025 年 6 月 30 日。"
        ),
    ]


def main() -> None:
    rng = random.Random(SEED)
    customers = build_customers(rng)
    transactions = build_transactions(rng, customers)
    sheets = {
        "交易明细": transactions,
        "客户主数据": customers,
        "月度汇总": build_monthly_summary(transactions),
        "绿色信贷台账": build_green_ledger(rng, customers),
    }
    excel_path = HERE / "sample_bank_data.xlsx"
    docx_path = HERE / "sample_report_template.docx"
    history_path = HERE / "sample_history_report.docx"
    write_excel(excel_path, sheets)
    write_docx(docx_path, blank_template_blocks())
    write_docx(history_path, build_history_report(transactions, customers))
    for name, rows in sheets.items():
        print(f"  {name}: {len(rows)} 行 × {len(rows[0])} 列")
    print(f"生成 {excel_path.name} / {docx_path.name} / {history_path.name}")


if __name__ == "__main__":
    main()
