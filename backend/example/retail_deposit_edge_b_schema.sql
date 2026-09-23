-- 零售存款边界数据 B：NULL 满天飞
-- 数据集：retail_deposit_edge_b
-- 另类 B：NULL 满天飞。5 客户 × 4 月 = 20 行。CUST000001 Deposit_Bal NULL；CUST000002 Cust_Open_Org_Id NULL；CUST000003 Belong_Branch_Id NULL；CUST000004 Ever_Hold_Deposit_ind NULL；CUST000005 除主键外全字段 NULL。

-- 建库：
--   mysql -u root -p < retail_deposit_edge_b_schema.sql

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
  (DATE '2024-01-15', 'CUST000001', 'ORG001', 'ORG001', 'BR001', NULL, '个人', '华东', '定期3M', NULL, '1.40%'),
  (DATE '2024-02-15', 'CUST000001', 'ORG001', 'ORG001', 'BR001', NULL, '个人', '华东', '定期3M', NULL, '1.40%'),
  (DATE '2024-03-15', 'CUST000001', 'ORG001', 'ORG001', 'BR001', NULL, '个人', '华东', '定期3M', NULL, '1.40%'),
  (DATE '2024-04-15', 'CUST000001', 'ORG001', 'ORG001', 'BR001', NULL, '个人', '华东', '定期3M', NULL, '1.40%'),
  (DATE '2024-01-15', 'CUST000002', NULL, 'ORG001', 'BR001', 100000.00, '个人', '华东', '定期3M', 95000.00, '1.40%'),
  (DATE '2024-02-15', 'CUST000002', NULL, 'ORG001', 'BR001', 100000.00, '个人', '华东', '定期3M', 95000.00, '1.40%'),
  (DATE '2024-03-15', 'CUST000002', NULL, 'ORG001', 'BR001', 100000.00, '个人', '华东', '定期3M', 95000.00, '1.40%'),
  (DATE '2024-04-15', 'CUST000002', NULL, 'ORG001', 'BR001', 100000.00, '个人', '华东', '定期3M', 95000.00, '1.40%'),
  (DATE '2024-01-15', 'CUST000003', 'ORG001', 'ORG001', NULL, 100000.00, '个人', '华东', '定期3M', 95000.00, '1.40%'),
  (DATE '2024-02-15', 'CUST000003', 'ORG001', 'ORG001', NULL, 100000.00, '个人', '华东', '定期3M', 95000.00, '1.40%'),
  (DATE '2024-03-15', 'CUST000003', 'ORG001', 'ORG001', NULL, 100000.00, '个人', '华东', '定期3M', 95000.00, '1.40%'),
  (DATE '2024-04-15', 'CUST000003', 'ORG001', 'ORG001', NULL, 100000.00, '个人', '华东', '定期3M', 95000.00, '1.40%'),
  (DATE '2024-01-15', 'CUST000004', 'ORG001', 'ORG001', 'BR001', 100000.00, '个人', '华东', '定期3M', 95000.00, '1.40%'),
  (DATE '2024-02-15', 'CUST000004', 'ORG001', 'ORG001', 'BR001', 100000.00, '个人', '华东', '定期3M', 95000.00, '1.40%'),
  (DATE '2024-03-15', 'CUST000004', 'ORG001', 'ORG001', 'BR001', 100000.00, '个人', '华东', '定期3M', 95000.00, '1.40%'),
  (DATE '2024-04-15', 'CUST000004', 'ORG001', 'ORG001', 'BR001', 100000.00, '个人', '华东', '定期3M', 95000.00, '1.40%'),
  (DATE '2024-01-15', 'CUST000005', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
  (DATE '2024-02-15', 'CUST000005', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
  (DATE '2024-03-15', 'CUST000005', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
  (DATE '2024-04-15', 'CUST000005', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);

-- RTL_CUST_BEHAVIOR_TAG 数据（20 行）
INSERT INTO RTL_CUST_BEHAVIOR_TAG (Statistics_Dt, Cust_Id, Ever_Hold_Deposit_ind, New_Fund_Flag) VALUES
  (DATE '2024-01-15', 'CUST000001', 'YES', 'NO'),
  (DATE '2024-02-15', 'CUST000001', 'YES', 'NO'),
  (DATE '2024-03-15', 'CUST000001', 'YES', 'NO'),
  (DATE '2024-04-15', 'CUST000001', 'YES', 'NO'),
  (DATE '2024-01-15', 'CUST000002', 'NO', 'NO'),
  (DATE '2024-02-15', 'CUST000002', 'NO', 'NO'),
  (DATE '2024-03-15', 'CUST000002', 'NO', 'NO'),
  (DATE '2024-04-15', 'CUST000002', 'NO', 'NO'),
  (DATE '2024-01-15', 'CUST000003', 'YES', 'NO'),
  (DATE '2024-02-15', 'CUST000003', 'YES', 'NO'),
  (DATE '2024-03-15', 'CUST000003', 'YES', 'NO'),
  (DATE '2024-04-15', 'CUST000003', 'YES', 'NO'),
  (DATE '2024-01-15', 'CUST000004', NULL, NULL),
  (DATE '2024-02-15', 'CUST000004', NULL, NULL),
  (DATE '2024-03-15', 'CUST000004', NULL, NULL),
  (DATE '2024-04-15', 'CUST000004', NULL, NULL),
  (DATE '2024-01-15', 'CUST000005', NULL, NULL),
  (DATE '2024-02-15', 'CUST000005', NULL, NULL),
  (DATE '2024-03-15', 'CUST000005', NULL, NULL),
  (DATE '2024-04-15', 'CUST000005', NULL, NULL);
