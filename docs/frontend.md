# 前端设计

## 技术栈

| 技术 | 版本 | 用途 |
|------|------|------|
| Vue | 3.5 | 前端框架 |
| TypeScript | 5.7 | 类型安全 |
| Element Plus | 2.9 | UI 组件库 |
| Pinia | 2.3 | 状态管理 |
| Vue Router | 4.5 | 路由管理 |
| Axios | 1.7 | HTTP 客户端 |
| ECharts | 5.5 | 图表可视化 |
| Vite | 6.0 | 构建工具 |

---

## 项目结构

```
frontend/
├── public/
│   └── vite.svg
├── src/
│   ├── api/                    # API 调用层
│   │   ├── client.ts           # Axios 客户端配置
│   │   ├── types.ts            # TypeScript 类型定义
│   │   ├── auth.ts             # 认证 API
│   │   ├── tenants.ts          # 租户 API
│   │   ├── keys.ts             # Key 管理 API
│   │   ├── channels.ts         # 渠道 API
│   │   ├── logs.ts             # 日志 API
│   │   ├── usage.ts            # 用量 API
│   │   ├── mcp.ts              # MCP API
│   │   └── health.ts           # 健康检查 API
│   ├── layouts/                # 布局组件
│   │   └── MainLayout.vue      # 主布局
│   ├── views/                  # 页面组件
│   │   ├── LoginView.vue       # 登录页
│   │   ├── DashboardView.vue   # 仪表盘
│   │   ├── KeysView.vue        # Key 管理
│   │   ├── SubKeysView.vue     # 子 Key 管理
│   │   ├── ChannelsView.vue    # 渠道管理
│   │   ├── LogsView.vue        # 日志查询
│   │   ├── UsageView.vue       # 用量统计
│   │   ├── MCPView.vue         # MCP 管理
│   │   └── TenantsView.vue     # 租户管理
│   ├── stores/                 # Pinia 状态管理
│   │   ├── auth.ts             # 认证状态
│   │   └── app.ts              # 应用状态
│   ├── router/                 # 路由配置
│   │   └── index.ts
│   ├── main.ts                 # 应用入口
│   └── App.vue                 # 根组件
├── package.json
├── vite.config.ts
├── tsconfig.json
├── nginx.conf
└── Dockerfile
```

---

## 路由配置

```typescript
const router = createRouter({
  history: createWebHistory(),
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
        { path: '', name: 'dashboard', component: DashboardView },
        { path: 'keys', name: 'keys', component: KeysView },
        { path: 'keys/:id/sub-keys', name: 'sub-keys', component: SubKeysView },
        { path: 'channels', name: 'channels', component: ChannelsView },
        { path: 'logs', name: 'logs', component: LogsView },
        { path: 'usage', name: 'usage', component: UsageView },
        { path: 'mcp', name: 'mcp', component: MCPView },
        { path: 'tenants', name: 'tenants', component: TenantsView }
      ]
    }
  ]
})

// 路由守卫
router.beforeEach((to, from, next) => {
  const authStore = useAuthStore()

  if (to.meta.requiresAuth !== false && !authStore.isAuthenticated) {
    next({ name: 'login', query: { redirect: to.fullPath } })
  } else {
    next()
  }
})
```

---

## 状态管理

### Auth Store

```typescript
export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(null)
  const user = ref<UserInfo | null>(null)

  const isAuthenticated = computed(() => !!token.value)

  function setToken(newToken: string) {
    token.value = newToken
  }

  function setUser(newUser: UserInfo) {
    user.value = newUser
  }

  function logout() {
    token.value = null
    user.value = null
  }

  function getAuthHeader() {
    return token.value ? { Authorization: `Bearer ${token.value}` } : {}
  }

  return {
    token, user, isAuthenticated,
    setToken, setUser, logout, getAuthHeader
  }
}, {
  persist: true  // 持久化到 localStorage
})
```

### App Store

```typescript
export const useAppStore = defineStore('app', () => {
  const sidebarCollapsed = ref(false)
  const loading = ref(false)

  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }

  function setLoading(value: boolean) {
    loading.value = value
  }

  return { sidebarCollapsed, loading, toggleSidebar, setLoading }
}, {
  persist: true
})
```

---

## API 客户端

### Axios 配置

```typescript
const instance = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' }
})

// 请求拦截器
instance.interceptors.request.use((config) => {
  const authStore = useAuthStore()
  const authHeader = authStore.getAuthHeader()
  config.headers = { ...config.headers, ...authHeader }
  return config
})

// 响应拦截器
instance.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      const authStore = useAuthStore()
      authStore.logout()
      router.push({ name: 'login' })
      ElMessage.error('登录已过期')
    }
    return Promise.reject(error)
  }
)
```

### API 模块示例

```typescript
// keys.ts
export const keysApi = {
  list(params?: PaginationParams) {
    return api.get<PaginatedResponse<APIKey>>('/admin/keys', { params })
  },

  create(data: CreateAPIKeyRequest) {
    return api.post<APIKey>('/admin/keys', data)
  },

  update(id: string, data: UpdateAPIKeyRequest) {
    return api.patch<APIKey>(`/admin/keys/${id}`, data)
  },

  delete(id: string) {
    return api.delete(`/admin/keys/${id}`)
  }
}
```

---

## 页面组件

### Dashboard

仪表盘页面展示系统概览：

- 统计卡片（请求数、Token数、成本、延迟）
- 请求趋势图
- 模型成本分布饼图
- 模型使用排行表

```vue
<template>
  <div class="dashboard">
    <!-- 统计卡片 -->
    <ElRow :gutter="20">
      <ElCol :xs="24" :sm="12" :md="6" v-for="stat in stats">
        <ElCard shadow="hover">
          <ElStatistic :title="stat.title" :value="stat.value" />
        </ElCard>
      </ElCol>
    </ElRow>

    <!-- 图表 -->
    <ElRow :gutter="20">
      <ElCol :span="16">
        <ElCard>
          <v-chart :option="chartOption" autoresize style="height: 300px" />
        </ElCard>
      </ElCol>
      <ElCol :span="8">
        <ElCard>
          <v-chart :option="pieOption" autoresize style="height: 300px" />
        </ElCard>
      </ElCol>
    </ElRow>
  </div>
</template>
```

### Key 管理

Key 管理页面功能：

- 列表展示（分页、搜索）
- 创建/编辑 Key
- 查看子 Key
- 重置/删除 Key
- 配额进度条显示

### 渠道管理

渠道管理页面功能：

- 列表展示渠道状态
- 创建/编辑渠道
- 测试渠道连通性
- 管理模型配置
- 重置熔断器

---

## UI 组件

### Element Plus 主题

```css
:root {
  --el-color-primary: #409EFF;
  --el-color-success: #67C23A;
  --el-color-warning: #E6A23C;
  --el-color-danger: #F56C6C;
  --el-color-info: #909399;
}
```

### 常用组件

- `ElTable` - 数据表格
- `ElForm` - 表单
- `ElDialog` - 弹窗
- `ElCard` - 卡片
- `ElPagination` - 分页
- `ElTag` - 标签
- `ElProgress` - 进度条
- `ElStatistic` - 统计数值

---

## 图表

### ECharts 配置

```typescript
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, PieChart, BarChart } from 'echarts/charts'
import { TitleComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import VChart from 'vue-echarts'

use([CanvasRenderer, LineChart, PieChart, BarChart, TitleComponent, TooltipComponent, LegendComponent])
```

### 图表示例

```vue
<v-chart
  :option="{
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: dates },
    yAxis: { type: 'value' },
    series: [{ type: 'line', data: values }]
  }"
  autoresize
  style="height: 300px"
/>
```

---

## 构建配置

### Vite 配置

```typescript
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) }
  },
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://localhost:8000', rewrite: (p) => p.replace(/^\/api/, '') },
      '/v1': { target: 'http://localhost:8000' },
      '/mcp': { target: 'http://localhost:8000' },
      '/admin': { target: 'http://localhost:8000' }
    }
  }
})
```

### Docker 构建

```dockerfile
# Build stage
FROM node:22-alpine AS build
WORKDIR /app
RUN npm install -g pnpm
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
RUN pnpm run build

# Production stage
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

---

## 开发命令

```bash
# 安装依赖
pnpm install

# 开发服务器
pnpm run dev

# 构建生产版本
pnpm run build

# 预览生产版本
pnpm run preview

# 代码检查
pnpm run lint

# 代码格式化
pnpm run format
```

---

*最后更新: 2026-03-10*
