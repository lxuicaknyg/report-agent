"""生成零售存款测试夹具：1 份正常数据 + 5 份另类（边界）数据。

每份数据输出 4 件套（写入 backend/example/）：
  - <name>_schema.sql          建库 + 建表 + INSERT（MySQL 语法）
  - <name>_data.xlsx           两 sheet：RTL_CUST_AST_MGT_BAL / RTL_CUST_BEHAVIOR_TAG
  - <name>_report_template.md  报告模板（6 章，章节里带派生计算要求）
  - <name>_TESTING.md          各章参考 SQL + 标准答案，行内对照用

参数化设计：改 NORMAL_CONFIG 或调用 gen_dataset(config) 可复用造中/大规模。

字段命名沿用 PascalCase + 下划线风格（如 Belong_Branch_Id）。
表结构扩展自 retail_deposit_schema.sql，保留两表设计语义：
  - RTL_CUST_AST_MGT_BAL 扩展 Cust_Type / Region / Deposit_Product / Avg_Bal / Rate_Band
  - RTL_CUST_BEHAVIOR_TAG 扩展 New_Fund_Flag

设计要点：
  - 正常数据 25 客户 × 12 月 = 300 行，二八分布 + 季节性 + 跨月趋势
  - 另类 A：全员零值/极端值（0、负数、10亿、6 位小数）
  - 另类 B：NULL 满天飞（金额/日期/机构 NULL，含全 NULL 行）
  - 另类 C：分布异常（全员同一余额、某月全员 0、全员同业）
  - 另类 D：关联断裂/重复（两表对不上、同客户同日期多条、客户号格式混乱）
  - 另类 E：时间异常（所有日期一样、跨年、未来日期、全员单调增长）

用法：
  python backend/example/gen_retail_data.py

依赖：openpyxl（pip install openpyxl）
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Callable

from openpyxl import Workbook

HERE = Path(__file__).resolve().parent
SEED = 20260101

# ============================================================
# 表结构（所有数据集共用同一套 schema）
# ============================================================

AST_COLUMNS = [
    # (字段名, DDL 片段, COMMENT)
    ("Statistics_Dt",    "DATE NOT NULL",              "统计日期"),
    ("Cust_Id",          "VARCHAR(150) NOT NULL",     "客户号"),
    ("Cust_Open_Org_Id", "VARCHAR(150)",              "客户开户机构"),
    ("Belong_Org_Id",    "VARCHAR(150)",              "客户归属机构编号"),
    ("Belong_Branch_Id", "VARCHAR(150)",              "客户归属机构分行编号"),
    ("Deposit_Bal",      "DECIMAL(18,2)",             "存款余额"),
    ("Cust_Type",        "VARCHAR(30)",               "客户类型(个人/对公/同业)"),
    ("Region",           "VARCHAR(30)",               "客户所属区域"),
    ("Deposit_Product",  "VARCHAR(60)",               "存款产品"),
    ("Avg_Bal",          "DECIMAL(18,2)",             "月日均余额"),
    ("Rate_Band",        "VARCHAR(30)",               "利率档位"),
]

TAG_COLUMNS = [
    ("Statistics_Dt",         "DATE NOT NULL",         "统计日期"),
    ("Cust_Id",               "VARCHAR(150) NOT NULL", "客户号"),
    ("Ever_Hold_Deposit_ind", "VARCHAR(3)",            "历史存款类产品购买标志(YES/NO/空值)"),
    ("New_Fund_Flag",         "VARCHAR(3)",            "是否当月新进资金(YES/NO/空值)"),
]

AST_FIELD_ORDER = [c[0] for c in AST_COLUMNS]
TAG_FIELD_ORDER = [c[0] for c in TAG_COLUMNS]

# Excel 表头用中文（参考 make_sample_data.py 风格，人看直观）；
# SQL schema 字段名仍用英文（数据库规范），内部数据 dict 的 key 也用英文，
# 只在写 Excel 第一行时换成中文表头。两套表头按下标一一对应。
AST_HEADER_ZH = ["统计日期", "客户号", "开户机构", "归属机构", "归属分行",
                 "存款余额", "客户类型", "区域", "存款产品", "月日均余额", "利率档位"]
TAG_HEADER_ZH = ["统计日期", "客户号", "历史持有标志", "新进资金标志"]
assert len(AST_HEADER_ZH) == len(AST_FIELD_ORDER)
assert len(TAG_HEADER_ZH) == len(TAG_FIELD_ORDER)

# ============================================================
# 业务常量（区域/分行/机构/产品/利率档）
# ============================================================

# 分行 → 区域 → 机构 一一映射（每个分行对应一个区域，分行下挂 1-2 个机构）
BRANCHES = [
    # (branch_id, region, [org_ids])
    ("BR001", "华东", ["ORG001", "ORG002"]),
    ("BR002", "华南", ["ORG003", "ORG004"]),
    ("BR003", "华北", ["ORG005"]),
    ("BR004", "西部", ["ORG006", "ORG007"]),
    ("BR005", "东北", ["ORG008"]),
]

# 客户类型 → 产品池 → 利率档
PRODUCT_TABLE = {
    "对公": [("大额存单", "2.30%"), ("通知存款", "1.50%"), ("定期1Y", "1.90%")],
    "同业": [("通知存款", "1.50%"), ("定期1Y", "1.90%"), ("大额存单", "2.40%")],
    "个人": [("活期", "0.30%"), ("定期3M", "1.40%"), ("定期6M", "1.60%"), ("大额存单", "2.00%")],
}

# 统计日期：每月 15 日，2024-01 ~ 2024-12
NORMAL_DATES = [date(2024, m, 15) for m in range(1, 13)]
# 季末月（冲量月）
SEASON_END_MONTHS = {3, 6, 9, 12}


def _q2(v) -> Decimal:
    """统一保留两位小数，避免浮点漂移。"""
    return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ============================================================
# 数据集配置：每份指定 bal/tag 两个行列表
# ============================================================

@dataclass
class DatasetConfig:
    """单个数据集的配置。

    rows_bal / rows_tag：每行是 dict，key 用字段名。
    note：数据集简介，写进文件头注释。
    with_pk：建表是否加 PRIMARY KEY (Statistics_Dt, Cust_Id)。
             另类 D 需要测"同客户同日期多条"，关掉 PK 才能插进去。
    """
    name: str                 # 文件前缀，如 retail_deposit_small
    title: str                # 报告标题
    period_desc: str          # 报告期描述
    note: str                 # 数据集说明
    rows_bal: list[dict]      # RTL_CUST_AST_MGT_BAL 行
    rows_tag: list[dict]      # RTL_CUST_BEHAVIOR_TAG 行
    with_pk: bool = True      # 默认带 PK，另类 D 关掉


# ============================================================
# 1) 正常数据生成
# ============================================================

def gen_normal_rows(rng: random.Random) -> tuple[list[dict], list[dict]]:
    """25 客户 × 12 月 = 300 行。二八分布 + 季节性 + 跨月趋势。

    客户分档：
      - 大客户 5 个（CUST000001~005）：对公 2 / 同业 2 / 个人大额 1，余额 500-1500 万
      - 普通 15 个（CUST000006~020）：个人，余额 5-100 万
      - 小额 5 个（CUST000021~025）：个人，余额 1-5 万
    跨月趋势：
      - CUST000001：持续增长（每月 +2-3%）
      - CUST000002：衰减（每月 -1-2%）
      - CUST000003：6 月突然大额转入
      - CUST000004：先平稳后下滑
      - CUST000005：周期波动
    季末冲量：3/6/9/12 月余额上浮 10-20%，New_Fund_Flag=YES
    """
    # 客户档案：cid → (cust_type, branch_idx, base_bal, trend_fn)
    cust_profiles = {}

    # 5 大客户
    big_defs = [
        # (cid, cust_type, branch_idx, base_bal(万), trend_fn)
        ("CUST000001", "对公", 0, 1200.0, "grow"),
        ("CUST000002", "对公", 1, 800.0,  "decay"),
        ("CUST000003", "同业", 2, 1000.0, "jump"),
        ("CUST000004", "同业", 3, 1500.0, "flat_then_down"),
        ("CUST000005", "个人", 4, 500.0,  "wave"),
    ]
    # 15 普通客户
    mid_defs = [
        (f"CUST00000{i:02d}", "个人", i % 5, round(rng.uniform(5, 100), 2), "normal")
        for i in range(6, 21)
    ]
    # 5 小额客户
    small_defs = [
        (f"CUST0000{i:03d}", "个人", i % 5, round(rng.uniform(1, 5), 2), "small")
        for i in range(21, 26)
    ]

    for cid, ctype, br_idx, base_wan, trend in big_defs + mid_defs + small_defs:
        br_id, region, orgs = BRANCHES[br_idx]
        org_id = rng.choice(orgs)
        product, rate = rng.choice(PRODUCT_TABLE[ctype])
        cust_profiles[cid] = {
            "cust_type": ctype,
            "branch_id": br_id,
            "region": region,
            "org_id": org_id,
            "product": product,
            "rate": rate,
            "base_bal": _q2(base_wan * 10000),  # 转成元
            "trend": trend,
        }

    rows_bal, rows_tag = [], []
    for m_idx, dt in enumerate(NORMAL_DATES):  # 0~11
        is_season_end = dt.month in SEASON_END_MONTHS
        # 季末冲量倍数
        season_mult = rng.uniform(1.10, 1.20) if is_season_end else 1.0
        for cid, p in cust_profiles.items():
            # 用 float 做趋势计算（Decimal 不能直接乘 float），最后量化回 Decimal
            bal = float(p["base_bal"])
            trend = p["trend"]
            # 跨月趋势
            if trend == "grow":
                bal = bal * (1 + 0.025 * m_idx)
            elif trend == "decay":
                bal = bal * (1 - 0.015 * m_idx)
            elif trend == "jump":
                # 6 月（m_idx=5）突然大额转入
                bal = bal * (3.0 if m_idx == 5 else 1.0)
            elif trend == "flat_then_down":
                # 前 6 月平稳，后 6 月每月 -3%
                bal = bal * (1.0 if m_idx < 6 else (0.97 ** (m_idx - 5)))
            elif trend == "wave":
                # 周期波动：正弦近似
                import math
                bal = bal * (1 + 0.10 * math.sin(m_idx / 12 * 2 * math.pi))
            # normal / small：小幅随机扰动
            if trend in ("normal", "small"):
                bal = bal * rng.uniform(0.95, 1.05)
            # 季末冲量
            bal = bal * season_mult
            bal_q = _q2(bal)
            # 月日均 = 余额 × (0.9~1.0)（日均略低于月末）
            avg_q = _q2(bal * rng.uniform(0.90, 1.00))

            rows_bal.append({
                "Statistics_Dt":    dt,
                "Cust_Id":          cid,
                "Cust_Open_Org_Id": p["org_id"],
                "Belong_Org_Id":    p["org_id"],
                "Belong_Branch_Id": p["branch_id"],
                "Deposit_Bal":      bal_q,
                "Cust_Type":        p["cust_type"],
                "Region":           p["region"],
                "Deposit_Product":  p["product"],
                "Avg_Bal":          avg_q,
                "Rate_Band":        p["rate"],
            })
            # 行为标签：大客户 YES，普通客户 YES/NO 混合，小额 NO 居多
            if p["cust_type"] in ("对公", "同业"):
                ever = "YES"
            elif p["cust_type"] == "个人" and bal_q >= 100000:
                ever = rng.choice(["YES", "YES", "NO"])
            else:
                ever = rng.choice(["NO", "NO", "YES"])
            new_fund = "YES" if is_season_end else "NO"
            rows_tag.append({
                "Statistics_Dt":         dt,
                "Cust_Id":               cid,
                "Ever_Hold_Deposit_ind": ever,
                "New_Fund_Flag":         new_fund,
            })
    return rows_bal, rows_tag


# ============================================================
# 2) 另类 A：零值/极端值
# ============================================================

def gen_edge_a_rows(rng: random.Random) -> tuple[list[dict], list[dict]]:
    """全员零值/极端值。5 客户 × 4 月 = 20 行。

    - CUST000001：余额 0.00
    - CUST000002：余额 -50000.00（负数，业务上代表冲正/多记）
    - CUST000003：余额 1000000000.00（10 亿，逼近 DECIMAL(18,2) 上限）
    - CUST000004：余额 1234.567891（6 位小数，会被 DECIMAL(18,2) 截断为 1234.57）
    - CUST000005：余额 999999999.99（接近 10 亿，差 1 分到 10 亿）
    """
    dates = [date(2024, m, 15) for m in range(1, 5)]
    # 5 种极端余额：0 / 负数 / 10 亿 / 6 位小数（落库后变 1234.57）/ 近 10 亿
    edge_bals = [
        Decimal("0.00"),
        Decimal("-50000.00"),
        Decimal("1000000000.00"),
        Decimal("1234.567891"),  # MySQL DECIMAL(18,2) 落库后为 1234.57
        Decimal("999999999.99"),
    ]
    cust_types = ["对公", "对公", "同业", "个人", "个人"]
    rows_bal, rows_tag = [], []
    for i, (cid, ctype) in enumerate(zip(
        ["CUST000001", "CUST000002", "CUST000003", "CUST000004", "CUST000005"], cust_types)):
        br_idx = i % len(BRANCHES)
        br_id, region, orgs = BRANCHES[br_idx]
        product, rate = PRODUCT_TABLE[ctype][0]
        for j, dt in enumerate(dates):
            # Excel 与 SQL INSERT 都写原值；DECIMAL(18,2) 落库时自动截断，
            # 造成 Excel 里的 1234.567891 与表里的 1234.57 天然对不上。
            bal = edge_bals[i]
            rows_bal.append({
                "Statistics_Dt":    dt,
                "Cust_Id":          cid,
                "Cust_Open_Org_Id": orgs[0],
                "Belong_Org_Id":    orgs[0],
                "Belong_Branch_Id": br_id,
                "Deposit_Bal":      bal,
                "Cust_Type":        ctype,
                "Region":           region,
                "Deposit_Product":  product,
                "Avg_Bal":          bal,
                "Rate_Band":        rate,
            })
            rows_tag.append({
                "Statistics_Dt":         dt,
                "Cust_Id":               cid,
                "Ever_Hold_Deposit_ind": "YES" if i % 2 == 0 else "NO",
                "New_Fund_Flag":         "NO",
            })
    return rows_bal, rows_tag


# ============================================================
# 3) 另类 B：NULL 满天飞
# ============================================================

def gen_edge_b_rows(rng: random.Random) -> tuple[list[dict], list[dict]]:
    """NULL 满天飞。5 客户 × 4 月 = 20 行。

    - CUST000001：Deposit_Bal NULL（其他字段正常）
    - CUST000002：Cust_Open_Org_Id NULL（开户机构空）
    - CUST000003：Belong_Branch_Id NULL（分行编号空）
    - CUST000004：Ever_Hold_Deposit_ind NULL（行为标签全 NULL）
    - CUST000005：除主键外全字段 NULL（一条空记录）
    """
    dates = [date(2024, m, 15) for m in range(1, 5)]
    base_row = {
        "Cust_Open_Org_Id": "ORG001",
        "Belong_Org_Id":    "ORG001",
        "Belong_Branch_Id": "BR001",
        "Deposit_Bal":      Decimal("100000.00"),
        "Cust_Type":        "个人",
        "Region":           "华东",
        "Deposit_Product":  "定期3M",
        "Avg_Bal":          Decimal("95000.00"),
        "Rate_Band":        "1.40%",
    }
    rows_bal, rows_tag = [], []
    cids = ["CUST000001", "CUST000002", "CUST000003", "CUST000004", "CUST000005"]
    for i, cid in enumerate(cids):
        for j, dt in enumerate(dates):
            row = {
                "Statistics_Dt":    dt,
                "Cust_Id":          cid,
            }
            row.update(base_row)
            # 按 cid 决定哪个字段置空
            if cid == "CUST000001":
                row["Deposit_Bal"] = None
                row["Avg_Bal"] = None
            elif cid == "CUST000002":
                row["Cust_Open_Org_Id"] = None
            elif cid == "CUST000003":
                row["Belong_Branch_Id"] = None
            elif cid == "CUST000004":
                # 正常，行为标签表那边全 NULL
                pass
            elif cid == "CUST000005":
                # 除主键外全 NULL
                for k in list(row.keys()):
                    if k not in ("Statistics_Dt", "Cust_Id"):
                        row[k] = None
            rows_bal.append(row)
            # 行为标签
            tag_row = {"Statistics_Dt": dt, "Cust_Id": cid}
            if cid == "CUST000004":
                tag_row["Ever_Hold_Deposit_ind"] = None
                tag_row["New_Fund_Flag"] = None
            elif cid == "CUST000005":
                tag_row["Ever_Hold_Deposit_ind"] = None
                tag_row["New_Fund_Flag"] = None
            else:
                tag_row["Ever_Hold_Deposit_ind"] = "YES" if i % 2 == 0 else "NO"
                tag_row["New_Fund_Flag"] = "NO"
            rows_tag.append(tag_row)
    return rows_bal, rows_tag


# ============================================================
# 4) 另类 C：分布异常
# ============================================================

def gen_edge_c_rows(rng: random.Random) -> tuple[list[dict], list[dict]]:
    """分布异常。5 客户 × 4 月 = 20 行。

    - 全员同一余额（1000000.00）
    - 某月（3 月）全员余额 0.00
    - 所有客户 Cust_Type 都是"同业"（应触发"客户类型分布 100% 同业"的异常检测）
    """
    dates = [date(2024, m, 15) for m in range(1, 5)]
    cids = ["CUST000001", "CUST000002", "CUST000003", "CUST000004", "CUST000005"]
    rows_bal, rows_tag = [], []
    for i, cid in enumerate(cids):
        br_idx = i % len(BRANCHES)
        br_id, region, orgs = BRANCHES[br_idx]
        product, rate = PRODUCT_TABLE["同业"][0]
        for j, dt in enumerate(dates):
            # 3 月全员 0，其他月全员 100 万
            if dt.month == 3:
                bal = Decimal("0.00")
                avg = Decimal("0.00")
            else:
                bal = Decimal("1000000.00")
                avg = Decimal("950000.00")
            rows_bal.append({
                "Statistics_Dt":    dt,
                "Cust_Id":          cid,
                "Cust_Open_Org_Id": orgs[0],
                "Belong_Org_Id":    orgs[0],
                "Belong_Branch_Id": br_id,
                "Deposit_Bal":      bal,
                "Cust_Type":        "同业",
                "Region":           region,
                "Deposit_Product":  product,
                "Avg_Bal":          avg,
                "Rate_Band":        rate,
            })
            rows_tag.append({
                "Statistics_Dt":         dt,
                "Cust_Id":               cid,
                "Ever_Hold_Deposit_ind": "YES",
                "New_Fund_Flag":         "YES" if dt.month == 3 else "NO",
            })
    return rows_bal, rows_tag


# ============================================================
# 5) 另类 D：关联断裂/重复
# ============================================================

def gen_edge_d_rows(rng: random.Random) -> tuple[list[dict], list[dict]]:
    """关联断裂/重复。约 30 行。

    - 两表对不上：CUST000001 在 bal 表有，tag 表没
    - CUST000002 在 tag 表有，bal 表没
    - CUST000003 在某月（2024-02）bal 表有 2 条（同日期同客户号）
    - 客户号格式混乱：CUST000004 vs CUST0004（少一个 0）
    - 客户号大小写混乱：cust-001 vs CUST-001
    """
    dates = [date(2024, m, 15) for m in range(1, 5)]
    rows_bal, rows_tag = [], []

    def _bal_row(cid, dt, br_idx, bal, ctype="个人"):
        br_id, region, orgs = BRANCHES[br_idx % len(BRANCHES)]
        product, rate = PRODUCT_TABLE[ctype][0]
        return {
            "Statistics_Dt":    dt,
            "Cust_Id":          cid,
            "Cust_Open_Org_Id": orgs[0],
            "Belong_Org_Id":    orgs[0],
            "Belong_Branch_Id": br_id,
            "Deposit_Bal":      _q2(bal),
            "Cust_Type":        ctype,
            "Region":           region,
            "Deposit_Product":  product,
            "Avg_Bal":          _q2(bal * 0.95),
            "Rate_Band":        rate,
        }

    def _tag_row(cid, dt, ever="YES", new="NO"):
        return {
            "Statistics_Dt":         dt,
            "Cust_Id":               cid,
            "Ever_Hold_Deposit_ind": ever,
            "New_Fund_Flag":         new,
        }

    # CUST000001：只在 bal 表
    for dt in dates:
        rows_bal.append(_bal_row("CUST000001", dt, 0, 50000))
    # CUST000002：只在 tag 表
    for dt in dates:
        rows_tag.append(_tag_row("CUST000002", dt, ever="NO"))

    # CUST000003：2024-02 在 bal 表有 2 条（同日期同客户号，破坏 PK）
    for dt in dates:
        rows_bal.append(_bal_row("CUST000003", dt, 1, 200000))
        rows_tag.append(_tag_row("CUST000003", dt))
    # 加一条重复
    dup = _bal_row("CUST000003", date(2024, 2, 15), 1, 250000)
    rows_bal.append(dup)

    # CUST000004 vs CUST0004（客户号少一个 0，看模型会不会识别为同一客户）
    for dt in dates:
        rows_bal.append(_bal_row("CUST000004", dt, 2, 80000))
        rows_bal.append(_bal_row("CUST0004",   dt, 2, 80000))
        rows_tag.append(_tag_row("CUST000004", dt))
        rows_tag.append(_tag_row("CUST0004",   dt))

    # cust-001 vs CUST-001（大小写+连字符混乱）
    for dt in dates:
        rows_bal.append(_bal_row("cust-001", dt, 3, 30000))
        rows_bal.append(_bal_row("CUST-001", dt, 3, 30000))
        rows_tag.append(_tag_row("cust-001", dt, ever="YES"))
        rows_tag.append(_tag_row("CUST-001", dt, ever="NO"))

    return rows_bal, rows_tag


# ============================================================
# 6) 另类 E：时间异常
# ============================================================

def gen_edge_e_rows(rng: random.Random) -> tuple[list[dict], list[dict]]:
    """时间异常。5 客户 × 4 月 = 20 行。

    - CUST000001~005：所有月份 Statistics_Dt 都是 2024-06-15（同一天）
    - CUST000001 跨年：2023-12 ~ 2024-02（看模型会不会算跨年同比）
    - CUST000002：未来日期（2026-01 ~ 2026-04）
    - CUST000003~005：全员余额单调增长（1月1万、2月2万...12月12万），
      验证模型会不会无脑套"稳步增长"套话
    """
    rows_bal, rows_tag = [], []

    def _bal_row(cid, dt, br_idx, bal, ctype="个人"):
        br_id, region, orgs = BRANCHES[br_idx % len(BRANCHES)]
        product, rate = PRODUCT_TABLE[ctype][0]
        return {
            "Statistics_Dt":    dt,
            "Cust_Id":          cid,
            "Cust_Open_Org_Id": orgs[0],
            "Belong_Org_Id":    orgs[0],
            "Belong_Branch_Id": br_id,
            "Deposit_Bal":      _q2(bal),
            "Cust_Type":        ctype,
            "Region":           region,
            "Deposit_Product":  product,
            "Avg_Bal":          _q2(bal * 0.95),
            "Rate_Band":        rate,
        }

    def _tag_row(cid, dt, ever="YES", new="NO"):
        return {
            "Statistics_Dt":         dt,
            "Cust_Id":               cid,
            "Ever_Hold_Deposit_ind": ever,
            "New_Fund_Flag":         new,
        }

    # CUST000001：所有行都是同一天 2024-06-15，余额递增
    for i in range(4):
        dt = date(2024, 6, 15)
        rows_bal.append(_bal_row("CUST000001", dt, 0, 10000 * (i + 1)))
        rows_tag.append(_tag_row("CUST000001", dt, new="YES"))

    # CUST000002：跨年 2023-12 ~ 2024-02
    cross_year_dates = [date(2023, 12, 15), date(2024, 1, 15), date(2024, 2, 15), date(2024, 3, 15)]
    for i, dt in enumerate(cross_year_dates):
        rows_bal.append(_bal_row("CUST000002", dt, 1, 80000 + i * 5000))
        rows_tag.append(_tag_row("CUST000002", dt))

    # CUST000003：未来日期 2026-01 ~ 2026-04
    for i, m in enumerate([1, 2, 3, 4]):
        dt = date(2026, m, 15)
        rows_bal.append(_bal_row("CUST000003", dt, 2, 120000))
        rows_tag.append(_tag_row("CUST000003", dt))

    # CUST000004 & 005：单调增长（1月1万、4月4万），看模型会不会无脑"稳步增长"
    for cid, br_idx, base in [("CUST000004", 3, 10000), ("CUST000005", 4, 15000)]:
        for i, m in enumerate([1, 2, 3, 4]):
            dt = date(2024, m, 15)
            rows_bal.append(_bal_row(cid, dt, br_idx, base * (i + 1)))
            rows_tag.append(_tag_row(cid, dt))

    return rows_bal, rows_tag


# ============================================================
# 文件写出器
# ============================================================

def _sql_val(v, is_date=False):
    """把 Python 值转成 SQL 字面量。"""
    if v is None:
        return "NULL"
    if is_date:
        # date 或字符串
        if isinstance(v, date):
            return f"DATE '{v.isoformat()}'"
        return f"DATE '{v}'"
    if isinstance(v, (int, Decimal)):
        return str(v)
    # 字符串
    s = str(v).replace("'", "''")
    return f"'{s}'"


def write_schema_sql(cfg: DatasetConfig, path: Path):
    """写 schema.sql：建库 + 建表 + INSERT（MySQL 语法）。"""
    db_name = "RTL_REPORT_TEST"
    lines = []
    lines.append(f"-- {cfg.title}")
    lines.append(f"-- 数据集：{cfg.name}")
    lines.append(f"-- {cfg.note}")
    lines.append("")
    lines.append("-- 建库：")
    lines.append(f"--   mysql -u root -p < {path.name}")
    lines.append("")
    lines.append(f"CREATE DATABASE IF NOT EXISTS {db_name}")
    lines.append("  DEFAULT CHARACTER SET utf8mb4")
    lines.append("  DEFAULT COLLATE utf8mb4_unicode_ci;")
    lines.append("")
    lines.append(f"USE {db_name};")
    lines.append("")
    # 建表
    lines.append("DROP TABLE IF EXISTS RTL_CUST_BEHAVIOR_TAG;")
    lines.append("DROP TABLE IF EXISTS RTL_CUST_AST_MGT_BAL;")
    lines.append("")
    pk_clause = "  PRIMARY KEY (Statistics_Dt, Cust_Id)" if cfg.with_pk else ""
    # 资产管理余额表
    lines.append("-- 零售客户资产管理余额表")
    lines.append("CREATE TABLE RTL_CUST_AST_MGT_BAL (")
    for name, ddl, comment in AST_COLUMNS:
        lines.append(f"  {name:<22} {ddl:<30} COMMENT '{comment}',")
    if pk_clause:
        lines.append(pk_clause)
    else:
        # 没有显式 PK 时去掉最后一行的逗号
        lines[-1] = lines[-1].rstrip(",")
    lines.append(") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci")
    lines.append("  COMMENT='零售客户资产管理余额表';")
    lines.append("")
    lines.append("-- 零售客户行为标签表")
    lines.append("CREATE TABLE RTL_CUST_BEHAVIOR_TAG (")
    for name, ddl, comment in TAG_COLUMNS:
        lines.append(f"  {name:<22} {ddl:<30} COMMENT '{comment}',")
    if pk_clause:
        lines.append(pk_clause)
    else:
        lines[-1] = lines[-1].rstrip(",")
    lines.append(") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci")
    lines.append("  COMMENT='零售客户行为标签表';")
    lines.append("")

    # INSERT bal
    lines.append(f"-- RTL_CUST_AST_MGT_BAL 数据（{len(cfg.rows_bal)} 行）")
    cols = AST_FIELD_ORDER
    lines.append(f"INSERT INTO RTL_CUST_AST_MGT_BAL ({', '.join(cols)}) VALUES")
    n = len(cfg.rows_bal)
    for i, row in enumerate(cfg.rows_bal):
        vals = []
        for c in cols:
            v = row.get(c)
            # Statistics_Dt 是 DATE
            vals.append(_sql_val(v, is_date=(c == "Statistics_Dt")))
        end = "," if i < n - 1 else ";"
        lines.append(f"  ({', '.join(vals)}){end}")
    lines.append("")

    # INSERT tag
    lines.append(f"-- RTL_CUST_BEHAVIOR_TAG 数据（{len(cfg.rows_tag)} 行）")
    cols = TAG_FIELD_ORDER
    lines.append(f"INSERT INTO RTL_CUST_BEHAVIOR_TAG ({', '.join(cols)}) VALUES")
    n = len(cfg.rows_tag)
    for i, row in enumerate(cfg.rows_tag):
        vals = []
        for c in cols:
            v = row.get(c)
            vals.append(_sql_val(v, is_date=(c == "Statistics_Dt")))
        end = "," if i < n - 1 else ";"
        lines.append(f"  ({', '.join(vals)}){end}")
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def _apply_col_widths(ws, headers):
    """根据表头长度给列设宽度（参考 make_sample_data.py 的 max(len*2,14)）。"""
    from openpyxl.utils import get_column_letter
    for idx, header in enumerate(headers, start=1):
        col = get_column_letter(idx)
        # 中文字符按 2 宽度估算，最小 14，避免日期显示成 #######
        width = max(len(str(header)) * 2, 14)
        ws.column_dimensions[col].width = min(width, 32)
    # 冻结表头，方便看数据
    ws.freeze_panes = "A2"


def write_data_xlsx(cfg: DatasetConfig, path: Path):
    """写 data.xlsx：两 sheet。

    第一行用中文表头（AST_HEADER_ZH / TAG_HEADER_ZH），数据行按英文字段名取值。
    这样 Excel 人看是中文，但内部数据 dict 和 SQL schema 字段名仍一致（英文）。
    """
    wb = Workbook()
    # 第一张表：资产管理余额
    ws1 = wb.active
    ws1.title = "RTL_CUST_AST_MGT_BAL"
    ws1.append(AST_HEADER_ZH)
    for row in cfg.rows_bal:
        ws1.append([row.get(c) for c in AST_FIELD_ORDER])
    _apply_col_widths(ws1, AST_HEADER_ZH)
    # 第二张表：行为标签
    ws2 = wb.create_sheet("RTL_CUST_BEHAVIOR_TAG")
    ws2.append(TAG_HEADER_ZH)
    for row in cfg.rows_tag:
        ws2.append([row.get(c) for c in TAG_FIELD_ORDER])
    _apply_col_widths(ws2, TAG_HEADER_ZH)
    wb.save(path)


def write_report_template(cfg: DatasetConfig, path: Path):
    """写 report_template.md：6 章模板，章节里带派生计算要求。"""
    content = f"""# {cfg.title}

{cfg.period_desc}

## 一、报告说明

说明本报告的分析口径与数据来源。本章为纯文字说明，不涉及任何统计指标。

数据取自零售客户资产管理余额表（RTL_CUST_AST_MGT_BAL）与零售客户行为标签表（RTL_CUST_BEHAVIOR_TAG），两表以统计日期（Statistics_Dt）和客户号（Cust_Id）关联。本章需要说明报告期、统计口径（月末/月日均）、客户类型范围（个人/对公/同业）、区域范围。

## 二、存款规模总览

概述报告期内零售客户的整体存款情况，需要说明并自行计算：

- 存款余额合计（SUM(Deposit_Bal)）
- 客户数（COUNT(DISTINCT Cust_Id)）
- 户均存款余额（AVG(Deposit_Bal)），并说明按记录平均还是按去重客户平均
- 月日均余额合计（SUM(Avg_Bal)）与月末余额合计的差异说明

本章需要指出两个口径（按记录 vs 按去重客户）的差异。

## 三、客户类型与产品结构

按客户类型（Cust_Type：个人/对公/同业）拆解存款余额，并按存款产品（Deposit_Product）细分，需要说明：

- 各客户类型的客户数与存款余额
- 各客户类型的存款余额占比（占总余额的百分比，需自行计算）
- 各存款产品的客户数与存款余额
- 指出存款余额占比最高的客户类型

| 客户类型 | 客户数 | 存款余额（元） | 占比 |
|---|---|---|---|
|  |  |  |  |

| 存款产品 | 客户数 | 存款余额（元） |
|---|---|---|
|  |  |  |

## 四、月度存款趋势

按统计日期（Statistics_Dt）逐月对比存款余额合计、客户数、月日均余额，需要说明：

- 各月存款余额合计与客户数
- 环比增速（需自行计算：本月 - 上月）/ 上月）
- 同比增速（若数据期跨年，需自行计算）
- 指出环比变化最大的月份

| 统计日期 | 客户数 | 存款余额（元） | 月日均余额（元） | 环比增速 |
|---|---|---|---|---|
|  |  |  |  |  |

## 五、分行与区域分布

按客户归属分行（Belong_Branch_Id）与区域（Region）拆解存款余额，需要说明：

- 各分行的客户数与存款余额
- 各区域的客户数与存款余额
- 各分行的户均存款余额（需自行计算：存款余额 / 客户数）
- 指出存款余额最高的分行与区域

| 分行编号 | 区域 | 客户数 | 存款余额（元） | 户均余额（元） |
|---|---|---|---|---|
|  |  |  |  |  |

## 六、高净值客户与行为标签分析

筛选高净值客户（存款余额 ≥ 100 万元的客户），结合行为标签（Ever_Hold_Deposit_ind / New_Fund_Flag）分析，需要说明：

- 高净值客户数与存款余额合计
- 高净值客户存款余额占总余额的占比（需自行计算）
- 持有存款类产品（Ever_Hold_Deposit_ind='YES'）与未持有（'NO'）的客户数对比
- 当月新进资金（New_Fund_Flag='YES'）的客户数与存款余额
- 指出存款余额最高的客户（不得在正文编造客户号）

| 客户号 | 客户类型 | 存款余额（元） | 历史持有标志 | 新进资金标志 |
|---|---|---|---|---|
|  |  |  |  |  |
"""
    path.write_text(content, encoding="utf-8")


def write_testing_md(cfg: DatasetConfig, path: Path, expected: dict):
    """写 TESTING.md：各章参考 SQL + 标准答案。

    expected 形如：
      {
        "二": [("存款余额合计", "value", "SELECT ...", "12345.67"), ...],
        "三": [("客户类型分布", "table", "SELECT ...", "| ... |")],
        ...
      }
    """
    lines = []
    lines.append(f"# {cfg.title}：参考 SQL 与标准答案")
    lines.append("")
    lines.append(f"数据集：`{cfg.name}`")
    lines.append("")
    lines.append(cfg.note)
    lines.append("")
    lines.append("## 准备")
    lines.append("")
    lines.append("```bash")
    lines.append(f"mysql -u root -p < backend/example/{cfg.name}_schema.sql")
    lines.append("")
    lines.append("# 只读账号")
    lines.append('mysql -u root -p -e "')
    lines.append("CREATE USER IF NOT EXISTS 'report_ro'@'%' IDENTIFIED BY 'ReadOnly@2024';")
    lines.append("GRANT SELECT ON RTL_REPORT_TEST.* TO 'report_ro'@'%';")
    lines.append('FLUSH PRIVILEGES;"')
    lines.append("```")
    lines.append("")
    lines.append("## 数据概况")
    lines.append("")
    lines.append(f"- RTL_CUST_AST_MGT_BAL：{len(cfg.rows_bal)} 行")
    lines.append(f"- RTL_CUST_BEHAVIOR_TAG：{len(cfg.rows_tag)} 行")
    lines.append("")

    lines.append("## shape 约定")
    lines.append("")
    lines.append("**`value` 型按位置解析：最后一列是数值，它前面的所有列都被当成维度。**"
                "单值指标要么只 SELECT 一列，要么把维度放在前面。")
    lines.append("")

    for ch, items in expected.items():
        lines.append(f"## {ch}章参考 SQL")
        lines.append("")
        if not items:
            lines.append("本章为纯文字章节，不应产生追问。")
            lines.append("")
            continue
        lines.append("| 指标 | shape | 参考 SQL | 标准答案 |")
        lines.append("|---|---|---|---|")
        for name, shape, sql, ans in items:
            sql_inline = sql.replace("|", "\\|").replace("\n", " ")
            ans_inline = str(ans).replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {name} | {shape} | `{sql_inline}` | {ans_inline} |")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


# ============================================================
# 标准答案计算（事后用同一份数据回算，避免人工填错）
# ============================================================

def _sum_bal(rows, col="Deposit_Bal") -> Decimal:
    return _q2(sum((r[col] for r in rows if r[col] is not None), Decimal("0")))


def _distinct_cust(rows) -> set:
    return {r["Cust_Id"] for r in rows if r["Cust_Id"] is not None}


def compute_expected(cfg: DatasetConfig) -> dict:
    """根据 cfg.rows_bal / rows_tag 回算各章标准答案。"""
    bal_rows = cfg.rows_bal
    tag_rows = cfg.rows_tag
    expected = {}

    # 一章：纯文字
    expected["一"] = []

    # 二章：存款规模总览
    total_bal = _sum_bal(bal_rows)
    n_records = len(bal_rows)
    n_distinct = len(_distinct_cust(bal_rows))
    avg_by_record = _q2(total_bal / n_records) if n_records else "N/A"
    avg_by_distinct = _q2(total_bal / n_distinct) if n_distinct else "N/A"
    sum_avg = _sum_bal(bal_rows, "Avg_Bal")
    expected["二"] = [
        ("存款余额合计", "value",
         "SELECT SUM(Deposit_Bal) FROM RTL_CUST_AST_MGT_BAL",
         str(total_bal)),
        ("客户数(去重)", "value",
         "SELECT COUNT(DISTINCT Cust_Id) FROM RTL_CUST_AST_MGT_BAL",
         str(n_distinct)),
        ("户均(按记录)", "value",
         "SELECT ROUND(AVG(Deposit_Bal),2) FROM RTL_CUST_AST_MGT_BAL",
         str(avg_by_record)),
        ("户均(按去重客户)", "value",
         "SELECT ROUND(SUM(Deposit_Bal)/COUNT(DISTINCT Cust_Id),2) FROM RTL_CUST_AST_MGT_BAL",
         str(avg_by_distinct)),
        ("月日均合计", "value",
         "SELECT SUM(Avg_Bal) FROM RTL_CUST_AST_MGT_BAL",
         str(sum_avg)),
    ]

    # 三章：客户类型与产品结构
    # 按客户类型
    by_type = {}
    for r in bal_rows:
        t = r.get("Cust_Type")
        if t is None:
            t = "(空值)"
        by_type.setdefault(t, {"cnt": 0, "bal": Decimal("0")})
        by_type[t]["cnt"] += 1
        by_type[t]["bal"] += r["Deposit_Bal"] if r["Deposit_Bal"] is not None else Decimal("0")
    type_rows = sorted(((t, v["cnt"], _q2(v["bal"])) for t, v in by_type.items()),
                       key=lambda x: -x[2])
    type_table = "| 客户类型 | 客户数 | 存款余额 |\\n|---|---|---|\\n"
    for t, c, b in type_rows:
        pct = _q2(b / total_bal * 100) if total_bal else "N/A"
        type_table += f"| {t} | {c} | {b} | 占比 {pct}%\\n"
    expected["三"] = [
        ("客户类型分布", "table",
         "SELECT COALESCE(Cust_Type,'(空值)') AS t, COUNT(*) AS cnt, SUM(Deposit_Bal) AS bal "
         "FROM RTL_CUST_AST_MGT_BAL GROUP BY 1 ORDER BY bal DESC",
         type_table),
        ("产品分布", "table",
         "SELECT COALESCE(Deposit_Product,'(空值)') AS p, COUNT(*) AS cnt, SUM(Deposit_Bal) AS bal "
         "FROM RTL_CUST_AST_MGT_BAL GROUP BY 1 ORDER BY bal DESC",
         "见下表"),
    ]

    # 四章：月度趋势
    by_month = {}
    for r in bal_rows:
        d = r["Statistics_Dt"]
        by_month.setdefault(d, {"cnt": 0, "bal": Decimal("0"), "avg": Decimal("0")})
        by_month[d]["cnt"] += 1
        by_month[d]["bal"] += r["Deposit_Bal"] if r["Deposit_Bal"] is not None else Decimal("0")
        by_month[d]["avg"] += r["Avg_Bal"] if r["Avg_Bal"] is not None else Decimal("0")
    months_sorted = sorted(by_month.keys())
    trend_table = "| 统计日期 | 客户数 | 存款余额 | 月日均 | 环比 |\\n|---|---|---|---|---|\\n"
    prev_bal = None
    for d in months_sorted:
        v = by_month[d]
        bal_q = _q2(v["bal"])
        avg_q = _q2(v["avg"])
        if prev_bal is not None and prev_bal != 0:
            mom = _q2((bal_q - prev_bal) / prev_bal * 100)
            mom_str = f"{mom}%"
        else:
            mom_str = "—"
        trend_table += f"| {d} | {v['cnt']} | {bal_q} | {avg_q} | {mom_str}\\n"
        prev_bal = bal_q
    expected["四"] = [
        ("月度趋势", "table",
         "SELECT Statistics_Dt, COUNT(*) AS cnt, SUM(Deposit_Bal) AS bal, SUM(Avg_Bal) AS avg "
         "FROM RTL_CUST_AST_MGT_BAL GROUP BY Statistics_Dt ORDER BY Statistics_Dt",
         trend_table),
    ]

    # 五章：分行与区域
    by_branch = {}
    for r in bal_rows:
        b = r.get("Belong_Branch_Id")
        rg = r.get("Region")
        if b is None:
            b = "(空值)"
        if rg is None:
            rg = "(空值)"
        by_branch.setdefault((b, rg), {"cnt": 0, "bal": Decimal("0")})
        by_branch[(b, rg)]["cnt"] += 1
        by_branch[(b, rg)]["bal"] += r["Deposit_Bal"] if r["Deposit_Bal"] is not None else Decimal("0")
    branch_rows = sorted(by_branch.items(), key=lambda x: -x[1]["bal"])
    branch_table = "| 分行 | 区域 | 客户数 | 存款余额 | 户均 |\\n|---|---|---|---|---|\\n"
    for (b, rg), v in branch_rows:
        bal_q = _q2(v["bal"])
        avg_q = _q2(bal_q / v["cnt"]) if v["cnt"] else "N/A"
        branch_table += f"| {b} | {rg} | {v['cnt']} | {bal_q} | {avg_q}\\n"
    expected["五"] = [
        ("分行分布", "table",
         "SELECT COALESCE(Belong_Branch_Id,'(空值)') AS br, COALESCE(Region,'(空值)') AS rg, "
         "COUNT(*) AS cnt, SUM(Deposit_Bal) AS bal "
         "FROM RTL_CUST_AST_MGT_BAL GROUP BY 1,2 ORDER BY bal DESC",
         branch_table),
    ]

    # 六章：高净值客户 + 行为标签
    # 高净值：Deposit_Bal >= 1000000
    high_rows = [r for r in bal_rows if r["Deposit_Bal"] is not None and r["Deposit_Bal"] >= 1000000]
    high_cnt = len(_distinct_cust(high_rows))
    high_sum = _sum_bal(high_rows)
    high_pct = _q2(high_sum / total_bal * 100) if total_bal else "N/A"

    # 两表 JOIN 后按 Ever_Hold_Deposit_ind 分组
    # 在 Python 里模拟 JOIN：按 (Statistics_Dt, Cust_Id)
    tag_idx = {}
    for t in tag_rows:
        key = (t.get("Statistics_Dt"), t.get("Cust_Id"))
        tag_idx[key] = t
    by_flag = {}
    for r in bal_rows:
        key = (r.get("Statistics_Dt"), r.get("Cust_Id"))
        t = tag_idx.get(key)
        flag = t["Ever_Hold_Deposit_ind"] if t else "(无标签)"
        if flag is None:
            flag = "(空值)"
        by_flag.setdefault(flag, {"cnt": 0, "bal": Decimal("0")})
        by_flag[flag]["cnt"] += 1
        by_flag[flag]["bal"] += r["Deposit_Bal"] if r["Deposit_Bal"] is not None else Decimal("0")
    flag_rows = sorted(by_flag.items(), key=lambda x: -x[1]["bal"])
    flag_table = "| 持有标志 | 客户数 | 存款余额 |\\n|---|---|---|\\n"
    for f, v in flag_rows:
        flag_table += f"| {f} | {v['cnt']} | {_q2(v['bal'])}\\n"

    # New_Fund_Flag
    by_new = {}
    for t in tag_rows:
        f = t.get("New_Fund_Flag")
        if f is None:
            f = "(空值)"
        by_new.setdefault(f, 0)
        by_new[f] += 1
    new_summary = ", ".join(f"{k}: {v}" for k, v in sorted(by_new.items()))

    expected["六"] = [
        ("高净值客户数(余额≥100万)", "value",
         "SELECT COUNT(DISTINCT Cust_Id) FROM RTL_CUST_AST_MGT_BAL WHERE Deposit_Bal>=1000000",
         str(high_cnt)),
        ("高净值存款合计", "value",
         "SELECT SUM(Deposit_Bal) FROM RTL_CUST_AST_MGT_BAL WHERE Deposit_Bal>=1000000",
         str(high_sum)),
        ("高净值占比", "value",
         "SELECT ROUND(SUM(CASE WHEN Deposit_Bal>=1000000 THEN Deposit_Bal ELSE 0 END)/"
         "SUM(Deposit_Bal)*100,2) FROM RTL_CUST_AST_MGT_BAL",
         f"{high_pct}%"),
        ("持有标志分布(JOIN后)", "table",
         "SELECT COALESCE(b.Ever_Hold_Deposit_ind,'(空值)') AS flag, COUNT(*) AS cnt, "
         "SUM(a.Deposit_Bal) AS bal FROM RTL_CUST_AST_MGT_BAL a "
         "LEFT JOIN RTL_CUST_BEHAVIOR_TAG b "
         "ON a.Statistics_Dt=b.Statistics_Dt AND a.Cust_Id=b.Cust_Id "
         "GROUP BY 1 ORDER BY bal DESC",
         flag_table),
        ("新进资金分布", "value",
         "SELECT New_Fund_Flag, COUNT(*) FROM RTL_CUST_BEHAVIOR_TAG GROUP BY 1",
         new_summary),
    ]
    return expected


# ============================================================
# 主入口
# ============================================================

def gen_dataset(cfg: DatasetConfig):
    """根据 cfg 生成 4 件套文件。"""
    schema_path = HERE / f"{cfg.name}_schema.sql"
    xlsx_path = HERE / f"{cfg.name}_data.xlsx"
    tmpl_path = HERE / f"{cfg.name}_report_template.md"
    test_path = HERE / f"{cfg.name}_TESTING.md"

    write_schema_sql(cfg, schema_path)
    write_data_xlsx(cfg, xlsx_path)
    write_report_template(cfg, tmpl_path)
    expected = compute_expected(cfg)
    write_testing_md(cfg, test_path, expected)

    return [schema_path, xlsx_path, tmpl_path, test_path]


def main():
    rng = random.Random(SEED)
    datasets = []

    # 1) 正常数据
    rows_bal, rows_tag = gen_normal_rows(rng)
    datasets.append(DatasetConfig(
        name="retail_deposit_small",
        title="零售客户存款经营分析报告",
        period_desc="本报告分析 2024 年 1 月至 12 月零售客户的存款规模、客户类型与产品结构、"
                    "月度趋势、分行区域分布与高净值客户行为。",
        note="正常数据集：25 客户 × 12 月 = 300 行。二八分布（5 大客户 + 15 普通 + 5 小额），"
             "3/6/9/12 月季末冲量，大客户有持续增长/衰减/突然大额转入/周期波动四种趋势。",
        rows_bal=rows_bal,
        rows_tag=rows_tag,
    ))

    # 2) 另类 A：零值/极端值
    rows_bal, rows_tag = gen_edge_a_rows(rng)
    datasets.append(DatasetConfig(
        name="retail_deposit_edge_a",
        title="零售存款边界数据 A：零值与极端值",
        period_desc="本报告分析 2024 年 1 月至 4 月零售存款边界数据，"
                    "数据集刻意包含零值、负数、10 亿级大额、6 位小数等极端情况。",
        note="另类 A：全员零值/极端值。5 客户 × 4 月 = 20 行。"
             "CUST000001 余额 0；CUST000002 余额 -5 万（负数）；CUST000003 余额 10 亿；"
             "CUST000004 Excel 余额 1234.567891（6 位小数），SQL 截断为 1234.57；"
             "CUST000005 余额 999999999.99（接近 10 亿）。",
        rows_bal=rows_bal,
        rows_tag=rows_tag,
    ))

    # 3) 另类 B：NULL 满天飞
    rows_bal, rows_tag = gen_edge_b_rows(rng)
    datasets.append(DatasetConfig(
        name="retail_deposit_edge_b",
        title="零售存款边界数据 B：NULL 满天飞",
        period_desc="本报告分析 2024 年 1 月至 4 月零售存款边界数据，"
                    "数据集刻意在金额、机构、标志列留有 NULL，含一条除主键外全 NULL 的空记录。",
        note="另类 B：NULL 满天飞。5 客户 × 4 月 = 20 行。"
             "CUST000001 Deposit_Bal NULL；CUST000002 Cust_Open_Org_Id NULL；"
             "CUST000003 Belong_Branch_Id NULL；CUST000004 Ever_Hold_Deposit_ind NULL；"
             "CUST000005 除主键外全字段 NULL。",
        rows_bal=rows_bal,
        rows_tag=rows_tag,
    ))

    # 4) 另类 C：分布异常
    rows_bal, rows_tag = gen_edge_c_rows(rng)
    datasets.append(DatasetConfig(
        name="retail_deposit_edge_c",
        title="零售存款边界数据 C：分布异常",
        period_desc="本报告分析 2024 年 1 月至 4 月零售存款边界数据，"
                    "数据集刻意制造分布异常：全员同一余额、某月全员 0、全员同业。",
        note="另类 C：分布异常。5 客户 × 4 月 = 20 行。"
             "全员余额 100 万；3 月全员余额 0；所有客户 Cust_Type 都是同业。",
        rows_bal=rows_bal,
        rows_tag=rows_tag,
    ))

    # 5) 另类 D：关联断裂/重复
    rows_bal, rows_tag = gen_edge_d_rows(rng)
    datasets.append(DatasetConfig(
        name="retail_deposit_edge_d",
        title="零售存款边界数据 D：关联断裂与重复",
        period_desc="本报告分析零售存款边界数据，"
                    "数据集刻意制造两表关联断裂、同客户同日期多条、客户号格式混乱。",
        note="另类 D：关联断裂/重复。约 30 行。"
             "CUST000001 只在 bal 表；CUST000002 只在 tag 表；"
             "CUST000003 在 2024-02 有 2 条（破坏 PK，故本数据集 schema 不设主键）；"
             "CUST000004 vs CUST0004（少 0）；cust-001 vs CUST-001（大小写+连字符混乱）。",
        rows_bal=rows_bal,
        rows_tag=rows_tag,
        with_pk=False,
    ))

    # 6) 另类 E：时间异常
    rows_bal, rows_tag = gen_edge_e_rows(rng)
    datasets.append(DatasetConfig(
        name="retail_deposit_edge_e",
        title="零售存款边界数据 E：时间异常",
        period_desc="本报告分析零售存款边界数据，"
                    "数据集刻意制造时间异常：所有日期相同、跨年、未来日期、余额单调增长。",
        note="另类 E：时间异常。约 20 行。"
             "CUST000001 所有行 Statistics_Dt 都是 2024-06-15（同一天）；"
             "CUST000002 跨年 2023-12 ~ 2024-03；CUST000003 未来日期 2026-01 ~ 2026-04；"
             "CUST000004/005 余额单调增长（验证模型会不会无脑套'稳步增长'套话）。",
        rows_bal=rows_bal,
        rows_tag=rows_tag,
    ))

    all_files = []
    for cfg in datasets:
        files = gen_dataset(cfg)
        all_files.extend(files)
        print(f"[OK] {cfg.name}: {len(cfg.rows_bal)} bal + {len(cfg.rows_tag)} tag rows")
    print(f"\n生成完成，共 {len(all_files)} 个文件，写入 {HERE}")
    for f in all_files:
        print(f"  - {f.name}")


if __name__ == "__main__":
    main()
