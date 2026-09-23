# 零售存款边界数据 E：时间异常：参考 SQL 与标准答案

数据集：`retail_deposit_edge_e`

另类 E：时间异常。约 20 行。CUST000001 所有行 Statistics_Dt 都是 2024-06-15（同一天）；CUST000002 跨年 2023-12 ~ 2024-03；CUST000003 未来日期 2026-01 ~ 2026-04；CUST000004/005 余额单调增长（验证模型会不会无脑套'稳步增长'套话）。

## 准备

```bash
mysql -u root -p < backend/example/retail_deposit_edge_e_schema.sql

# 只读账号
mysql -u root -p -e "
CREATE USER IF NOT EXISTS 'report_ro'@'%' IDENTIFIED BY 'ReadOnly@2024';
GRANT SELECT ON RTL_REPORT_TEST.* TO 'report_ro'@'%';
FLUSH PRIVILEGES;"
```

## 数据概况

- RTL_CUST_AST_MGT_BAL：20 行
- RTL_CUST_BEHAVIOR_TAG：20 行

## shape 约定

**`value` 型按位置解析：最后一列是数值，它前面的所有列都被当成维度。**单值指标要么只 SELECT 一列，要么把维度放在前面。

## 一章参考 SQL

本章为纯文字章节，不应产生追问。

## 二章参考 SQL

| 指标 | shape | 参考 SQL | 标准答案 |
|---|---|---|---|
| 存款余额合计 | value | `SELECT SUM(Deposit_Bal) FROM RTL_CUST_AST_MGT_BAL` | 1180000.00 |
| 客户数(去重) | value | `SELECT COUNT(DISTINCT Cust_Id) FROM RTL_CUST_AST_MGT_BAL` | 5 |
| 户均(按记录) | value | `SELECT ROUND(AVG(Deposit_Bal),2) FROM RTL_CUST_AST_MGT_BAL` | 59000.00 |
| 户均(按去重客户) | value | `SELECT ROUND(SUM(Deposit_Bal)/COUNT(DISTINCT Cust_Id),2) FROM RTL_CUST_AST_MGT_BAL` | 236000.00 |
| 月日均合计 | value | `SELECT SUM(Avg_Bal) FROM RTL_CUST_AST_MGT_BAL` | 1121000.00 |

## 三章参考 SQL

| 指标 | shape | 参考 SQL | 标准答案 |
|---|---|---|---|
| 客户类型分布 | table | `SELECT COALESCE(Cust_Type,'(空值)') AS t, COUNT(*) AS cnt, SUM(Deposit_Bal) AS bal FROM RTL_CUST_AST_MGT_BAL GROUP BY 1 ORDER BY bal DESC` | \| 客户类型 \| 客户数 \| 存款余额 \|\n\|---\|---\|---\|\n\| 个人 \| 20 \| 1180000.00 \| 占比 100.00%\n |
| 产品分布 | table | `SELECT COALESCE(Deposit_Product,'(空值)') AS p, COUNT(*) AS cnt, SUM(Deposit_Bal) AS bal FROM RTL_CUST_AST_MGT_BAL GROUP BY 1 ORDER BY bal DESC` | 见下表 |

## 四章参考 SQL

| 指标 | shape | 参考 SQL | 标准答案 |
|---|---|---|---|
| 月度趋势 | table | `SELECT Statistics_Dt, COUNT(*) AS cnt, SUM(Deposit_Bal) AS bal, SUM(Avg_Bal) AS avg FROM RTL_CUST_AST_MGT_BAL GROUP BY Statistics_Dt ORDER BY Statistics_Dt` | \| 统计日期 \| 客户数 \| 存款余额 \| 月日均 \| 环比 \|\n\|---\|---\|---\|---\|---\|\n\| 2023-12-15 \| 1 \| 80000.00 \| 76000.00 \| —\n\| 2024-01-15 \| 3 \| 110000.00 \| 104500.00 \| 37.50%\n\| 2024-02-15 \| 3 \| 140000.00 \| 133000.00 \| 27.27%\n\| 2024-03-15 \| 3 \| 170000.00 \| 161500.00 \| 21.43%\n\| 2024-04-15 \| 2 \| 100000.00 \| 95000.00 \| -41.18%\n\| 2024-06-15 \| 4 \| 100000.00 \| 95000.00 \| 0.00%\n\| 2026-01-15 \| 1 \| 120000.00 \| 114000.00 \| 20.00%\n\| 2026-02-15 \| 1 \| 120000.00 \| 114000.00 \| 0.00%\n\| 2026-03-15 \| 1 \| 120000.00 \| 114000.00 \| 0.00%\n\| 2026-04-15 \| 1 \| 120000.00 \| 114000.00 \| 0.00%\n |

## 五章参考 SQL

| 指标 | shape | 参考 SQL | 标准答案 |
|---|---|---|---|
| 分行分布 | table | `SELECT COALESCE(Belong_Branch_Id,'(空值)') AS br, COALESCE(Region,'(空值)') AS rg, COUNT(*) AS cnt, SUM(Deposit_Bal) AS bal FROM RTL_CUST_AST_MGT_BAL GROUP BY 1,2 ORDER BY bal DESC` | \| 分行 \| 区域 \| 客户数 \| 存款余额 \| 户均 \|\n\|---\|---\|---\|---\|---\|\n\| BR003 \| 华北 \| 4 \| 480000.00 \| 120000.00\n\| BR002 \| 华南 \| 4 \| 350000.00 \| 87500.00\n\| BR005 \| 东北 \| 4 \| 150000.00 \| 37500.00\n\| BR001 \| 华东 \| 4 \| 100000.00 \| 25000.00\n\| BR004 \| 西部 \| 4 \| 100000.00 \| 25000.00\n |

## 六章参考 SQL

| 指标 | shape | 参考 SQL | 标准答案 |
|---|---|---|---|
| 高净值客户数(余额≥100万) | value | `SELECT COUNT(DISTINCT Cust_Id) FROM RTL_CUST_AST_MGT_BAL WHERE Deposit_Bal>=1000000` | 0 |
| 高净值存款合计 | value | `SELECT SUM(Deposit_Bal) FROM RTL_CUST_AST_MGT_BAL WHERE Deposit_Bal>=1000000` | 0.00 |
| 高净值占比 | value | `SELECT ROUND(SUM(CASE WHEN Deposit_Bal>=1000000 THEN Deposit_Bal ELSE 0 END)/SUM(Deposit_Bal)*100,2) FROM RTL_CUST_AST_MGT_BAL` | 0.00% |
| 持有标志分布(JOIN后) | table | `SELECT COALESCE(b.Ever_Hold_Deposit_ind,'(空值)') AS flag, COUNT(*) AS cnt, SUM(a.Deposit_Bal) AS bal FROM RTL_CUST_AST_MGT_BAL a LEFT JOIN RTL_CUST_BEHAVIOR_TAG b ON a.Statistics_Dt=b.Statistics_Dt AND a.Cust_Id=b.Cust_Id GROUP BY 1 ORDER BY bal DESC` | \| 持有标志 \| 客户数 \| 存款余额 \|\n\|---\|---\|---\|\n\| YES \| 20 \| 1180000.00\n |
| 新进资金分布 | value | `SELECT New_Fund_Flag, COUNT(*) FROM RTL_CUST_BEHAVIOR_TAG GROUP BY 1` | NO: 16, YES: 4 |
