-- 零售存款测试库：给"追问后补充 SQL 数据"这条路径做的夹具。
--
-- 这个库不是报告的取数源，而是**追问的应答源**。章节 agent 在研究阶段只读会话
-- 附带的 dataset，读不到已保存的连接；连接只在用户回答追问时被 _resolve_by_sql
-- 执行。所以测试方式是：只上传模板不传数据 → 每个带指标的章节都停下来问 →
-- 在问题卡里选这个连接、写 SQL 把数取回来。
--
-- 建库：
--   mysql -u root -p < backend/example/retail_deposit_schema.sql
--
-- 表结构来自需求文档。文档里写的是 PostgreSQL 的 COMMENT ON 语法，MySQL 不认，
-- 这里转成内联 COMMENT；NUMERIC 换成等价的 DECIMAL。数据逐行照抄，未作改动。

CREATE DATABASE IF NOT EXISTS RTL_REPORT_TEST
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE RTL_REPORT_TEST;

DROP TABLE IF EXISTS RTL_CUST_BEHAVIOR_TAG;
DROP TABLE IF EXISTS RTL_CUST_AST_MGT_BAL;

-- 零售客户行为标签表
CREATE TABLE RTL_CUST_BEHAVIOR_TAG (
  Statistics_Dt         DATE         NOT NULL               COMMENT '统计日期',
  Cust_Id               VARCHAR(150) NOT NULL               COMMENT '客户号',
  Ever_Hold_Deposit_ind VARCHAR(3)                          COMMENT '历史客户存款类产品购买标志(YES/NO/空值)',
  -- 统计日期 + 客户号唯一标识一条记录
  PRIMARY KEY (Statistics_Dt, Cust_Id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='零售客户行为标签表';

-- 零售客户资产管理余额表
CREATE TABLE RTL_CUST_AST_MGT_BAL (
  Statistics_Dt    DATE           NOT NULL                  COMMENT '统计日期',
  Cust_Id          VARCHAR(150)   NOT NULL                  COMMENT '客户号',
  Cust_Open_Org_Id VARCHAR(150)                             COMMENT '客户开户机构',
  Belong_Org_Id    VARCHAR(150)                             COMMENT '客户归属机构编号',
  Belong_Branch_Id VARCHAR(150)                             COMMENT '客户归属机构分行编号',
  Deposit_Bal      DECIMAL(18,2)                            COMMENT '存款余额',
  -- 统计日期 + 客户号唯一标识一条记录
  PRIMARY KEY (Statistics_Dt, Cust_Id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='零售客户资产管理余额表';

-- 行为标签，20 条
INSERT INTO RTL_CUST_BEHAVIOR_TAG (Statistics_Dt, Cust_Id, Ever_Hold_Deposit_ind) VALUES
  ('2024-01-15', 'CUST000001', 'YES'),
  ('2024-01-15', 'CUST000002', 'NO'),
  ('2024-01-15', 'CUST000003', 'YES'),
  ('2024-01-15', 'CUST000004', NULL),
  ('2024-01-15', 'CUST000005', 'YES'),
  ('2024-02-15', 'CUST000001', 'YES'),
  ('2024-02-15', 'CUST000006', 'NO'),
  ('2024-02-15', 'CUST000007', 'YES'),
  ('2024-02-15', 'CUST000008', 'YES'),
  ('2024-02-15', 'CUST000009', NULL),
  ('2024-03-15', 'CUST000010', 'NO'),
  ('2024-03-15', 'CUST000011', 'YES'),
  ('2024-03-15', 'CUST000012', 'YES'),
  ('2024-03-15', 'CUST000013', 'NO'),
  ('2024-03-15', 'CUST000014', 'YES'),
  ('2024-04-15', 'CUST000015', NULL),
  ('2024-04-15', 'CUST000016', 'YES'),
  ('2024-04-15', 'CUST000017', 'NO'),
  ('2024-04-15', 'CUST000018', 'YES'),
  ('2024-04-15', 'CUST000019', 'YES');

-- 资产余额，20 条。客户号与行为标签表逐行对齐，两表可按
-- (Statistics_Dt, Cust_Id) 无损内连接。
INSERT INTO RTL_CUST_AST_MGT_BAL (Statistics_Dt, Cust_Id, Cust_Open_Org_Id, Belong_Org_Id, Belong_Branch_Id, Deposit_Bal) VALUES
  -- 2024 年 1 月，5 条
  ('2024-01-15', 'CUST000001', 'ORG001', 'ORG001', 'BR001', 150000.50),
  ('2024-01-15', 'CUST000002', 'ORG002', 'ORG002', 'BR002', 50000.00),
  ('2024-01-15', 'CUST000003', 'ORG001', 'ORG001', 'BR003', 2800000.75),
  ('2024-01-15', 'CUST000004', 'ORG003', 'ORG003', 'BR004', 3200.00),
  ('2024-01-15', 'CUST000005', 'ORG002', 'ORG002', 'BR002', 1000000.00),
  -- 2024 年 2 月，5 条，含一个重复客户 CUST000001
  ('2024-02-15', 'CUST000001', 'ORG001', 'ORG001', 'BR001', 155000.00),
  ('2024-02-15', 'CUST000006', 'ORG004', 'ORG004', 'BR005', 88000.30),
  ('2024-02-15', 'CUST000007', 'ORG001', 'ORG002', 'BR002', 500000.00),
  ('2024-02-15', 'CUST000008', 'ORG003', 'ORG003', 'BR006', 12500.00),
  ('2024-02-15', 'CUST000009', 'ORG002', 'ORG002', 'BR003', 999999.99),
  -- 2024 年 3 月，5 条
  ('2024-03-15', 'CUST000010', 'ORG005', 'ORG005', 'BR007', 0.00),
  ('2024-03-15', 'CUST000011', 'ORG001', 'ORG001', 'BR001', 350000.00),
  ('2024-03-15', 'CUST000012', 'ORG002', 'ORG003', 'BR004', 78200.50),
  ('2024-03-15', 'CUST000013', 'ORG003', 'ORG003', 'BR006', 1500.00),
  ('2024-03-15', 'CUST000014', 'ORG004', 'ORG004', 'BR005', 6200000.00),
  -- 2024 年 4 月，5 条
  ('2024-04-15', 'CUST000015', 'ORG001', 'ORG001', 'BR003', 45000.25),
  ('2024-04-15', 'CUST000016', 'ORG005', 'ORG005', 'BR007', 210000.00),
  ('2024-04-15', 'CUST000017', 'ORG002', 'ORG002', 'BR002', 8900.00),
  ('2024-04-15', 'CUST000018', 'ORG003', 'ORG003', 'BR004', 1750000.00),
  ('2024-04-15', 'CUST000019', 'ORG004', 'ORG004', 'BR006', 36000.00);
