<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useAppStore } from '@/stores/app'
import {
  ElContainer,
  ElAside,
  ElHeader,
  ElMain,
  ElMenu,
  ElMenuItem,
  ElSubMenu,
  ElDropdown,
  ElDropdownMenu,
  ElDropdownItem,
  ElAvatar,
  ElBadge,
  ElIcon
} from 'element-plus'
import {
  Monitor,
  Key,
  Connection,
  Document,
  TrendCharts,
  Setting,
  User,
  SwitchButton,
  Fold,
  Expand
} from '@element-plus/icons-vue'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const appStore = useAppStore()

const activeMenu = computed(() => route.name as string)

const menuItems = [
  { index: 'dashboard', title: '仪表盘', icon: Monitor },
  { index: 'keys', title: 'Key管理', icon: Key },
  { index: 'channels', title: '渠道管理', icon: Connection },
  { index: 'logs', title: '日志查询', icon: Document },
  { index: 'usage', title: '用量统计', icon: TrendCharts },
  { index: 'mcp', title: 'MCP管理', icon: Setting },
  { index: 'tenants', title: '租户管理', icon: User }
]

function handleMenuSelect(index: string) {
  router.push({ name: index })
}

function handleLogout() {
  authStore.logout()
  router.push({ name: 'login' })
}

function handleCommand(command: string) {
  if (command === 'logout') {
    handleLogout()
  }
}
</script>

<template>
  <ElContainer class="main-layout">
    <ElAside :width="appStore.sidebarCollapsed ? '64px' : '220px'" class="sidebar">
      <div class="logo">
        <span v-if="!appStore.sidebarCollapsed">AI Gateway</span>
        <span v-else>AI</span>
      </div>
      <ElMenu
        :default-active="activeMenu"
        :collapse="appStore.sidebarCollapsed"
        :router="false"
        @select="handleMenuSelect"
        background-color="#304156"
        text-color="#bfcbd9"
        active-text-color="#409EFF"
      >
        <ElMenuItem v-for="item in menuItems" :key="item.index" :index="item.index">
          <ElIcon><component :is="item.icon" /></ElIcon>
          <template #title>{{ item.title }}</template>
        </ElMenuItem>
      </ElMenu>
    </ElAside>
    <ElContainer>
      <ElHeader class="header">
        <div class="header-left">
          <div class="collapse-btn" @click="appStore.toggleSidebar">
            <ElIcon :size="20">
              <Fold v-if="!appStore.sidebarCollapsed" />
              <Expand v-else />
            </ElIcon>
          </div>
        </div>
        <div class="header-right">
          <ElDropdown @command="handleCommand">
            <div class="user-info">
              <ElAvatar :size="32" :icon="User" />
              <span class="username">{{ authStore.user?.username || '用户' }}</span>
            </div>
            <template #dropdown>
              <ElDropdownMenu>
                <ElDropdownItem command="profile">个人信息</ElDropdownItem>
                <ElDropdownItem command="logout" divided>
                  <ElIcon><SwitchButton /></ElIcon>
                  退出登录
                </ElDropdownItem>
              </ElDropdownMenu>
            </template>
          </ElDropdown>
        </div>
      </ElHeader>
      <ElMain class="main-content">
        <RouterView v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </RouterView>
      </ElMain>
    </ElContainer>
  </ElContainer>
</template>

<style scoped>
.main-layout {
  height: 100vh;
}

.sidebar {
  background-color: #304156;
  transition: width 0.3s;
  overflow: hidden;
}

.logo {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 20px;
  font-weight: bold;
  background-color: #263445;
}

.el-menu {
  border-right: none;
}

.header {
  background-color: #fff;
  box-shadow: 0 1px 4px rgba(0, 21, 41, 0.08);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
}

.header-left {
  display: flex;
  align-items: center;
}

.collapse-btn {
  cursor: pointer;
  padding: 10px;
  border-radius: 4px;
  transition: background-color 0.3s;
}

.collapse-btn:hover {
  background-color: #f5f5f5;
}

.header-right {
  display: flex;
  align-items: center;
}

.user-info {
  display: flex;
  align-items: center;
  cursor: pointer;
  padding: 5px 10px;
  border-radius: 4px;
  transition: background-color 0.3s;
}

.user-info:hover {
  background-color: #f5f5f5;
}

.username {
  margin-left: 8px;
  color: #333;
}

.main-content {
  background-color: #f0f2f5;
  padding: 20px;
  overflow-y: auto;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
