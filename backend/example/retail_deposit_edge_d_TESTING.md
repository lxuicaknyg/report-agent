# 零售存款边界数据 D：关联断裂与重复：参考 SQL 与标准答案

数据集：`retail_deposit_edge_d`

另类 D：关联断裂/重复。约 30 行。CUST000001 只在 bal 表；CUST000002 只在 tag 表；CUST000003 在 2024-02 有 2 条（破坏 PK，故本数据集 schema 不设主键）；CUST000004 vs CUST0004（少 0）；cust-001 vs CUST-001（大小写+连字符混乱）。

## 准备

```bash
mysql -u root -p < backend/example/retail_deposit_edge_d_schema.sql

# 只读账号
mysql -u root -p -e "
CREATE USER IF NOT EXISTS 'report_ro'@'%' IDENTIFIED BY 'ReadOnly@2024';
GRANT SELECT ON RTL_REPORT_TEST.* TO 'report_ro'@'%';
FLUSH PRIVILEGES;"
```

## 数据概况

- RTL_CUST_AST_MGT_BAL：25 行
- RTL_CUST_BEHAVIOR_TAG：24 行

## shape 约定

**`value` 型按位置解析：最后一列是数值，它前面的所有列都被当成维度。**单值指标要么只 SELECT 一列，要么把维度放在前面。

## 一章参考 SQL

本章为纯文字章节，不应产生追问。

## 二章参考 SQL

| 指标 | shape | 参考 SQL | 标准答案 |
|---|---|---|---|
| 存款余额合计 | value | `SELECT SUM(Deposit_Bal) FROM RTL_CUST_AST_MGT_BAL` | 2130000.00 |
| 客户数(去重) | value | `SELECT COUNT(DISTINCT Cust_Id) FROM RTL_CUST_AST_MGT_BAL` | 6 |
| 户均(按记录) | value | `SELECT ROUND(AVG(Deposit_Bal),2) FROM RTL_CUST_AST_MGT_BAL` | 85200.00 |
| 户均(按去重客户) | value | `SELECT ROUND(SUM(Deposit_Bal)/COUNT(DISTINCT Cust_Id),2) FROM RTL_CUST_AST_MGT_BAL` | 355000.00 |
| 月日均合计 | value | `SELECT SUM(Avg_Bal) FROM RTL_CUST_AST_MGT_BAL` | 2023500.00 |

## 三章参考 SQL

| 指标 | shape | 参考 SQL | 标准答案 |
|---|---|---|---|
| 客户类型分布 | table | `SELECT COALESCE(Cust_Type,'(空值)') AS t, COUNT(*) AS cnt, SUM(Deposit_Bal) AS bal FROM RTL_CUST_AST_MGT_BAL GROUP BY 1 ORDER BY bal DESC` | \| 客户类型 \| 客户数 \| 存款余额 \|\n\|---\|---\|---\|\n\| 个人 \| 25 \| 2130000.00 \| 占比 100.00%\n |
| 产品分布 | table | `SELECT COALESCE(Deposit_Product,'(空值)') AS p, COUNT(*) AS cnt, SUM(Deposit_Bal) AS bal FROM RTL_CUST_AST_MGT_BAL GROUP BY 1 ORDER BY bal DESC` | 见下表 |

## 四章参考 SQL

| 指标 | shape | 参考 SQL | 标准答案 |
|---|---|---|---|
| 月度趋势 | table | `SELECT Statistics_Dt, COUNT(*) AS cnt, SUM(Deposit_Bal) AS bal, SUM(Avg_Bal) AS avg FROM RTL_CUST_AST_MGT_BAL GROUP BY Statistics_Dt ORDER BY Statistics_Dt` | \| 统计日期 \| 客户数 \| 存款余额 \| 月日均 \| 环比 \|\n\|---\|---\|---\|---\|---\|\n\| 2024-01-15 \| 6 \| 470000.00 \| 446500.00 \| —\n\| 2024-02-15 \| 7 \| 720000.00 \| 684000.00 \| 53.19%\n\| 2024-03-15 \| 6 \| 470000.00 \| 446500.00 \| -34.72%\n\| 2024-04-15 \| 6 \| 470000.00 \| 446500.00 \| 0.00%\n |

## 五章参考 SQL

| 指标 | shape | 参考 SQL | 标准答案 |
|---|---|---|---|
| 分行分布 | table | `SELECT COALESCE(Belong_Branch_Id,'(空值)') AS br, COALESCE(Region,'(空值)') AS rg, COUNT(*) AS cnt, SUM(Deposit_Bal) AS bal FROM RTL_CUST_AST_MGT_BAL GROUP BY 1,2 ORDER BY bal DESC` | \| 分行 \| 区域 \| 客户数 \| 存款余额 \| 户均 \|\n\|---\|---\|---\|---\|---\|\n\| BR002 \| 华南 \| 5 \| 1050000.00 \| 210000.00\n\| BR003 \| 华北 \| 8 \| 640000.00 \| 80000.00\n\| BR004 \| 西部 \| 8 \| 240000.00 \| 30000.00\n\| BR001 \| 华东 \| 4 \| 200000.00 \| 50000.00\n |

## 六章参考 SQL

| 指标 | shape | 参考 SQL | 标准答案 |
|---|---|---|---|
| 高净值客户数(余额≥100万) | value | `SELECT COUNT(DISTINCT Cust_Id) FROM RTL_CUST_AST_MGT_BAL WHERE Deposit_Bal>=1000000` | 0 |
| 高净值存款合计 | value | `SELECT SUM(Deposit_Bal) FROM RTL_CUST_AST_MGT_BAL WHERE Deposit_Bal>=1000000` | 0.00 |
| 高净值占比 | value | `SELECT ROUND(SUM(CASE WHEN Deposit_Bal>=1000000 THEN Deposit_Bal ELSE 0 END)/SUM(Deposit_Bal)*100,2) FROM RTL_CUST_AST_MGT_BAL` | 0.00% |
| 持有标志分布(JOIN后) | table | `SELECT COALESCE(b.Ever_Hold_Deposit_ind,'(空值)') AS flag, COUNT(*) AS cnt, SUM(a.Deposit_Bal) AS bal FROM RTL_CUST_AST_MGT_BAL a LEFT JOIN RTL_CUST_BEHAVIOR_TAG b ON a.Statistics_Dt=b.Statistics_Dt AND a.Cust_Id=b.Cust_Id GROUP BY 1 ORDER BY bal DESC` | \| 持有标志 \| 客户数 \| 存款余额 \|\n\|---\|---\|---\|\n\| YES \| 17 \| 1810000.00\n\| (无标签) \| 4 \| 200000.00\n\| NO \| 4 \| 120000.00\n |
| 新进资金分布 | value | `SELECT New_Fund_Flag, COUNT(*) FROM RTL_CUST_BEHAVIOR_TAG GROUP BY 1` | NO: 24 |
