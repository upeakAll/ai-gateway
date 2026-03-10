<script setup lang="ts">
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElForm, ElFormItem, ElInput, ElButton, ElCard, ElMessage } from 'element-plus'
import { User, Lock } from '@element-plus/icons-vue'
import { authApi } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const formRef = ref()
const loading = ref(false)
const form = ref({
  username: '',
  password: ''
})

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }]
}

async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  loading.value = true
  try {
    const response = await authApi.login(form.value)
    authStore.setToken(response.access_token)
    authStore.setUser(response.user)
    ElMessage.success('登录成功')

    const redirect = route.query.redirect as string
    router.push(redirect || { name: 'dashboard' })
  } catch {
    // Error handled by interceptor
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-container">
    <ElCard class="login-card">
      <template #header>
        <div class="login-header">
          <h2>AI Gateway</h2>
          <p>企业级AI网关管理系统</p>
        </div>
      </template>
      <ElForm ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent="handleSubmit">
        <ElFormItem label="用户名" prop="username">
          <ElInput
            v-model="form.username"
            placeholder="请输入用户名"
            :prefix-icon="User"
            size="large"
          />
        </ElFormItem>
        <ElFormItem label="密码" prop="password">
          <ElInput
            v-model="form.password"
            type="password"
            placeholder="请输入密码"
            :prefix-icon="Lock"
            size="large"
            show-password
          />
        </ElFormItem>
        <ElFormItem>
          <ElButton type="primary" size="large" :loading="loading" @click="handleSubmit" style="width: 100%">
            登录
          </ElButton>
        </ElFormItem>
      </ElForm>
    </ElCard>
  </div>
</template>

<style scoped>
.login-container {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.login-card {
  width: 400px;
}

.login-header {
  text-align: center;
}

.login-header h2 {
  margin: 0;
  color: #303133;
}

.login-header p {
  margin: 8px 0 0;
  color: #909399;
  font-size: 14px;
}
</style>
