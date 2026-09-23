import type { WorkspaceModule } from '../../app/modules'
import PendingToolPage from '../PendingToolPage.vue'

const module: WorkspaceModule = {
  key: 'prose',
  label: '报告摘要',
  entry: 'prose',
  routes: [
    {
      path: 'prose',
      name: 'prose',
      // 接入时把 component 换成自己的页面，props 一并删掉。
      component: PendingToolPage,
      props: { name: '报告摘要', dir: 'src/modules/prose/' },
      meta: { nav: 'prose' },
    },
  ],
}

export default module
