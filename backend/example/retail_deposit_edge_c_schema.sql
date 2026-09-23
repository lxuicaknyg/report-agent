-- 零售存款边界数据 C：分布异常
-- 数据集：retail_deposit_edge_c
-- 另类 C：分布异常。5 客户 × 4 月 = 20 行。全员余额 100 万；3 月全员余额 0；所有客户 Cust_Type 都是同业。

-- 建库：
--   mysql -u root -p < retail_deposit_edge_c_schema.sql

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
  (DATE '2024-01-15', 'CUST000001', 'ORG001', 'ORG001', 'BR001', 1000000.00, '同业', '华东', '通知存款', 950000.00, '1.50%'),
  (DATE '2024-02-15', 'CUST000001', 'ORG001', 'ORG001', 'BR001', 1000000.00, '同业', '华东', '通知存款', 950000.00, '1.50%'),
  (DATE '2024-03-15', 'CUST000001', 'ORG001', 'ORG001', 'BR001', 0.00, '同业', '华东', '通知存款', 0.00, '1.50%'),
  (DATE '2024-04-15', 'CUST000001', 'ORG001', 'ORG001', 'BR001', 1000000.00, '同业', '华东', '通知存款', 950000.00, '1.50%'),
  (DATE '2024-01-15', 'CUST000002', 'ORG003', 'ORG003', 'BR002', 1000000.00, '同业', '华南', '通知存款', 950000.00, '1.50%'),
  (DATE '2024-02-15', 'CUST000002', 'ORG003', 'ORG003', 'BR002', 1000000.00, '同业', '华南', '通知存款', 950000.00, '1.50%'),
  (DATE '2024-03-15', 'CUST000002', 'ORG003', 'ORG003', 'BR002', 0.00, '同业', '华南', '通知存款', 0.00, '1.50%'),
  (DATE '2024-04-15', 'CUST000002', 'ORG003', 'ORG003', 'BR002', 1000000.00, '同业', '华南', '通知存款', 950000.00, '1.50%'),
  (DATE '2024-01-15', 'CUST000003', 'ORG005', 'ORG005', 'BR003', 1000000.00, '同业', '华北', '通知存款', 950000.00, '1.50%'),
  (DATE '2024-02-15', 'CUST000003', 'ORG005', 'ORG005', 'BR003', 1000000.00, '同业', '华北', '通知存款', 950000.00, '1.50%'),
  (DATE '2024-03-15', 'CUST000003', 'ORG005', 'ORG005', 'BR003', 0.00, '同业', '华北', '通知存款', 0.00, '1.50%'),
  (DATE '2024-04-15', 'CUST000003', 'ORG005', 'ORG005', 'BR003', 1000000.00, '同业', '华北', '通知存款', 950000.00, '1.50%'),
  (DATE '2024-01-15', 'CUST000004', 'ORG006', 'ORG006', 'BR004', 1000000.00, '同业', '西部', '通知存款', 950000.00, '1.50%'),
  (DATE '2024-02-15', 'CUST000004', 'ORG006', 'ORG006', 'BR004', 1000000.00, '同业', '西部', '通知存款', 950000.00, '1.50%'),
  (DATE '2024-03-15', 'CUST000004', 'ORG006', 'ORG006', 'BR004', 0.00, '同业', '西部', '通知存款', 0.00, '1.50%'),
  (DATE '2024-04-15', 'CUST000004', 'ORG006', 'ORG006', 'BR004', 1000000.00, '同业', '西部', '通知存款', 950000.00, '1.50%'),
  (DATE '2024-01-15', 'CUST000005', 'ORG008', 'ORG008', 'BR005', 1000000.00, '同业', '东北', '通知存款', 950000.00, '1.50%'),
  (DATE '2024-02-15', 'CUST000005', 'ORG008', 'ORG008', 'BR005', 1000000.00, '同业', '东北', '通知存款', 950000.00, '1.50%'),
  (DATE '2024-03-15', 'CUST000005', 'ORG008', 'ORG008', 'BR005', 0.00, '同业', '东北', '通知存款', 0.00, '1.50%'),
  (DATE '2024-04-15', 'CUST000005', 'ORG008', 'ORG008', 'BR005', 1000000.00, '同业', '东北', '通知存款', 950000.00, '1.50%');

-- RTL_CUST_BEHAVIOR_TAG 数据（20 行）
INSERT INTO RTL_CUST_BEHAVIOR_TAG (Statistics_Dt, Cust_Id, Ever_Hold_Deposit_ind, New_Fund_Flag) VALUES
  (DATE '2024-01-15', 'CUST000001', 'YES', 'NO'),
  (DATE '2024-02-15', 'CUST000001', 'YES', 'NO'),
  (DATE '2024-03-15', 'CUST000001', 'YES', 'YES'),
  (DATE '2024-04-15', 'CUST000001', 'YES', 'NO'),
  (DATE '2024-01-15', 'CUST000002', 'YES', 'NO'),
  (DATE '2024-02-15', 'CUST000002', 'YES', 'NO'),
  (DATE '2024-03-15', 'CUST000002', 'YES', 'YES'),
  (DATE '2024-04-15', 'CUST000002', 'YES', 'NO'),
  (DATE '2024-01-15', 'CUST000003', 'YES', 'NO'),
  (DATE '2024-02-15', 'CUST000003', 'YES', 'NO'),
  (DATE '2024-03-15', 'CUST000003', 'YES', 'YES'),
  (DATE '2024-04-15', 'CUST000003', 'YES', 'NO'),
  (DATE '2024-01-15', 'CUST000004', 'YES', 'NO'),
  (DATE '2024-02-15', 'CUST000004', 'YES', 'NO'),
  (DATE '2024-03-15', 'CUST000004', 'YES', 'YES'),
  (DATE '2024-04-15', 'CUST000004', 'YES', 'NO'),
  (DATE '2024-01-15', 'CUST000005', 'YES', 'NO'),
  (DATE '2024-02-15', 'CUST000005', 'YES', 'NO'),
  (DATE '2024-03-15', 'CUST000005', 'YES', 'YES'),
  (DATE '2024-04-15', 'CUST000005', 'YES', 'NO');
