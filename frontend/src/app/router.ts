import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('../pages/LoginPage.vue'),
    },
    {
      path: '/',
      name: 'workspace',
      component: () => import('../pages/WorkspacePage.vue'),
      redirect: '/conversations/new',
      meta: { requiresAuth: true },
      children: [
        {
          path: 'datasets',
          name: 'datasets',
          component: () => import('../features/datasets/DatasetListPage.vue'),
          meta: { nav: 'datasets' },
        },
        {
          path: 'datasets/:datasetId',
          name: 'dataset-detail',
          component: () => import('../features/datasets/DatasetDetailPage.vue'),
          meta: { nav: 'datasets' },
        },
        {
          path: 'connections',
          name: 'connections',
          component: () => import('../features/connections/DataSourcePage.vue'),
          meta: { nav: 'connections' },
        },
        {
          path: 'reports',
          name: 'reports',
          redirect: '/reports/templates',
          meta: { nav: 'reports' },
        },
        {
          path: 'reports/templates',
          name: 'report-templates',
          component: () => import('../features/reports/ReportTemplatesPage.vue'),
          meta: { nav: 'reports' },
        },
        {
          path: 'reports/:sessionId',
          name: 'report-detail',
          component: () => import('../features/reports/ReportDetailPage.vue'),
          meta: { nav: 'reports' },
        },
        {
          path: 'conversations',
          name: 'conversations',
          redirect: '/conversations/new',
          meta: { nav: 'reports' },
        },
        {
          path: 'conversations/new',
          name: 'conversation-new',
          component: () => import('../features/conversations/ConversationView.vue'),
          meta: { nav: 'reports' },
        },
        {
          path: 'conversations/:conversationId',
          name: 'conversation-detail',
          component: () => import('../features/conversations/ConversationView.vue'),
          meta: { nav: 'reports' },
        },
        {
          path: 'capabilities',
          name: 'capabilities',
          component: () => import('../features/capabilities/CapabilitiesPlaceholderPage.vue'),
          meta: { nav: 'capabilities' },
        },
      ],
    },
    { path: '/:pathMatch(.*)*', name: 'not-found', component: () => import('../pages/NotFoundPage.vue') },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  await auth.ensureLoaded()
  if (to.meta.requiresAuth && !auth.isLoggedIn) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  if (to.path === '/login' && auth.isLoggedIn) {
    return { path: '/conversations/new' }
  }
})

export default router
