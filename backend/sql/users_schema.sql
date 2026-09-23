-- 登录用户表。结构对齐生产库 AI_DA_DB.users。
--
-- 注意：password 是明文列，与现网数据一致。校验逻辑同时支持哈希值，
-- 所以这一列改存哈希不需要改代码，详见 backend/app/auth/service.py。
--
-- 样例数据在 users_seed.sql，单独执行。

CREATE DATABASE IF NOT EXISTS AI_DA_DB
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE AI_DA_DB;

CREATE TABLE IF NOT EXISTS users (
  id         INT AUTO_INCREMENT PRIMARY KEY,
  username   VARCHAR(50)  NOT NULL,
  password   VARCHAR(255) NOT NULL,
  created_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  role       VARCHAR(20)  NOT NULL DEFAULT 'user',
  workspace  VARCHAR(100) NULL,
  UNIQUE KEY uk_users_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
