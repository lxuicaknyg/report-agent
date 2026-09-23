-- 零售存款边界数据 D：关联断裂与重复
-- 数据集：retail_deposit_edge_d
-- 另类 D：关联断裂/重复。约 30 行。CUST000001 只在 bal 表；CUST000002 只在 tag 表；CUST000003 在 2024-02 有 2 条（破坏 PK，故本数据集 schema 不设主键）；CUST000004 vs CUST0004（少 0）；cust-001 vs CUST-001（大小写+连字符混乱）。

-- 建库：
--   mysql -u root -p < retail_deposit_edge_d_schema.sql

CREATE DATABASE IF NOT EXISTS RTL_REPORT_TEST
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE RTL_REPORT_TEST;

DROP TABLE IF EXISTS RTL_CUST_BEHAVIOR_TAG;
DROP TABLE IF EXISTS RTL_CUST_AST_MGT_BAL;

-- 零售客户资产管理余额表
CREATE TABLE RTL_CUST_AST_MGT_BAL (
  Statistics_Dt          DATE NOT NULL                  COMMENT '统计日期',
  Cust_Id                VARCHAR(150) NOT NULL          COMMENT '客户号',
  Cust_Open_Org_Id       VARCHAR(150)                   COMMENT '客户开户机构',
  Belong_Org_Id          VARCHAR(150)                   COMMENT '客户归属机构编号',
  Belong_Branch_Id       VARCHAR(150)                   COMMENT '客户归属机构分行编号',
  Deposit_Bal            DECIMAL(18,2)                  COMMENT '存款余额',
  Cust_Type              VARCHAR(30)                    COMMENT '客户类型(个人/对公/同业)',
  Region                 VARCHAR(30)                    COMMENT '客户所属区域',
  Deposit_Product        VARCHAR(60)                    COMMENT '存款产品',
  Avg_Bal                DECIMAL(18,2)                  COMMENT '月日均余额',
  Rate_Band              VARCHAR(30)                    COMMENT '利率档位'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='零售客户资产管理余额表';

-- 零售客户行为标签表
CREATE TABLE RTL_CUST_BEHAVIOR_TAG (
  Statistics_Dt          DATE NOT NULL                  COMMENT '统计日期',
  Cust_Id                VARCHAR(150) NOT NULL          COMMENT '客户号',
  Ever_Hold_Deposit_ind  VARCHAR(3)                     COMMENT '历史存款类产品购买标志(YES/NO/空值)',
  New_Fund_Flag          VARCHAR(3)                     COMMENT '是否当月新进资金(YES/NO/空值)'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='零售客户行为标签表';

-- RTL_CUST_AST_MGT_BAL 数据（25 行）
INSERT INTO RTL_CUST_AST_MGT_BAL (Statistics_Dt, Cust_Id, Cust_Open_Org_Id, Belong_Org_Id, Belong_Branch_Id, Deposit_Bal, Cust_Type, Region, Deposit_Product, Avg_Bal, Rate_Band) VALUES
  (DATE '2024-01-15', 'CUST000001', 'ORG001', 'ORG001', 'BR001', 50000.00, '个人', '华东', '活期', 47500.00, '0.30%'),
  (DATE '2024-02-15', 'CUST000001', 'ORG001', 'ORG001', 'BR001', 50000.00, '个人', '华东', '活期', 47500.00, '0.30%'),
  (DATE '2024-03-15', 'CUST000001', 'ORG001', 'ORG001', 'BR001', 50000.00, '个人', '华东', '活期', 47500.00, '0.30%'),
  (DATE '2024-04-15', 'CUST000001', 'ORG001', 'ORG001', 'BR001', 50000.00, '个人', '华东', '活期', 47500.00, '0.30%'),
  (DATE '2024-01-15', 'CUST000003', 'ORG003', 'ORG003', 'BR002', 200000.00, '个人', '华南', '活期', 190000.00, '0.30%'),
  (DATE '2024-02-15', 'CUST000003', 'ORG003', 'ORG003', 'BR002', 200000.00, '个人', '华南', '活期', 190000.00, '0.30%'),
  (DATE '2024-03-15', 'CUST000003', 'ORG003', 'ORG003', 'BR002', 200000.00, '个人', '华南', '活期', 190000.00, '0.30%'),
  (DATE '2024-04-15', 'CUST000003', 'ORG003', 'ORG003', 'BR002', 200000.00, '个人', '华南', '活期', 190000.00, '0.30%'),
  (DATE '2024-02-15', 'CUST000003', 'ORG003', 'ORG003', 'BR002', 250000.00, '个人', '华南', '活期', 237500.00, '0.30%'),
  (DATE '2024-01-15', 'CUST000004', 'ORG005', 'ORG005', 'BR003', 80000.00, '个人', '华北', '活期', 76000.00, '0.30%'),
  (DATE '2024-01-15', 'CUST0004', 'ORG005', 'ORG005', 'BR003', 80000.00, '个人', '华北', '活期', 76000.00, '0.30%'),
  (DATE '2024-02-15', 'CUST000004', 'ORG005', 'ORG005', 'BR003', 80000.00, '个人', '华北', '活期', 76000.00, '0.30%'),
  (DATE '2024-02-15', 'CUST0004', 'ORG005', 'ORG005', 'BR003', 80000.00, '个人', '华北', '活期', 76000.00, '0.30%'),
  (DATE '2024-03-15', 'CUST000004', 'ORG005', 'ORG005', 'BR003', 80000.00, '个人', '华北', '活期', 76000.00, '0.30%'),
  (DATE '2024-03-15', 'CUST0004', 'ORG005', 'ORG005', 'BR003', 80000.00, '个人', '华北', '活期', 76000.00, '0.30%'),
  (DATE '2024-04-15', 'CUST000004', 'ORG005', 'ORG005', 'BR003', 80000.00, '个人', '华北', '活期', 76000.00, '0.30%'),
  (DATE '2024-04-15', 'CUST0004', 'ORG005', 'ORG005', 'BR003', 80000.00, '个人', '华北', '活期', 76000.00, '0.30%'),
  (DATE '2024-01-15', 'cust-001', 'ORG006', 'ORG006', 'BR004', 30000.00, '个人', '西部', '活期', 28500.00, '0.30%'),
  (DATE '2024-01-15', 'CUST-001', 'ORG006', 'ORG006', 'BR004', 30000.00, '个人', '西部', '活期', 28500.00, '0.30%'),
  (DATE '2024-02-15', 'cust-001', 'ORG006', 'ORG006', 'BR004', 30000.00, '个人', '西部', '活期', 28500.00, '0.30%'),
  (DATE '2024-02-15', 'CUST-001', 'ORG006', 'ORG006', 'BR004', 30000.00, '个人', '西部', '活期', 28500.00, '0.30%'),
  (DATE '2024-03-15', 'cust-001', 'ORG006', 'ORG006', 'BR004', 30000.00, '个人', '西部', '活期', 28500.00, '0.30%'),
  (DATE '2024-03-15', 'CUST-001', 'ORG006', 'ORG006', 'BR004', 30000.00, '个人', '西部', '活期', 28500.00, '0.30%'),
  (DATE '2024-04-15', 'cust-001', 'ORG006', 'ORG006', 'BR004', 30000.00, '个人', '西部', '活期', 28500.00, '0.30%'),
  (DATE '2024-04-15', 'CUST-001', 'ORG006', 'ORG006', 'BR004', 30000.00, '个人', '西部', '活期', 28500.00, '0.30%');

-- RTL_CUST_BEHAVIOR_TAG 数据（24 行）
INSERT INTO RTL_CUST_BEHAVIOR_TAG (Statistics_Dt, Cust_Id, Ever_Hold_Deposit_ind, New_Fund_Flag) VALUES
  (DATE '2024-01-15', 'CUST000002', 'NO', 'NO'),
  (DATE '2024-02-15', 'CUST000002', 'NO', 'NO'),
  (DATE '2024-03-15', 'CUST000002', 'NO', 'NO'),
  (DATE '2024-04-15', 'CUST000002', 'NO', 'NO'),
  (DATE '2024-01-15', 'CUST000003', 'YES', 'NO'),
  (DATE '2024-02-15', 'CUST000003', 'YES', 'NO'),
  (DATE '2024-03-15', 'CUST000003', 'YES', 'NO'),
  (DATE '2024-04-15', 'CUST000003', 'YES', 'NO'),
  (DATE '2024-01-15', 'CUST000004', 'YES', 'NO'),
  (DATE '2024-01-15', 'CUST0004', 'YES', 'NO'),
  (DATE '2024-02-15', 'CUST000004', 'YES', 'NO'),
  (DATE '2024-02-15', 'CUST0004', 'YES', 'NO'),
  (DATE '2024-03-15', 'CUST000004', 'YES', 'NO'),
  (DATE '2024-03-15', 'CUST0004', 'YES', 'NO'),
  (DATE '2024-04-15', 'CUST000004', 'YES', 'NO'),
  (DATE '2024-04-15', 'CUST0004', 'YES', 'NO'),
  (DATE '2024-01-15', 'cust-001', 'YES', 'NO'),
  (DATE '2024-01-15', 'CUST-001', 'NO', 'NO'),
  (DATE '2024-02-15', 'cust-001', 'YES', 'NO'),
  (DATE '2024-02-15', 'CUST-001', 'NO', 'NO'),
  (DATE '2024-03-15', 'cust-001', 'YES', 'NO'),
  (DATE '2024-03-15', 'CUST-001', 'NO', 'NO'),
  (DATE '2024-04-15', 'cust-001', 'YES', 'NO'),
  (DATE '2024-04-15', 'CUST-001', 'NO', 'NO');
