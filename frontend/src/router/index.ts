import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { requiresAuth: false }
    },
    {
      path: '/',
      component: () => import('@/layouts/MainLayout.vue'),
      meta: { requiresAuth: true },
      children: [
        {
          path: '',
          name: 'dashboard',
          component: () => import('@/views/DashboardView.vue'),
          meta: { title: '仪表盘' }
        },
        {
          path: 'keys',
          name: 'keys',
          component: () => import('@/views/KeysView.vue'),
          meta: { title: 'Key管理' }
        },
        {
          path: 'keys/:id/sub-keys',
          name: 'sub-keys',
          component: () => import('@/views/SubKeysView.vue'),
          meta: { title: '子Key管理' }
        },
        {
          path: 'channels',
          name: 'channels',
          component: () => import('@/views/ChannelsView.vue'),
          meta: { title: '渠道管理' }
        },
        {
          path: 'logs',
          name: 'logs',
          component: () => import('@/views/LogsView.vue'),
          meta: { title: '日志查询' }
        },
        {
          path: 'usage',
          name: 'usage',
          component: () => import('@/views/UsageView.vue'),
          meta: { title: '用量统计' }
        },
        {
          path: 'mcp',
          name: 'mcp',
          component: () => import('@/views/MCPView.vue'),
          meta: { title: 'MCP管理' }
        },
        {
          path: 'tenants',
          name: 'tenants',
          component: () => import('@/views/TenantsView.vue'),
          meta: { title: '租户管理' }
        }
      ]
    }
  ]
})

router.beforeEach((to, _from, next) => {
  const authStore = useAuthStore()

  if (to.meta.requiresAuth !== false && !authStore.isAuthenticated) {
    next({ name: 'login', query: { redirect: to.fullPath } })
  } else {
    next()
  }
})

export default router
