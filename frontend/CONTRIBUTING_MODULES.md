# 在 AI 数据分析工作台中接入工具

本工作台是宿主应用：它提供登录、顶部导航和统一的视觉规范。你的工具作为一个**模块**接进来，在顶部导航栏里占一项。

本文只讲前端。你的后端独立部署、独立维护，不需要合并到本项目。

---

## 一、你得到什么，不得到什么

| 得到 | 不得到 |
|---|---|
| 顶部导航栏（logo、导航、账号区）与其中属于你的那一项 | 报告工作台的会话侧栏 |
| 登录与登录态，用户只登一次 | 报告相关的 store 和状态 |
| 统一的 CSS 设计令牌 | 对宿主路由的控制权 |
| 带身份的 API 客户端 | |

点进你的工具后，页面上只有**顶栏 + 你自己的界面**。侧栏是报告工作台专有的，不会出现。

当前顶栏：报告生成（宿主）｜报告摘要 `/prose`｜片段润色 `/polish`｜数据处理 `/excel-tools`。

---

## 二、目录结构

> **先看 `src/modules/_example/`。** 那是一个能跑的完整参考实现：路由、带命名
> 空间的接口调用、加前缀的 store、用设计令牌的 scoped 样式，本文讲的约定它全
> 都演示了一遍。照着抄比照着文档从头写快得多。
>
> 它没有注册进顶栏（打包时会被 tree-shake 掉，线上零成本），但会跟着
> `pnpm check` 一起做类型检查。

在 `src/modules/` 下建一个属于你的目录，所有代码都放在里面：

```
src/modules/your-tool/
├── index.ts          模块入口（唯一约定的文件）
├── routes.ts         路由（可选，也可以直接写在 index.ts）
├── pages/            页面组件
├── components/       组件
├── stores/           Pinia store（store id 要加前缀，见第五节）
├── services/         接口调用
└── types.ts
```

**不要修改 `src/modules/` 以外的任何文件**，除了第三节那一行注册。

---

## 三、注册

`src/modules/your-tool/index.ts`：

```ts
import type { WorkspaceModule } from '../../app/modules'

const module: WorkspaceModule = {
  key: 'your-tool',                      // 稳定 id，同时用作 store 前缀和 meta.nav 的值
  label: '数据比对',                      // 顶栏上显示的文字，越短越好
  entry: 'your-tool',                    // 顶栏这一项打开的路由 name
  routes: [
    {
      path: 'your-tool',                 // 相对于 /，不写开头的斜杠
      name: 'your-tool',
      component: () => import('./pages/HomePage.vue'),
      meta: { nav: 'your-tool' },         // 必须，见下方说明
    },
  ],
}

export default module
```

然后在 `src/app/modules.ts` 里加两处：

```ts
import yourTool from '../modules/your-tool'

export const modules: WorkspaceModule[] = [prose, polish, excelTools, yourTool]
```

**就这些。** 顶栏会自动多出你这一项，路由自动挂载 —— 顶栏和路由读的是同一份 `modules` 数组。

### 关于 `meta: { nav: <key> }`

顶栏靠这个字段决定高亮哪一项。你的**每条**路由都要带上它，并且值要等于你的 `key`，否则用户进到你的二级页面时顶栏会不知道该亮哪个。

### 关于 `path` 和 `name`

用你的工具名做一级路径。多个页面就多写几条 `routes`，`entry` 指向落地页。

**宿主已占用的一级路径**（撞了你的页面会打不开）：

```
login  datasets  connections  reports  conversations
```

**宿主已占用的路由 name**（`name` 全局唯一，撞了 vue-router 会静默用后注册的那个）：

```
login  workspace  not-found
datasets  dataset-detail  connections
reports  report-templates  report-detail
conversations  conversation-new  conversation-detail
```

建议直接用 `key` 和 `key-xxx`，天然不会撞。

### 顶栏上的位置

`modules` 数组的顺序就是顶栏的顺序，「报告生成」固定在最前。想调位置改数组顺序即可。

---

## 四、调接口与用户身份

### 必须使用宿主的 apiClient

```ts
import { apiClient } from '../../services/api/client'

const result = await apiClient.get<YourType>('/your-tool/v1/items')
if (result.success && result.data) {
  // result.data
} else {
  console.error(result.error?.message)
}
```

可用方法：`get` / `post` / `put` / `delete` / `upload`。

返回值统一是：

```ts
interface ApiResult<T> {
  success: boolean
  data?: T | null
  error?: { code: string; message: string; details?: Record<string, unknown> }
}
```

**不要自己写 `fetch()`。** apiClient 会自动附加登录令牌，自己发请求就没有身份信息，你的后端会拒绝。

### 用户身份怎么传到你的后端

apiClient 对每个请求自动加上：

```
Authorization: Bearer <JWT>
```

这个 JWT 由宿主在登录时签发，payload 里是：

```json
{
  "sub": "123",
  "username": "zhangsan",
  "role": "analyst",
  "workspace": "default",
  "iat": 1770000000,
  "exp": 1770086400
}
```

你的后端拿**同一个 `AUTH_SECRET`** 验签即可：

```python
import jwt

payload  = jwt.decode(token, AUTH_SECRET, algorithms=["HS256"])
username = payload["username"]
user_id  = payload["sub"]
role     = payload["role"]
```

PyJWT 默认会校验 `exp`，不用自己判断过期。

**三件必须和宿主约定一致的事：**

| | |
|---|---|
| `AUTH_SECRET` | 同一个值，环境变量下发，不要写进代码或提交到仓库 |
| 算法 | `HS256` |
| 字段名 | `sub` / `username` / `role` / `workspace` |

密钥不一致，你的后端验签会失败，用户就得在你的工具里再登一次 —— 统一工作台的意义就没了。

> **不要让前端把用户名放在 body 或 query 里传给后端。** 那个值浏览器里随手就能改，等于没有身份校验。JWT 是签过名的，改一个字符验签就不过。

### 前端读当前用户

需要在界面上显示用户名时：

```ts
import { useAuthStore } from '../../stores'

const auth = useAuthStore()
auth.username      // 用户名
auth.user          // 完整用户对象
auth.isLoggedIn    // 是否已登录
```

只读。登录和登出由宿主负责，模块不要调 `login()` / `logout()`。

### API 路径命名空间

apiClient 的基地址是 `/api`，下一段路径决定请求去哪个容器。线上由 nginx 按这一段分发：

```
/api/report/v1/*     → 报告生成后端（宿主）
/api/your-tool/v1/*  → 你的后端
```

所以你的接口路径要带自己的命名空间，apiClient 只负责补 `/api`：

```ts
apiClient.get('/your-tool/v1/items')   // 实际请求 /api/your-tool/v1/items
```

**命名空间用你的工具名，版本号自己管**，别和宿主的 `report` 撞。定下来之后告诉宿主维护者，nginx 要加一条对应的 `location`。

> 宿主自己的代码走的是 `hostApi`（`apiClient` 的包装，自动补 `/report/v1`）。你不要用它 —— 那是宿主的命名空间，用了请求会打到报告后端去。

---

## 五、命名约束

### Pinia store id 必须加前缀

```ts
export const useYourToolStore = defineStore('your-tool-main', () => { ... })
//                                           ^^^^^^^^^^ 前缀
```

宿主已经占用了这些 id：`auth`、`conversation`、`connection`、`dataset`、`report`。

**撞车不会报错，是静默覆盖** —— 两个模块共用一份状态，排查起来非常痛苦。

### localStorage key 也要加前缀

```ts
localStorage.setItem('your-tool:filter-v1', value)
```

宿主用的是 `report-agent:` 前缀。

---

## 六、样式

### 用宿主的设计令牌，不要自带一套配色

```css
.your-card {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  color: var(--color-text-body);
  box-shadow: var(--shadow-card);
}
```

可用的令牌：

```
颜色   --color-primary          --color-primary-dark    --color-primary-accent
       --color-primary-light    --color-primary-border  --color-primary-border-strong
       --color-bg               --color-bg-card         --color-bg-sidebar
       --color-bg-hover         --color-bg-active       --color-bg-gray
       --color-border
       --color-text-dark        --color-text-medium     --color-text-light
       --color-text-lighter     --color-text-body
状态   --color-success  --color-success-bg    --color-warning  --color-warning-bg
       --color-error    --color-error-bg      --color-error-border
       --color-info     --color-info-bg
圆角   --radius-sm  --radius-md  --radius-lg  --radius-pill
阴影   --shadow-card  --shadow-hover  --shadow-dropdown
渐变   --gradient-primary
```

### 样式必须 scoped

```vue
<style scoped>
  /* 你的样式 */
</style>
```

**不要写 `:root`、`*`、`html`、`body` 这类全局规则。** 它们会溢出到整个应用 —— 如果你也定义 `--color-primary`，后加载的那份会赢，另一半界面的配色就废了。

需要给 `v-html` 内容加样式时，用 `:deep()` 限定在自己的容器里，不要开一个不带 scoped 的 `<style>`。

---

## 七、本地开发

本项目用 **pnpm**（仓库里只有 `pnpm-lock.yaml`）。用 npm 装会生成一份
`package-lock.json`，两份锁文件并存之后谁都说不清依赖版本到底是哪个，构建
镜像时也会装出和你本地不一样的东西。

```bash
cd frontend
corepack enable          # 没装过 pnpm 的话
pnpm install
pnpm dev                 # http://localhost:5173
```

### 你需要先能登录

**你的页面挂在需要登录的路由下**，不登录连自己的界面都打不开。登录要有宿主
后端和用户库，但你不需要为此装一套 Python —— 直接跑我们构建好的镜像：

```bash
# 在仓库根目录。需要一份填好 AUTH_DATABASE_URL 的 .env，找宿主维护者要。
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d backend
```

这会把宿主后端起在 `127.0.0.1:8000`，正好是 vite 默认代理的地址，`pnpm dev`
就能登录了。

### 代理到你自己的后端

vite 会把整个 `/api/*` 代理到 `http://127.0.0.1:8000`。要指向你自己的后端，
在 `frontend/.env.local` 里设（这个文件不要提交）：

```
VITE_API_PROXY_TARGET=http://127.0.0.1:你的端口
```

但注意：这样一来宿主的 `/api/report/v1/*`（含登录）也会被代理到你那边。
同时要用两边的话，让你的后端把 `/api/report/v1/*` 转发给宿主后端，或者干脆
在你的后端上也起一个 `/api/report/v1/auth/login` 的转发。

### 提交前必须过这三关

```bash
pnpm check               # = vue-tsc --noEmit && vite build
pnpm dev                 # 再手动点一遍
```

> `vue-tsc` 不解析模板和 `<style>` 块，语法错误它看不出来。构建是必跑的，
> 所以 `check` 把两步绑在一起了。
>
> 前端是一个镜像、一次构建：你这边构建不过，**所有人**都发不了版。这一步
> 别省。

---

## 八、部署时你需要做的

前端合并进来就跟着宿主的镜像走，你不用管。**你的后端**要做两件事：

1. **加入同一个 compose 网络**，这样网关能按服务名找到你：

   ```yaml
   services:
     your-backend:
       image: your-tool-backend:latest
       environment:
         AUTH_SECRET: ${AUTH_SECRET}      # 和宿主同一个值
       networks: [workspace]

   networks:
     workspace:
       external: true
       name: report-agent-workspace
   ```

2. **加一条网关路由**：在 `deploy/nginx-modules/` 下放一个 `<你的工具>.conf`，
   照着那个目录里的 `their-tool.conf.example` 改。**务必照抄里面 `proxy_pass`
   走变量的写法** —— 直接写主机名的话，你的容器没起来会导致整个网关起不来，
   连登录页和别人的工具一起挂掉。

完整部署说明见仓库根目录的 `DEPLOY.md`。

---

## 九、提交前检查清单

- [ ] 所有代码都在 `src/modules/your-tool/` 下
- [ ] `src/app/modules.ts` 里只加了一个 import 和一个数组项
- [ ] 每条路由都有 `meta: { nav: '<你的 key>' }`
- [ ] 路由 `path` 和 `name` 没有和宿主或其他模块撞车
- [ ] 所有请求走 `apiClient`，没有裸 `fetch()`
- [ ] API 路径带自己的命名空间
- [ ] store id 和 localStorage key 都加了前缀
- [ ] 所有 `<style>` 都是 `scoped`，没有 `:root` / `*` / `html` / `body`
- [ ] 颜色圆角用的是设计令牌，不是硬编码色值
- [ ] `pnpm check` 通过
- [ ] 你的后端用同一个 `AUTH_SECRET` 验签，能拿到 `username`
- [ ] `deploy/nginx-modules/` 下有你的 `.conf`，且 `proxy_pass` 走变量

---

## 十、遇到问题

- **接口 401**：检查你的后端 `AUTH_SECRET` 和宿主是否一致，算法是否是 HS256。宿主的接口在无 token 时一律返回 401，你的也应该这样
- **接口 404 但资源确实存在**：宿主对「不是你的」资源统一返回 404 而不是 403（403 等于承认这个 id 存在）。你的后端建议保持一致
- **请求没带 Authorization**：你可能用了裸 `fetch()`，改用 `apiClient`
- **顶栏高亮不对**：路由缺 `meta: { nav: '<你的 key>' }`，或者值和 `key` 不一致
- **样式串了**：你写了非 scoped 的全局规则，或者重新定义了 `--color-*` 令牌
- **状态莫名其妙被改**：store id 撞了宿主或其他模块

宿主相关的问题找本项目维护者，其余找你自己团队。
