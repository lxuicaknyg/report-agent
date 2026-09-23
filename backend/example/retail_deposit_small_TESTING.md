# 零售客户存款经营分析报告：参考 SQL 与标准答案

数据集：`retail_deposit_small`

正常数据集：25 客户 × 12 月 = 300 行。二八分布（5 大客户 + 15 普通 + 5 小额），3/6/9/12 月季末冲量，大客户有持续增长/衰减/突然大额转入/周期波动四种趋势。

## 准备

```bash
mysql -u root -p < backend/example/retail_deposit_small_schema.sql

# 只读账号
mysql -u root -p -e "
CREATE USER IF NOT EXISTS 'report_ro'@'%' IDENTIFIED BY 'ReadOnly@2024';
GRANT SELECT ON RTL_REPORT_TEST.* TO 'report_ro'@'%';
FLUSH PRIVILEGES;"
```

## 数据概况

- RTL_CUST_AST_MGT_BAL：300 行
- RTL_CUST_BEHAVIOR_TAG：300 行

## shape 约定

**`value` 型按位置解析：最后一列是数值，它前面的所有列都被当成维度。**单值指标要么只 SELECT 一列，要么把维度放在前面。

## 一章参考 SQL

本章为纯文字章节，不应产生追问。

## 二章参考 SQL

| 指标 | shape | 参考 SQL | 标准答案 |
|---|---|---|---|
| 存款余额合计 | value | `SELECT SUM(Deposit_Bal) FROM RTL_CUST_AST_MGT_BAL` | 741317306.75 |
| 客户数(去重) | value | `SELECT COUNT(DISTINCT Cust_Id) FROM RTL_CUST_AST_MGT_BAL` | 25 |
| 户均(按记录) | value | `SELECT ROUND(AVG(Deposit_Bal),2) FROM RTL_CUST_AST_MGT_BAL` | 2471057.69 |
| 户均(按去重客户) | value | `SELECT ROUND(SUM(Deposit_Bal)/COUNT(DISTINCT Cust_Id),2) FROM RTL_CUST_AST_MGT_BAL` | 29652692.27 |
| 月日均合计 | value | `SELECT SUM(Avg_Bal) FROM RTL_CUST_AST_MGT_BAL` | 703362561.91 |

## 三章参考 SQL

| 指标 | shape | 参考 SQL | 标准答案 |
|---|---|---|---|
| 客户类型分布 | table | `SELECT COALESCE(Cust_Type,'(空值)') AS t, COUNT(*) AS cnt, SUM(Deposit_Bal) AS bal FROM RTL_CUST_AST_MGT_BAL GROUP BY 1 ORDER BY bal DESC` | \| 客户类型 \| 客户数 \| 存款余额 \|\n\|---\|---\|---\|\n\| 同业 \| 24 \| 326254047.43 \| 占比 44.01%\n\| 对公 \| 24 \| 263434305.00 \| 占比 35.54%\n\| 个人 \| 252 \| 151628954.32 \| 占比 20.45%\n |
| 产品分布 | table | `SELECT COALESCE(Deposit_Product,'(空值)') AS p, COUNT(*) AS cnt, SUM(Deposit_Bal) AS bal FROM RTL_CUST_AST_MGT_BAL GROUP BY 1 ORDER BY bal DESC` | 见下表 |

## 四章参考 SQL

| 指标 | shape | 参考 SQL | 标准答案 |
|---|---|---|---|
| 月度趋势 | table | `SELECT Statistics_Dt, COUNT(*) AS cnt, SUM(Deposit_Bal) AS bal, SUM(Avg_Bal) AS avg FROM RTL_CUST_AST_MGT_BAL GROUP BY Statistics_Dt ORDER BY Statistics_Dt` | \| 统计日期 \| 客户数 \| 存款余额 \| 月日均 \| 环比 \|\n\|---\|---\|---\|---\|---\|\n\| 2024-01-15 \| 25 \| 57185039.34 \| 55251931.14 \| —\n\| 2024-02-15 \| 25 \| 57432926.87 \| 53547385.27 \| 0.43%\n\| 2024-03-15 \| 25 \| 65141006.80 \| 61726249.23 \| 13.42%\n\| 2024-04-15 \| 25 \| 58082149.40 \| 54484841.28 \| -10.84%\n\| 2024-05-15 \| 25 \| 58279297.02 \| 54821597.69 \| 0.34%\n\| 2024-06-15 \| 25 \| 87259285.71 \| 82114312.17 \| 49.73%\n\| 2024-07-15 \| 25 \| 57743573.56 \| 54595849.67 \| -33.83%\n\| 2024-08-15 \| 25 \| 57285652.81 \| 53744134.25 \| -0.79%\n\| 2024-09-15 \| 25 \| 62647082.57 \| 60100312.38 \| 9.36%\n\| 2024-10-15 \| 25 \| 56432790.51 \| 54343255.88 \| -9.92%\n\| 2024-11-15 \| 25 \| 56333379.34 \| 53306219.05 \| -0.18%\n\| 2024-12-15 \| 25 \| 67495122.82 \| 65326473.90 \| 19.81%\n |

## 五章参考 SQL

| 指标 | shape | 参考 SQL | 标准答案 |
|---|---|---|---|
| 分行分布 | table | `SELECT COALESCE(Belong_Branch_Id,'(空值)') AS br, COALESCE(Region,'(空值)') AS rg, COUNT(*) AS cnt, SUM(Deposit_Bal) AS bal FROM RTL_CUST_AST_MGT_BAL GROUP BY 1,2 ORDER BY bal DESC` | \| 分行 \| 区域 \| 客户数 \| 存款余额 \| 户均 \|\n\|---\|---\|---\|---\|---\|\n\| BR001 \| 华东 \| 60 \| 195282404.09 \| 3254706.73\n\| BR004 \| 西部 \| 60 \| 186183205.21 \| 3103053.42\n\| BR003 \| 华北 \| 60 \| 165821217.83 \| 2763686.96\n\| BR002 \| 华南 \| 60 \| 102465490.76 \| 1707758.18\n\| BR005 \| 东北 \| 60 \| 91564988.86 \| 1526083.15\n |

## 六章参考 SQL

| 指标 | shape | 参考 SQL | 标准答案 |
|---|---|---|---|
| 高净值客户数(余额≥100万) | value | `SELECT COUNT(DISTINCT Cust_Id) FROM RTL_CUST_AST_MGT_BAL WHERE Deposit_Bal>=1000000` | 9 |
| 高净值存款合计 | value | `SELECT SUM(Deposit_Bal) FROM RTL_CUST_AST_MGT_BAL WHERE Deposit_Bal>=1000000` | 664007794.32 |
| 高净值占比 | value | `SELECT ROUND(SUM(CASE WHEN Deposit_Bal>=1000000 THEN Deposit_Bal ELSE 0 END)/SUM(Deposit_Bal)*100,2) FROM RTL_CUST_AST_MGT_BAL` | 89.57% |
| 持有标志分布(JOIN后) | table | `SELECT COALESCE(b.Ever_Hold_Deposit_ind,'(空值)') AS flag, COUNT(*) AS cnt, SUM(a.Deposit_Bal) AS bal FROM RTL_CUST_AST_MGT_BAL a LEFT JOIN RTL_CUST_BEHAVIOR_TAG b ON a.Statistics_Dt=b.Statistics_Dt AND a.Cust_Id=b.Cust_Id GROUP BY 1 ORDER BY bal DESC` | \| 持有标志 \| 客户数 \| 存款余额 \|\n\|---\|---\|---\|\n\| YES \| 179 \| 681478114.69\n\| NO \| 121 \| 59839192.06\n |
| 新进资金分布 | value | `SELECT New_Fund_Flag, COUNT(*) FROM RTL_CUST_BEHAVIOR_TAG GROUP BY 1` | NO: 200, YES: 100 |
