# 零售存款边界数据 A：零值与极端值：参考 SQL 与标准答案

数据集：`retail_deposit_edge_a`

另类 A：全员零值/极端值。5 客户 × 4 月 = 20 行。CUST000001 余额 0；CUST000002 余额 -5 万（负数）；CUST000003 余额 10 亿；CUST000004 Excel 余额 1234.567891（6 位小数），SQL 截断为 1234.57；CUST000005 余额 999999999.99（接近 10 亿）。

## 准备

```bash
mysql -u root -p < backend/example/retail_deposit_edge_a_schema.sql

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
| 存款余额合计 | value | `SELECT SUM(Deposit_Bal) FROM RTL_CUST_AST_MGT_BAL` | 7999804938.23 |
| 客户数(去重) | value | `SELECT COUNT(DISTINCT Cust_Id) FROM RTL_CUST_AST_MGT_BAL` | 5 |
| 户均(按记录) | value | `SELECT ROUND(AVG(Deposit_Bal),2) FROM RTL_CUST_AST_MGT_BAL` | 399990246.91 |
| 户均(按去重客户) | value | `SELECT ROUND(SUM(Deposit_Bal)/COUNT(DISTINCT Cust_Id),2) FROM RTL_CUST_AST_MGT_BAL` | 1599960987.65 |
| 月日均合计 | value | `SELECT SUM(Avg_Bal) FROM RTL_CUST_AST_MGT_BAL` | 7999804938.23 |

## 三章参考 SQL

| 指标 | shape | 参考 SQL | 标准答案 |
|---|---|---|---|
| 客户类型分布 | table | `SELECT COALESCE(Cust_Type,'(空值)') AS t, COUNT(*) AS cnt, SUM(Deposit_Bal) AS bal FROM RTL_CUST_AST_MGT_BAL GROUP BY 1 ORDER BY bal DESC` | \| 客户类型 \| 客户数 \| 存款余额 \|\n\|---\|---\|---\|\n\| 个人 \| 8 \| 4000004938.23 \| 占比 50.00%\n\| 同业 \| 4 \| 4000000000.00 \| 占比 50.00%\n\| 对公 \| 8 \| -200000.00 \| 占比 -0.00%\n |
| 产品分布 | table | `SELECT COALESCE(Deposit_Product,'(空值)') AS p, COUNT(*) AS cnt, SUM(Deposit_Bal) AS bal FROM RTL_CUST_AST_MGT_BAL GROUP BY 1 ORDER BY bal DESC` | 见下表 |

## 四章参考 SQL

| 指标 | shape | 参考 SQL | 标准答案 |
|---|---|---|---|
| 月度趋势 | table | `SELECT Statistics_Dt, COUNT(*) AS cnt, SUM(Deposit_Bal) AS bal, SUM(Avg_Bal) AS avg FROM RTL_CUST_AST_MGT_BAL GROUP BY Statistics_Dt ORDER BY Statistics_Dt` | \| 统计日期 \| 客户数 \| 存款余额 \| 月日均 \| 环比 \|\n\|---\|---\|---\|---\|---\|\n\| 2024-01-15 \| 5 \| 1999951234.56 \| 1999951234.56 \| —\n\| 2024-02-15 \| 5 \| 1999951234.56 \| 1999951234.56 \| 0.00%\n\| 2024-03-15 \| 5 \| 1999951234.56 \| 1999951234.56 \| 0.00%\n\| 2024-04-15 \| 5 \| 1999951234.56 \| 1999951234.56 \| 0.00%\n |

## 五章参考 SQL

| 指标 | shape | 参考 SQL | 标准答案 |
|---|---|---|---|
| 分行分布 | table | `SELECT COALESCE(Belong_Branch_Id,'(空值)') AS br, COALESCE(Region,'(空值)') AS rg, COUNT(*) AS cnt, SUM(Deposit_Bal) AS bal FROM RTL_CUST_AST_MGT_BAL GROUP BY 1,2 ORDER BY bal DESC` | \| 分行 \| 区域 \| 客户数 \| 存款余额 \| 户均 \|\n\|---\|---\|---\|---\|---\|\n\| BR003 \| 华北 \| 4 \| 4000000000.00 \| 1000000000.00\n\| BR005 \| 东北 \| 4 \| 3999999999.96 \| 999999999.99\n\| BR004 \| 西部 \| 4 \| 4938.27 \| 1234.57\n\| BR001 \| 华东 \| 4 \| 0.00 \| 0.00\n\| BR002 \| 华南 \| 4 \| -200000.00 \| -50000.00\n |

## 六章参考 SQL

| 指标 | shape | 参考 SQL | 标准答案 |
|---|---|---|---|
| 高净值客户数(余额≥100万) | value | `SELECT COUNT(DISTINCT Cust_Id) FROM RTL_CUST_AST_MGT_BAL WHERE Deposit_Bal>=1000000` | 2 |
| 高净值存款合计 | value | `SELECT SUM(Deposit_Bal) FROM RTL_CUST_AST_MGT_BAL WHERE Deposit_Bal>=1000000` | 7999999999.96 |
| 高净值占比 | value | `SELECT ROUND(SUM(CASE WHEN Deposit_Bal>=1000000 THEN Deposit_Bal ELSE 0 END)/SUM(Deposit_Bal)*100,2) FROM RTL_CUST_AST_MGT_BAL` | 100.00% |
| 持有标志分布(JOIN后) | table | `SELECT COALESCE(b.Ever_Hold_Deposit_ind,'(空值)') AS flag, COUNT(*) AS cnt, SUM(a.Deposit_Bal) AS bal FROM RTL_CUST_AST_MGT_BAL a LEFT JOIN RTL_CUST_BEHAVIOR_TAG b ON a.Statistics_Dt=b.Statistics_Dt AND a.Cust_Id=b.Cust_Id GROUP BY 1 ORDER BY bal DESC` | \| 持有标志 \| 客户数 \| 存款余额 \|\n\|---\|---\|---\|\n\| YES \| 12 \| 7999999999.96\n\| NO \| 8 \| -195061.73\n |
| 新进资金分布 | value | `SELECT New_Fund_Flag, COUNT(*) FROM RTL_CUST_BEHAVIOR_TAG GROUP BY 1` | NO: 20 |
