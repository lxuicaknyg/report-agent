# 零售存款测试夹具：验证"追问 → 补充 SQL 数据"

这套夹具专门用来走通 `waiting_user` 那条路：章节取不到数 → 停下来提问 → 用户在问题卡里选连接写 SQL → `_resolve_by_sql` 重跑语句把数落到指标上 → 本章重写 → 继续下一章。

## 为什么是"只传模板、不传数据"

章节 agent 的取数阶段**读不到已保存的连接**，它只能用会话附带的 dataset（[chapter_writer_agent.py](../app/reporting/chapter_writer_agent.py)）。连接只在用户回答追问时被 [`_resolve_by_sql`](../app/reporting/report_generation.py) 执行。

而[只上传模板就足以开工](../app/conversations/orchestrator.py)，`dataset_ids` 允许为空。

两件事合起来：**只传模板不传 Excel，每个带指标的章节都必然停下来追问**。这是稳定触发，不是碰运气。

## 准备

```bash
# 1. 建库（含只读账号授权的说明见文件头）
mysql -u root -p < backend/example/retail_deposit_schema.sql

# 2. 建只读账号
mysql -u root -p -e "
CREATE USER IF NOT EXISTS 'report_ro'@'%' IDENTIFIED BY 'ReadOnly@2024';
GRANT SELECT ON RTL_REPORT_TEST.* TO 'report_ro'@'%';
FLUSH PRIVILEGES;"
```

然后在前端 `/connections` 页面新建连接（或用 `POST /api/v1/connections`）：

| 字段 | 值 |
|---|---|
| 名称 | 零售存款测试库 |
| 驱动 | MySQL |
| 主机 / 端口 | `127.0.0.1` / `3306` |
| 数据库 | `RTL_REPORT_TEST` |
| 账号 / 密码 | `report_ro` / `ReadOnly@2024` |

> 用只读账号而不是 root：连接的密码会明文存进 `STATE_DIR/connections.json`，而且驱动说明本身就写着"账号只需具备只读权限"。

## 测试步骤

1. 新建对话，**只上传** `retail_deposit_report_template.md`，不要传任何 Excel
2. 附一句指令，例如"生成 2024 年 1-4 月零售客户存款经营分析报告"
3. 等计划卡出来，确认是 6 章（正文 + 下表的 5 章），说"确认，开始生成"
4. 第二章开始就会停在 `waiting_user`，问题卡列出缺的指标
5. 在问题卡里选「零售存款测试库」，填下面的参考 SQL，选对 shape，提交
6. 本章重写完继续下一章，重复到报告完成

## 数据概况

两张表各 20 行，统计日期为 2024-01-15 / 02-15 / 03-15 / 04-15，每期 5 个客户。客户号在两表间逐行对齐，按 `(Statistics_Dt, Cust_Id)` 内连接无损（12 + 5 + 3 = 20）。

- `RTL_CUST_AST_MGT_BAL` — 存款余额，带开户机构 / 归属机构 / 分行编号
- `RTL_CUST_BEHAVIOR_TAG` — 历史存款类产品购买标志，取值 `YES` / `NO` / `NULL`

注意几个有意留下的边界：`CUST000001` 在 1 月和 2 月各出现一次（20 条记录、19 个去重客户）；`CUST000010` 余额为 `0.00`；`CUST000009` 余额 `999999.99` 差一分钱够不着 100 万；标志列有 3 个 `NULL`。

## 各章追问与参考答案

**shape 约定很重要**：`value` 型按位置解析 —— **最后一列是数值，它前面的所有列都被当成维度**。所以单值指标要么只 SELECT 一列，要么把维度放在前面。

### 一、报告说明

**不应该产生任何追问。** 这章是纯文字、无指标，用来验证"`metrics` 为空的叙述性章节不允许因缺数据提问"这条逻辑。如果它也停下来问了，那是 bug。

### 二、存款规模总览

| 指标 | shape | 参考 SQL | 标准答案 |
|---|---|---|---|
| 存款余额合计 | value | `SELECT SUM(Deposit_Bal) FROM RTL_CUST_AST_MGT_BAL` | `14438302.29` |
| 客户数 | value | `SELECT COUNT(DISTINCT Cust_Id) FROM RTL_CUST_AST_MGT_BAL` | `19` |
| 户均存款余额 | value | `SELECT ROUND(AVG(Deposit_Bal),2) FROM RTL_CUST_AST_MGT_BAL` | `721915.11` |

> 户均有两个口径，正好用来看模型会不会说清自己算的是哪个：按 20 条记录平均是 `721915.11`，按 19 个去重客户是 `759910.65`。

### 三、分行存款分布

| 指标 | shape | 参考 SQL |
|---|---|---|
| 分行存款分布 | **table** | `SELECT Belong_Branch_Id, COUNT(*) AS cust_cnt, SUM(Deposit_Bal) AS bal FROM RTL_CUST_AST_MGT_BAL GROUP BY Belong_Branch_Id ORDER BY bal DESC` |

标准答案（7 个分行）：

| 分行 | 客户数 | 存款余额 |
|---|---|---|
| BR005 | 2 | 6288000.30 |
| BR003 | 3 | 3845000.99 |
| BR004 | 3 | 1831400.50 |
| BR002 | 4 | 1558900.00 |
| BR001 | 3 | 655000.50 |
| BR007 | 2 | 210000.00 |
| BR006 | 3 | 50000.00 |

**存款余额最高的分行是 BR005。** 模板里那句"指出存款余额最高的分行"就是用来看模型会不会从表里读出结论，还是硬编一个。

### 四、存款类产品持有情况

这章要两表 join，是最容易写错 SQL 的一章。

| 指标 | shape | 参考 SQL | 标准答案 |
|---|---|---|---|
| 持有/未持有分布 | table | `SELECT COALESCE(b.Ever_Hold_Deposit_ind,'(空值)') AS flag, COUNT(*) AS cust_cnt, SUM(a.Deposit_Bal) AS bal, ROUND(AVG(a.Deposit_Bal),2) AS avg_bal FROM RTL_CUST_AST_MGT_BAL a JOIN RTL_CUST_BEHAVIOR_TAG b ON a.Statistics_Dt=b.Statistics_Dt AND a.Cust_Id=b.Cust_Id GROUP BY 1` | 见下 |

| 持有标志 | 客户数 | 存款余额 | 户均余额 |
|---|---|---|---|
| YES | 12 | 13241701.75 | 1103475.15 |
| NO | 5 | 148400.30 | 29680.06 |
| (空值) | 3 | 1048200.24 | 349400.08 |

持有率同样有两个口径：占全部 `60.00%`，剔除空值后 `70.59%`。空值怎么处理是这章的考点。

### 五、月度存款趋势

| 指标 | shape | 参考 SQL |
|---|---|---|
| 月度存款趋势 | **table** | `SELECT Statistics_Dt, COUNT(*) AS cust_cnt, SUM(Deposit_Bal) AS bal, ROUND(AVG(Deposit_Bal),2) AS avg_bal FROM RTL_CUST_AST_MGT_BAL GROUP BY Statistics_Dt ORDER BY Statistics_Dt` |

| 统计日期 | 客户数 | 存款余额 | 户均余额 |
|---|---|---|---|
| 2024-01-15 | 5 | 4003201.25 | 800640.25 |
| 2024-02-15 | 5 | 1755500.29 | 351100.06 |
| 2024-03-15 | 5 | 6629700.50 | 1325940.10 |
| 2024-04-15 | 5 | 2049900.25 | 409980.05 |

趋势不是单调的（降、升、降），避免模型靠"稳步增长"这种套话蒙混过关。

## 顺便可以测的其他路径

- **drop（不补了）**：任选一个指标点"跳过"。按设计，被丢弃的指标要完全离开计划，正文**既不能提它、也不能解释它为什么缺席**。
- **直接填值**：不走 SQL，手填一个数。填一个和上表对不上的数（比如存款合计填 `99999999`），看产物里是不是真用了你填的值 —— 这验证"写作阶段不重算指标"。
- **自动放弃**：同一章连续追问超过 `max_chapter_attempts` 轮后，指标会被自动移出报告并在 `resolved_questions` 里留痕。
- **高净值边界**：`SELECT COUNT(*), SUM(Deposit_Bal) FROM RTL_CUST_AST_MGT_BAL WHERE Deposit_Bal>=1000000` → `4` 户、`11750000.75`。`999999.99` 那条不该被算进去。
