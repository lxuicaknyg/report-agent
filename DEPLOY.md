# 离线内网部署

两个容器：

| 容器 | 是什么 | 对外 |
|---|---|---|
| `gateway` | 前端 SPA + nginx 反向代理 | 唯一对外端口 |
| `backend` | 报告生成后端 | 不映射端口，只有网关能访问 |

其他团队的后端加入同一个 compose 网络，用服务名互访。浏览器只看到一个源，
所以整套部署里没有 CORS 配置，也不需要有。

```
浏览器 ──→ gateway:80 ┬─ /                     → SPA（history 路由）
                      ├─ /api/report/v1/*      → backend:8000
                      └─ /api/<工具>/v1/*      → <他们的容器>:port
```

---

## 一、构建与搬运

内网没有 docker registry 和公网，所以在**有网的机器上构建**，导出成 tar
搬进去：

```bash
# 有网的机器
docker compose build
docker save report-agent-gateway:latest report-agent-backend:latest \
  | gzip > report-agent-images.tar.gz

# 内网机器
gunzip -c report-agent-images.tar.gz | docker load
```

> 构建机的 CPU 架构要和内网机器一致。构建机是 Apple Silicon 而内网是 x86
> 服务器的话，加 `--platform linux/amd64` 构建，否则镜像加载后起不来。

除了这两个镜像，还要带进去的文件：

- `docker-compose.yml`
- `deploy/nginx-modules/`（其他团队的路由）
- 你自己的 `.env`（从 `deploy/env.example` 复制后填写）

---

## 二、配置

```bash
cp deploy/env.example .env
```

必须填的四项，缺任何一项容器会拒绝启动（而不是起来之后才在日志里报错）：

| 变量 | 说明 |
|---|---|
| `AUTH_SECRET` | `openssl rand -base64 48`。**工作台内所有后端必须用同一个值** |
| `AUTH_DATABASE_URL` | 用户库，含 `users` 表。密码里的 `@` 要写成 `%40` |
| `LLM_BASE_URL` | 内网 OpenAI 兼容网关 |
| `LLM_MODEL_NAME` | 网关上的模型名 |

### 关于 AUTH_SECRET

这是整套架构里唯一一个**跨团队共享**的配置。宿主在登录时用它签发 JWT，
同事的后端用同一个值验签，用户才只需要登录一次。

值不一致的表现是：用户在宿主这边登录正常，一点进同事的工具就 401。
排查时先对这个值，不要先去看代码。

轮换会让所有已登录用户掉线（在途的报告生成不受影响，但页面要重新登录），
所以要挑时间窗口，并且和其他团队同步改。

---

## 三、启动

```bash
docker compose up -d
docker compose ps          # 两个都应该是 healthy
curl http://localhost/healthz
```

第一次启动后验证一遍：

```bash
# 未登录必须被拒
curl -s -o /dev/null -w '%{http_code}\n' http://localhost/api/report/v1/conversations
# 期望 401

# 登录
curl -s http://localhost/api/report/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"...","password":"..."}'
# 期望返回 token
```

登录这一步如果返回 503，是用户库连不上，不是密码错 —— 后端会把这两种情况
分开报。

---

## 四、接入其他团队的工具

**前端**：他们按 `frontend/CONTRIBUTING_MODULES.md` 提 PR 合进
`frontend/src/modules/`，然后重新构建 gateway 镜像。

**后端**：他们的容器加到 `report-agent-workspace` 网络里：

```yaml
# 他们的 docker-compose.yml
services:
  their-backend:
    image: their-tool-backend:latest
    environment:
      AUTH_SECRET: ${AUTH_SECRET}      # 和宿主同一个值
    networks: [workspace]

networks:
  workspace:
    external: true
    name: report-agent-workspace
```

**路由**：在 `deploy/nginx-modules/` 下加一个 `.conf`，照
`their-tool.conf.example` 改。然后热加载，不用重启：

```bash
docker compose exec gateway nginx -t && docker compose exec gateway nginx -s reload
```

> 前端是一个镜像。同事改一行前端也要重新构建、重新搬运整个 gateway 镜像 ——
> 这是这套架构最大的组织成本，发版节奏要提前和他们约定好。后端路由改动不受
> 影响，热加载即可。

---

## 五、数据与备份

需要留存的东西全部在一个卷里：

```
report-state (/var/lib/report-agent)
├── datasets/       上传的 Excel
├── artifacts/      生成的报告文件
├── templates/      上传的报告模板原件
├── templates.json  模板元数据
├── sessions.json   报告生成状态
├── conversations.json
├── connections.json  ← 含数据库凭据
└── logs/
```

```bash
docker run --rm -v report-agent_report-state:/data -v "$PWD":/backup alpine \
  tar czf /backup/report-state-$(date +%F).tar.gz -C /data .
```

`connections.json` 里有用户保存的数据库密码，备份文件按同等密级管理。

---

## 六、已知限制

### backend 只能单副本、单 worker

报告生成是进程内的 asyncio 任务，进度在内存 + 卷上的 JSON 里。加副本或加
worker 会导致：

- 前端轮询打到没有这个任务的进程 → 用户看到 404
- 两个进程并发写同一份 JSON → 互相覆盖

`Dockerfile` 里写死了 `--workers 1`，compose 里 `replicas: 1`。**不要为了
"提升性能" 改这两个值** —— 要横向扩展得先把任务状态挪到进程外，那是另一个
量级的改动。

容器重启会把在途的报告标记为「已终止，请重新提交」（而不是永远转圈）。

### openLooKeng 的 JDBC 驱动 jar 要挂载

JRE 已经装在后端镜像里（`openjdk-17-jre-headless`，`JAVA_HOME` 指向
`/usr/lib/jvm/java-17-openjdk-amd64`），构建时装好，内网不需要再准备 Java。

**驱动 jar 不在镜像里**，它是厂商授权的、还要和集群版本对上，所以走挂载：
把 jar 放进 `deploy/jdbc/`，容器里是 `/opt/jdbc/`。

前端「数据源」表单里那个「JDBC 驱动 jar 路径」填的是**容器内**路径
（`/opt/jdbc/xxx.jar`），不是宿主机路径 —— 这是最容易填错的一项。

用不到 openLooKeng 就把 compose 里那个挂载删掉，只有那一个驱动会失效，
MySQL 和 GaussDB 不受影响。
