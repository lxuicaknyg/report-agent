/**
 * 参考实现 —— 照着抄，别照着改。
 *
 * 目录名带下划线前缀，且**没有注册进 `app/modules.ts`**：顶栏里看不到它，
 * 打包时因为没人 import 也会被 tree-shake 掉，线上零成本。但 tsconfig 的
 * include 覆盖 src/**，所以它照样过类型检查 —— 示例代码编译不过的话，CI 会
 * 先于你的同事发现。
 *
 * 这里把该演示的约定都演示了一遍：路由与顶栏高亮、带命名空间的接口调用、
 * 加前缀的 store id 和 localStorage key、用设计令牌的 scoped 样式。
 *
 * 接入步骤见 ../../../CONTRIBUTING_MODULES.md。
 */
import type { WorkspaceModule } from '../../app/modules'

const module: WorkspaceModule = {
  // 一个 key 同时管三件事，必须完全一致：
  //   1. 顶栏这一项的标识
  //   2. 路由里 meta.nav 的值（决定顶栏高亮哪一项）
  //   3. 接口命名空间 /api/<key>/v1/*（nginx 按这一段分发到你的容器）
  // 三者对不上，症状分别是：顶栏不亮、请求 404。
  key: 'example',
  label: '示例工具',
  entry: 'example',
  routes: [
    {
      // 相对于 /，不写开头的斜杠。别和宿主占用的路径撞，清单见文档第三节。
      path: 'example',
      name: 'example',
      component: () => import('./pages/ExamplePage.vue'),
      meta: { nav: 'example' },
    },
    {
      // 二级页面同样要带 meta.nav，否则用户点进来顶栏就不知道该亮哪一项了。
      path: 'example/:itemId',
      name: 'example-detail',
      component: () => import('./pages/ExamplePage.vue'),
      meta: { nav: 'example' },
    },
  ],
}

export default module
