"""
小规模测试数据生成脚本：5 客户 × 2 个月 = 10 行，金额用整数方便心算。

生成 3 个文件（写在 backend/example/）：
  - simple_test_report_template.md  报告模板（4 章）
  - simple_test_data.xlsx           两 sheet：RTL_CUST_AST_MGT_BAL / RTL_CUST_BEHAVIOR_TAG
  - simple_test_TESTING.md          各章参考 SQL + 标准答案，行内对照用

数据全部硬编码（不用随机），保证可复现、可心算验证。

用法：
  python backend/example/gen_simple_test.py
"""

from pathlib import Path
from openpyxl import Workbook
from openpyxl.utils import get_column_letter

HERE = Path(__file__).parent

# ============================================================
# 数据：5 客户 × 2 个月 = 10 行，金额全整数
# ============================================================

# 字段顺序（和 retail_deposit_small 一致）
AST_FIELDS = [
    "Statistics_Dt", "Cust_Id", "Cust_Open_Org_Id", "Belong_Org_Id",
    "Belong_Branch_Id", "Deposit_Bal", "Cust_Type", "Region",
    "Deposit_Product", "Avg_Bal", "Rate_Band",
]
TAG_FIELDS = ["Statistics_Dt", "Cust_Id", "Ever_Hold_Deposit_ind", "New_Fund_Flag"]

AST_HEADER_ZH = ["统计日期", "客户号", "开户机构", "归属机构", "归属分行",
                 "存款余额", "客户类型", "区域", "存款产品", "月日均余额", "利率档位"]
TAG_HEADER_ZH = ["统计日期", "客户号", "历史持有标志", "新进资金标志"]

# 10 行余额数据（金额全整数，方便心算）
ROWS_BAL = [
    # 2024 年 1 月，5 条
    {"Statistics_Dt": "2024-01-15", "Cust_Id": "CUST001", "Cust_Open_Org_Id": "ORG01",
     "Belong_Org_Id": "ORG01", "Belong_Branch_Id": "BR01", "Deposit_Bal": 1000000,
     "Cust_Type": "个人", "Region": "华东", "Deposit_Product": "活期",
     "Avg_Bal": 950000, "Rate_Band": "0.3%"},
    {"Statistics_Dt": "2024-01-15", "Cust_Id": "CUST002", "Cust_Open_Org_Id": "ORG02",
     "Belong_Org_Id": "ORG02", "Belong_Branch_Id": "BR02", "Deposit_Bal": 500000,
     "Cust_Type": "个人", "Region": "华南", "Deposit_Product": "定期3M",
     "Avg_Bal": 480000, "Rate_Band": "1.5%"},
    {"Statistics_Dt": "2024-01-15", "Cust_Id": "CUST003", "Cust_Open_Org_Id": "ORG01",
     "Belong_Org_Id": "ORG01", "Belong_Branch_Id": "BR01", "Deposit_Bal": 2000000,
     "Cust_Type": "对公", "Region": "华东", "Deposit_Product": "定期1Y",
     "Avg_Bal": 1900000, "Rate_Band": "2.0%"},
    {"Statistics_Dt": "2024-01-15", "Cust_Id": "CUST004", "Cust_Open_Org_Id": "ORG03",
     "Belong_Org_Id": "ORG03", "Belong_Branch_Id": "BR03", "Deposit_Bal": 50000,
     "Cust_Type": "个人", "Region": "华北", "Deposit_Product": "活期",
     "Avg_Bal": 48000, "Rate_Band": "0.3%"},
    {"Statistics_Dt": "2024-01-15", "Cust_Id": "CUST005", "Cust_Open_Org_Id": "ORG02",
     "Belong_Org_Id": "ORG02", "Belong_Branch_Id": "BR02", "Deposit_Bal": 800000,
     "Cust_Type": "同业", "Region": "华南", "Deposit_Product": "大额存单",
     "Avg_Bal": 780000, "Rate_Band": "2.5%"},
    # 2024 年 2 月，5 条
    {"Statistics_Dt": "2024-02-15", "Cust_Id": "CUST001", "Cust_Open_Org_Id": "ORG01",
     "Belong_Org_Id": "ORG01", "Belong_Branch_Id": "BR01", "Deposit_Bal": 1100000,
     "Cust_Type": "个人", "Region": "华东", "Deposit_Product": "活期",
     "Avg_Bal": 1050000, "Rate_Band": "0.3%"},
    {"Statistics_Dt": "2024-02-15", "Cust_Id": "CUST002", "Cust_Open_Org_Id": "ORG02",
     "Belong_Org_Id": "ORG02", "Belong_Branch_Id": "BR02", "Deposit_Bal": 480000,
     "Cust_Type": "个人", "Region": "华南", "Deposit_Product": "定期3M",
     "Avg_Bal": 470000, "Rate_Band": "1.5%"},
    {"Statistics_Dt": "2024-02-15", "Cust_Id": "CUST003", "Cust_Open_Org_Id": "ORG01",
     "Belong_Org_Id": "ORG01", "Belong_Branch_Id": "BR01", "Deposit_Bal": 2200000,
     "Cust_Type": "对公", "Region": "华东", "Deposit_Product": "定期1Y",
     "Avg_Bal": 2100000, "Rate_Band": "2.0%"},
    {"Statistics_Dt": "2024-02-15", "Cust_Id": "CUST004", "Cust_Open_Org_Id": "ORG03",
     "Belong_Org_Id": "ORG03", "Belong_Branch_Id": "BR03", "Deposit_Bal": 60000,
     "Cust_Type": "个人", "Region": "华北", "Deposit_Product": "活期",
     "Avg_Bal": 55000, "Rate_Band": "0.3%"},
    {"Statistics_Dt": "2024-02-15", "Cust_Id": "CUST005", "Cust_Open_Org_Id": "ORG02",
     "Belong_Org_Id": "ORG02", "Belong_Branch_Id": "BR02", "Deposit_Bal": 900000,
     "Cust_Type": "同业", "Region": "华南", "Deposit_Product": "大额存单",
     "Avg_Bal": 880000, "Rate_Band": "2.5%"},
]

# 10 行行为标签（和余额表逐行对齐，可按 Statistics_Dt + Cust_Id 内连接）
ROWS_TAG = [
    {"Statistics_Dt": "2024-01-15", "Cust_Id": "CUST001", "Ever_Hold_Deposit_ind": "YES", "New_Fund_Flag": "NO"},
    {"Statistics_Dt": "2024-01-15", "Cust_Id": "CUST002", "Ever_Hold_Deposit_ind": "NO",  "New_Fund_Flag": "NO"},
    {"Statistics_Dt": "2024-01-15", "Cust_Id": "CUST003", "Ever_Hold_Deposit_ind": "YES", "New_Fund_Flag": "YES"},
    {"Statistics_Dt": "2024-01-15", "Cust_Id": "CUST004", "Ever_Hold_Deposit_ind": None,  "New_Fund_Flag": "NO"},
    {"Statistics_Dt": "2024-01-15", "Cust_Id": "CUST005", "Ever_Hold_Deposit_ind": "YES", "New_Fund_Flag": "YES"},
    {"Statistics_Dt": "2024-02-15", "Cust_Id": "CUST001", "Ever_Hold_Deposit_ind": "YES", "New_Fund_Flag": "NO"},
    {"Statistics_Dt": "2024-02-15", "Cust_Id": "CUST002", "Ever_Hold_Deposit_ind": "NO",  "New_Fund_Flag": "NO"},
    {"Statistics_Dt": "2024-02-15", "Cust_Id": "CUST003", "Ever_Hold_Deposit_ind": "YES", "New_Fund_Flag": "YES"},
    {"Statistics_Dt": "2024-02-15", "Cust_Id": "CUST004", "Ever_Hold_Deposit_ind": "YES", "New_Fund_Flag": "NO"},
    {"Statistics_Dt": "2024-02-15", "Cust_Id": "CUST005", "Ever_Hold_Deposit_ind": "NO",  "New_Fund_Flag": "YES"},
]


# ============================================================
# 标准答案（手算，心算可验证）
# ============================================================
# 1月合计 = 1000000+500000+2000000+50000+800000 = 4350000
# 2月合计 = 1100000+480000+2200000+60000+900000 = 4740000
# 总合计 = 4350000+4740000 = 9090000
# 客户数(去重) = 5
# 户均(去重) = 9090000/5 = 1818000
# 环比2月 = (4740000-4350000)/4350000 = 8.9655% ≈ 8.97%
# 分行：BR01(华东) 4条 6400000；BR02(华南) 4条 2680000；BR03(华北) 2条 110000
# 客户类型：个人 6条 3190000；对公 2条 4200000；同业 2条 1700000
# 高净值(≥100万)：CUST001(1月100万✓,2月110万✓)、CUST003(1月200万✓,2月220万✓)
#   → 4条记录，2户，合计 6300000，占比 6300000/9090000 = 69.30%


def write_template(path: Path):
    """写报告模板：4 章。"""
    content = """# 零售存款小规模测试报告

本报告分析 2024 年 1 月至 2 月零售客户的存款规模、分行分布与月度趋势，报告期内统计日期为每月 15 日。

## 一、报告说明

说明本报告的分析口径与数据来源。本章为纯文字说明，不涉及任何统计指标。

数据取自零售客户资产管理余额表与零售客户行为标签表，两表以统计日期和客户号关联。

## 二、存款规模总览

概述报告期内零售客户的整体存款情况，需要说明：存款余额合计、客户数、户均存款余额。

## 三、分行存款分布

按客户归属分行编号拆解存款余额，说明各分行的客户数与存款余额，并指出存款余额最高的分行。

| 分行编号 | 客户数 | 存款余额（元） |
|---|---|---|
|  |  |  |

## 四、月度存款趋势

按统计日期逐月对比存款余额合计与客户数，说明报告期内的变动情况。

| 统计日期 | 客户数 | 存款余额（元） |
|---|---|---|
|  |  |  |
"""
    path.write_text(content, encoding="utf-8")


def write_xlsx(path: Path):
    """写 Excel：两 sheet，中文表头。"""
    wb = Workbook()
    # 第一张表：资产管理余额
    ws1 = wb.active
    ws1.title = "RTL_CUST_AST_MGT_BAL"
    ws1.append(AST_HEADER_ZH)
    for row in ROWS_BAL:
        ws1.append([row.get(f) for f in AST_FIELDS])
    _apply_col_widths(ws1, AST_HEADER_ZH)
    # 第二张表：行为标签
    ws2 = wb.create_sheet("RTL_CUST_BEHAVIOR_TAG")
    ws2.append(TAG_HEADER_ZH)
    for row in ROWS_TAG:
        ws2.append([row.get(f) for f in TAG_FIELDS])
    _apply_col_widths(ws2, TAG_HEADER_ZH)
    wb.save(path)


def _apply_col_widths(ws, headers):
    """根据表头长度给列设宽度。"""
    for idx, header in enumerate(headers, start=1):
        col = get_column_letter(idx)
        width = max(len(str(header)) * 2, 14)
        ws.column_dimensions[col].width = min(width, 32)
    ws.freeze_panes = "A2"


def write_testing(path: Path):
    """写 TESTING.md：各章参考 SQL + 标准答案。"""
    content = """# 小规模测试数据：参考 SQL 与标准答案

数据集：`simple_test`（5 客户 × 2 个月 = 10 行，金额全整数方便心算）

## 数据概况

- RTL_CUST_AST_MGT_BAL：10 行
- RTL_CUST_BEHAVIOR_TAG：10 行
- 两表按 (Statistics_Dt, Cust_Id) 内连接无损

## shape 约定

`value` 型按位置解析：最后一列是数值，前面所有列当维度。

## 一章（报告说明）

纯文字章节，不应产生追问。

## 二章（存款规模总览）

| 指标 | shape | 参考 SQL | 标准答案 |
|---|---|---|---|
| 存款余额合计 | value | `SELECT SUM(Deposit_Bal) FROM RTL_CUST_AST_MGT_BAL` | 9090000 |
| 客户数(去重) | value | `SELECT COUNT(DISTINCT Cust_Id) FROM RTL_CUST_AST_MGT_BAL` | 5 |
| 户均(按去重客户) | value | `SELECT ROUND(SUM(Deposit_Bal)/COUNT(DISTINCT Cust_Id),2) FROM RTL_CUST_AST_MGT_BAL` | 1818000 |

## 三章（分行存款分布）

| 指标 | shape | 参考 SQL |
|---|---|---|
| 分行分布 | table | `SELECT Belong_Branch_Id, COUNT(*) AS cnt, SUM(Deposit_Bal) AS bal FROM RTL_CUST_AST_MGT_BAL GROUP BY Belong_Branch_Id ORDER BY bal DESC` |

标准答案（3 个分行）：

| 分行 | 客户数 | 存款余额 |
|---|---|---|
| BR01 | 4 | 6300000 |
| BR02 | 4 | 2680000 |
| BR03 | 2 | 110000 |

存款余额最高的分行是 BR01。

## 四章（月度存款趋势）

| 指标 | shape | 参考 SQL |
|---|---|---|
| 月度趋势 | table | `SELECT Statistics_Dt, COUNT(*) AS cnt, SUM(Deposit_Bal) AS bal FROM RTL_CUST_AST_MGT_BAL GROUP BY Statistics_Dt ORDER BY Statistics_Dt` |

标准答案：

| 统计日期 | 客户数 | 存款余额 | 环比 |
|---|---|---|---|
| 2024-01-15 | 5 | 4350000 | — |
| 2024-02-15 | 5 | 4740000 | 8.97% |

环比 = (4740000-4350000)/4350000 = 8.9655% ≈ 8.97%

## 顺便可以验证的

- 高净值(≥100万)：CUST001(100万、110万)、CUST003(200万、220万) → 4 条记录、2 户、合计 6300000、占比 69.30%
- 客户类型分布：个人 6 条 3190000、对公 2 条 4200000、同业 2 条 1700000
- 持有标志(JOIN后)：YES 6 条、NO 3 条、空值 1 条
"""
    path.write_text(content, encoding="utf-8")


def main():
    template_path = HERE / "simple_test_report_template.md"
    xlsx_path = HERE / "simple_test_data.xlsx"
    testing_path = HERE / "simple_test_TESTING.md"

    write_template(template_path)
    write_xlsx(xlsx_path)
    write_testing(testing_path)

    print(f"[OK] 生成完成，共 3 个文件：")
    print(f"  - {template_path.name}")
    print(f"  - {xlsx_path.name}")
    print(f"  - {testing_path.name}")
    print(f"路径：{HERE}")
    print()
    print("数据概况：5 客户 × 2 个月 = 10 行，金额全整数")
    print("标准答案（心算可验证）：")
    print("  存款合计 = 9,090,000")
    print("  客户数 = 5")
    print("  户均 = 1,818,000")
    print("  1月 = 4,350,000 / 2月 = 4,740,000 / 环比 = 8.97%")
    print("  分行：BR01=6,400,000 / BR02=2,680,000 / BR03=110,000")


if __name__ == "__main__":
    main()
