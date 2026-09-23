# 小规模测试数据：参考 SQL 与标准答案

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
| BR01 | 4 | 6400000 |
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
