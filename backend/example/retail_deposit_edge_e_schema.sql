-- 零售存款边界数据 E：时间异常
-- 数据集：retail_deposit_edge_e
-- 另类 E：时间异常。约 20 行。CUST000001 所有行 Statistics_Dt 都是 2024-06-15（同一天）；CUST000002 跨年 2023-12 ~ 2024-03；CUST000003 未来日期 2026-01 ~ 2026-04；CUST000004/005 余额单调增长（验证模型会不会无脑套'稳步增长'套话）。

-- 建库：
--   mysql -u root -p < retail_deposit_edge_e_schema.sql

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
  Rate_Band              VARCHAR(30)                    COMMENT '利率档位',
  PRIMARY KEY (Statistics_Dt, Cust_Id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='零售客户资产管理余额表';

-- 零售客户行为标签表
CREATE TABLE RTL_CUST_BEHAVIOR_TAG (
  Statistics_Dt          DATE NOT NULL                  COMMENT '统计日期',
  Cust_Id                VARCHAR(150) NOT NULL          COMMENT '客户号',
  Ever_Hold_Deposit_ind  VARCHAR(3)                     COMMENT '历史存款类产品购买标志(YES/NO/空值)',
  New_Fund_Flag          VARCHAR(3)                     COMMENT '是否当月新进资金(YES/NO/空值)',
  PRIMARY KEY (Statistics_Dt, Cust_Id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='零售客户行为标签表';

-- RTL_CUST_AST_MGT_BAL 数据（20 行）
INSERT INTO RTL_CUST_AST_MGT_BAL (Statistics_Dt, Cust_Id, Cust_Open_Org_Id, Belong_Org_Id, Belong_Branch_Id, Deposit_Bal, Cust_Type, Region, Deposit_Product, Avg_Bal, Rate_Band) VALUES
  (DATE '2024-06-15', 'CUST000001', 'ORG001', 'ORG001', 'BR001', 10000.00, '个人', '华东', '活期', 9500.00, '0.30%'),
  (DATE '2024-06-15', 'CUST000001', 'ORG001', 'ORG001', 'BR001', 20000.00, '个人', '华东', '活期', 19000.00, '0.30%'),
  (DATE '2024-06-15', 'CUST000001', 'ORG001', 'ORG001', 'BR001', 30000.00, '个人', '华东', '活期', 28500.00, '0.30%'),
  (DATE '2024-06-15', 'CUST000001', 'ORG001', 'ORG001', 'BR001', 40000.00, '个人', '华东', '活期', 38000.00, '0.30%'),
  (DATE '2023-12-15', 'CUST000002', 'ORG003', 'ORG003', 'BR002', 80000.00, '个人', '华南', '活期', 76000.00, '0.30%'),
  (DATE '2024-01-15', 'CUST000002', 'ORG003', 'ORG003', 'BR002', 85000.00, '个人', '华南', '活期', 80750.00, '0.30%'),
  (DATE '2024-02-15', 'CUST000002', 'ORG003', 'ORG003', 'BR002', 90000.00, '个人', '华南', '活期', 85500.00, '0.30%'),
  (DATE '2024-03-15', 'CUST000002', 'ORG003', 'ORG003', 'BR002', 95000.00, '个人', '华南', '活期', 90250.00, '0.30%'),
  (DATE '2026-01-15', 'CUST000003', 'ORG005', 'ORG005', 'BR003', 120000.00, '个人', '华北', '活期', 114000.00, '0.30%'),
  (DATE '2026-02-15', 'CUST000003', 'ORG005', 'ORG005', 'BR003', 120000.00, '个人', '华北', '活期', 114000.00, '0.30%'),
  (DATE '2026-03-15', 'CUST000003', 'ORG005', 'ORG005', 'BR003', 120000.00, '个人', '华北', '活期', 114000.00, '0.30%'),
  (DATE '2026-04-15', 'CUST000003', 'ORG005', 'ORG005', 'BR003', 120000.00, '个人', '华北', '活期', 114000.00, '0.30%'),
  (DATE '2024-01-15', 'CUST000004', 'ORG006', 'ORG006', 'BR004', 10000.00, '个人', '西部', '活期', 9500.00, '0.30%'),
  (DATE '2024-02-15', 'CUST000004', 'ORG006', 'ORG006', 'BR004', 20000.00, '个人', '西部', '活期', 19000.00, '0.30%'),
  (DATE '2024-03-15', 'CUST000004', 'ORG006', 'ORG006', 'BR004', 30000.00, '个人', '西部', '活期', 28500.00, '0.30%'),
  (DATE '2024-04-15', 'CUST000004', 'ORG006', 'ORG006', 'BR004', 40000.00, '个人', '西部', '活期', 38000.00, '0.30%'),
  (DATE '2024-01-15', 'CUST000005', 'ORG008', 'ORG008', 'BR005', 15000.00, '个人', '东北', '活期', 14250.00, '0.30%'),
  (DATE '2024-02-15', 'CUST000005', 'ORG008', 'ORG008', 'BR005', 30000.00, '个人', '东北', '活期', 28500.00, '0.30%'),
  (DATE '2024-03-15', 'CUST000005', 'ORG008', 'ORG008', 'BR005', 45000.00, '个人', '东北', '活期', 42750.00, '0.30%'),
  (DATE '2024-04-15', 'CUST000005', 'ORG008', 'ORG008', 'BR005', 60000.00, '个人', '东北', '活期', 57000.00, '0.30%');

-- RTL_CUST_BEHAVIOR_TAG 数据（20 行）
INSERT INTO RTL_CUST_BEHAVIOR_TAG (Statistics_Dt, Cust_Id, Ever_Hold_Deposit_ind, New_Fund_Flag) VALUES
  (DATE '2024-06-15', 'CUST000001', 'YES', 'YES'),
  (DATE '2024-06-15', 'CUST000001', 'YES', 'YES'),
  (DATE '2024-06-15', 'CUST000001', 'YES', 'YES'),
  (DATE '2024-06-15', 'CUST000001', 'YES', 'YES'),
  (DATE '2023-12-15', 'CUST000002', 'YES', 'NO'),
  (DATE '2024-01-15', 'CUST000002', 'YES', 'NO'),
  (DATE '2024-02-15', 'CUST000002', 'YES', 'NO'),
  (DATE '2024-03-15', 'CUST000002', 'YES', 'NO'),
  (DATE '2026-01-15', 'CUST000003', 'YES', 'NO'),
  (DATE '2026-02-15', 'CUST000003', 'YES', 'NO'),
  (DATE '2026-03-15', 'CUST000003', 'YES', 'NO'),
  (DATE '2026-04-15', 'CUST000003', 'YES', 'NO'),
  (DATE '2024-01-15', 'CUST000004', 'YES', 'NO'),
  (DATE '2024-02-15', 'CUST000004', 'YES', 'NO'),
  (DATE '2024-03-15', 'CUST000004', 'YES', 'NO'),
  (DATE '2024-04-15', 'CUST000004', 'YES', 'NO'),
  (DATE '2024-01-15', 'CUST000005', 'YES', 'NO'),
  (DATE '2024-02-15', 'CUST000005', 'YES', 'NO'),
  (DATE '2024-03-15', 'CUST000005', 'YES', 'NO'),
  (DATE '2024-04-15', 'CUST000005', 'YES', 'NO');
