import type { WorkspaceModule } from '../../app/modules'
import PendingToolPage from '../PendingToolPage.vue'

const module: WorkspaceModule = {
  key: 'excel-tools',
  label: '数据处理',
  entry: 'excel-tools',
  routes: [
    {
      path: 'excel-tools',
      name: 'excel-tools',
      // 接入时把 component 换成自己的页面，props 一并删掉。
      component: PendingToolPage,
      props: { name: '数据处理', dir: 'src/modules/excel-tools/' },
      meta: { nav: 'excel-tools' },
    },
  ],
}

export default module
