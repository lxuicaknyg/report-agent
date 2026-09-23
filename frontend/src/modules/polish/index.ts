import type { WorkspaceModule } from '../../app/modules'
import PendingToolPage from '../PendingToolPage.vue'

const module: WorkspaceModule = {
  key: 'polish',
  label: '片段润色',
  entry: 'polish',
  routes: [
    {
      path: 'polish',
      name: 'polish',
      // 接入时把 component 换成自己的页面，props 一并删掉。
      component: PendingToolPage,
      props: { name: '片段润色', dir: 'src/modules/polish/' },
      meta: { nav: 'polish' },
    },
  ],
}

export default module
