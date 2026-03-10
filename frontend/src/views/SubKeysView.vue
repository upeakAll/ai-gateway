<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import {
  ElCard,
  ElTable,
  ElTableColumn,
  ElButton,
  ElTag,
  ElDialog,
  ElForm,
  ElFormItem,
  ElInput,
  ElInputNumber,
  ElMessage,
  ElMessageBox,
  ElProgress,
  ElTooltip,
  ElPageHeader
} from 'element-plus'
import { Plus, Delete, CopyDocument, Back } from '@element-plus/icons-vue'
import { keysApi } from '@/api/keys'
import type { SubKey, CreateSubKeyRequest, APIKey } from '@/api/types'

const router = useRouter()
const route = useRoute()

const parentKeyId = route.params.id as string

const loading = ref(false)
const subKeys = ref<SubKey[]>([])
const parentKey = ref<APIKey | null>(null)

const dialogVisible = ref(false)
const formLoading = ref(false)
const formRef = ref()
const formData = ref<CreateSubKeyRequest>({
  name: '',
  quota_total: 10,
  rpm_limit: 30
})

const rules = {
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }]
}

async function fetchData() {
  loading.value = true
  try {
    const [subKeysResponse, keyResponse] = await Promise.all([
      keysApi.listSubKeys(parentKeyId),
      keysApi.get(parentKeyId)
    ])
    subKeys.value = subKeysResponse.items
    parentKey.value = keyResponse
  } finally {
    loading.value = false
  }
}

function handleCreate() {
  formData.value = {
    name: '',
    quota_total: 10,
    rpm_limit: 30
  }
  dialogVisible.value = true
}

async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  formLoading.value = true
  try {
    await keysApi.createSubKey(parentKeyId, formData.value)
    ElMessage.success('创建成功')
    dialogVisible.value = false
    fetchData()
  } finally {
    formLoading.value = false
  }
}

async function handleDelete(subKey: SubKey) {
  await ElMessageBox.confirm(`确定要删除子Key "${subKey.name}" 吗？`, '确认删除', {
    type: 'warning'
  })
  await keysApi.deleteSubKey(parentKeyId, subKey.id)
  ElMessage.success('删除成功')
  fetchData()
}

function copyKey(key: string) {
  navigator.clipboard.writeText(key)
  ElMessage.success('已复制到剪贴板')
}

function getQuotaPercent(subKey: SubKey) {
  return subKey.quota_total > 0 ? (subKey.quota_used / subKey.quota_total) * 100 : 0
}

function goBack() {
  router.push({ name: 'keys' })
}

onMounted(() => {
  fetchData()
})
</script>

<template>
  <div class="sub-keys-view">
    <ElPageHeader :title="parentKey?.name || '子Key管理'" @back="goBack">
      <template #content>
        <span class="page-title">子Key管理</span>
      </template>
      <template #extra>
        <ElButton type="primary" :icon="Plus" @click="handleCreate">创建子Key</ElButton>
      </template>
    </ElPageHeader>

    <ElCard shadow="never" class="content-card">
      <ElTable :data="subKeys" v-loading="loading" stripe>
        <ElTableColumn prop="name" label="名称" min-width="120" />
        <ElTableColumn label="Key" min-width="200">
          <template #default="{ row }">
            <div class="key-cell">
              <ElTooltip :content="row.key" placement="top">
                <span class="key-text">{{ row.key.substring(0, 16) }}...</span>
              </ElTooltip>
              <ElButton link :icon="CopyDocument" @click="copyKey(row.key)" />
            </div>
          </template>
        </ElTableColumn>
        <ElTableColumn label="配额" min-width="150">
          <template #default="{ row }">
            <div class="quota-cell">
              <ElProgress
                :percentage="getQuotaPercent(row)"
                :color="getQuotaPercent(row) > 80 ? '#f56c6c' : '#67c23a'"
                :stroke-width="10"
              />
              <span class="quota-text">
                ${{ row.quota_used.toFixed(2) }} / ${{ row.quota_total.toFixed(2) }}
              </span>
            </div>
          </template>
        </ElTableColumn>
        <ElTableColumn prop="rpm_limit" label="RPM限制" width="100" />
        <ElTableColumn label="状态" width="80">
          <template #default="{ row }">
            <ElTag :type="row.is_active ? 'success' : 'danger'">
              {{ row.is_active ? '启用' : '禁用' }}
            </ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn label="创建时间" width="180">
          <template #default="{ row }">
            {{ new Date(row.created_at).toLocaleString() }}
          </template>
        </ElTableColumn>
        <ElTableColumn label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <ElButton link type="danger" :icon="Delete" @click="handleDelete(row)">
              删除
            </ElButton>
          </template>
        </ElTableColumn>
      </ElTable>

      <div v-if="subKeys.length === 0 && !loading" class="empty-state">
        <p>暂无子Key，点击上方按钮创建</p>
      </div>
    </ElCard>

    <!-- Create Dialog -->
    <ElDialog v-model="dialogVisible" title="创建子Key" width="500px">
      <ElForm ref="formRef" :model="formData" :rules="rules" label-width="100px">
        <ElFormItem label="名称" prop="name">
          <ElInput v-model="formData.name" placeholder="请输入子Key名称" />
        </ElFormItem>
        <ElFormItem label="配额">
          <ElInputNumber v-model="formData.quota_total" :min="0" :precision="2" style="width: 100%">
            <template #prefix>$</template>
          </ElInputNumber>
        </ElFormItem>
        <ElFormItem label="RPM限制">
          <ElInputNumber v-model="formData.rpm_limit" :min="1" style="width: 100%" />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="dialogVisible = false">取消</ElButton>
        <ElButton type="primary" :loading="formLoading" @click="handleSubmit">确定</ElButton>
      </template>
    </ElDialog>
  </div>
</template>

<style scoped>
.sub-keys-view {
  max-width: 1200px;
}

.page-title {
  font-size: 18px;
  font-weight: 600;
}

.content-card {
  margin-top: 20px;
}

.key-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.key-text {
  font-family: monospace;
  color: #606266;
}

.quota-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.quota-text {
  font-size: 12px;
  color: #909399;
}

.empty-state {
  padding: 40px;
  text-align: center;
  color: #909399;
}
</style>
