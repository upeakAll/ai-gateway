<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import {
  ElCard,
  ElTable,
  ElTableColumn,
  ElButton,
  ElTag,
  ElPagination,
  ElDialog,
  ElForm,
  ElFormItem,
  ElInput,
  ElInputNumber,
  ElSelect,
  ElSwitch,
  ElMessage,
  ElMessageBox,
  ElProgress,
  ElTooltip
} from 'element-plus'
import { Plus, Refresh, Delete, View, CopyDocument } from '@element-plus/icons-vue'
import { keysApi } from '@/api/keys'
import { tenantsApi } from '@/api/tenants'
import type { APIKey, CreateAPIKeyRequest, Tenant } from '@/api/types'

const router = useRouter()

const loading = ref(false)
const keys = ref<APIKey[]>([])
const tenants = ref<Tenant[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(10)

const dialogVisible = ref(false)
const dialogTitle = ref('创建Key')
const formLoading = ref(false)
const formRef = ref()
const formData = ref<CreateAPIKeyRequest>({
  tenant_id: '',
  name: '',
  quota_total: 100,
  rpm_limit: 60,
  tpm_limit: 100000,
  allowed_models: []
})

const rules = {
  tenant_id: [{ required: true, message: '请选择租户', trigger: 'change' }],
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }]
}

async function fetchData() {
  loading.value = true
  try {
    const response = await keysApi.list({ page: page.value, page_size: pageSize.value })
    keys.value = response.items
    total.value = response.total
  } finally {
    loading.value = false
  }
}

async function fetchTenants() {
  try {
    const response = await tenantsApi.list({ page_size: 100 })
    tenants.value = response.items
  } catch {
    // Error handled
  }
}

function handleCreate() {
  dialogTitle.value = '创建Key'
  formData.value = {
    tenant_id: '',
    name: '',
    quota_total: 100,
    rpm_limit: 60,
    tpm_limit: 100000,
    allowed_models: []
  }
  dialogVisible.value = true
}

async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  formLoading.value = true
  try {
    await keysApi.create(formData.value)
    ElMessage.success('创建成功')
    dialogVisible.value = false
    fetchData()
  } finally {
    formLoading.value = false
  }
}

async function handleDelete(key: APIKey) {
  await ElMessageBox.confirm(`确定要删除Key "${key.name}" 吗？`, '确认删除', {
    type: 'warning'
  })
  await keysApi.delete(key.id)
  ElMessage.success('删除成功')
  fetchData()
}

async function handleRegenerate(key: APIKey) {
  await ElMessageBox.confirm('重新生成Key会使旧Key立即失效，确定继续吗？', '确认操作', {
    type: 'warning'
  })
  await keysApi.regenerate(key.id)
  ElMessage.success('Key已重新生成')
  fetchData()
}

function copyKey(key: string) {
  navigator.clipboard.writeText(key)
  ElMessage.success('已复制到剪贴板')
}

function viewSubKeys(key: APIKey) {
  router.push({ name: 'sub-keys', params: { id: key.id } })
}

function getQuotaPercent(key: APIKey) {
  return key.quota_total > 0 ? (key.quota_used / key.quota_total) * 100 : 0
}

function handlePageChange(val: number) {
  page.value = val
  fetchData()
}

onMounted(() => {
  fetchData()
  fetchTenants()
})
</script>

<template>
  <div class="keys-view">
    <div class="page-header">
      <h2>Key管理</h2>
      <ElButton type="primary" :icon="Plus" @click="handleCreate">创建Key</ElButton>
    </div>

    <ElCard shadow="never">
      <ElTable :data="keys" v-loading="loading" stripe>
        <ElTableColumn prop="name" label="名称" min-width="120" />
        <ElTableColumn label="Key" min-width="200">
          <template #default="{ row }">
            <div class="key-cell">
              <ElTooltip :content="row.key" placement="top">
                <span class="key-text">{{ row.key.substring(0, 12) }}...</span>
              </ElTooltip>
              <ElButton link :icon="CopyDocument" @click="copyKey(row.key)" />
            </div>
          </template>
        </ElTableColumn>
        <ElTableColumn prop="tenant_id" label="租户ID" min-width="120">
          <template #default="{ row }">
            <span class="tenant-id">{{ row.tenant_id.substring(0, 8) }}...</span>
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
        <ElTableColumn prop="tpm_limit" label="TPM限制" width="100" />
        <ElTableColumn label="状态" width="80">
          <template #default="{ row }">
            <ElTag :type="row.is_active ? 'success' : 'danger'">
              {{ row.is_active ? '启用' : '禁用' }}
            </ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn label="操作" width="240" fixed="right">
          <template #default="{ row }">
            <ElButton link type="primary" :icon="View" @click="viewSubKeys(row)">
              子Key
            </ElButton>
            <ElButton link type="warning" :icon="Refresh" @click="handleRegenerate(row)">
              重置
            </ElButton>
            <ElButton link type="danger" :icon="Delete" @click="handleDelete(row)">
              删除
            </ElButton>
          </template>
        </ElTableColumn>
      </ElTable>

      <div class="pagination">
        <ElPagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="total"
          layout="total, prev, pager, next"
          @current-change="handlePageChange"
        />
      </div>
    </ElCard>

    <!-- Create Dialog -->
    <ElDialog v-model="dialogVisible" :title="dialogTitle" width="500px">
      <ElForm ref="formRef" :model="formData" :rules="rules" label-width="100px">
        <ElFormItem label="租户" prop="tenant_id">
          <ElSelect v-model="formData.tenant_id" placeholder="请选择租户" style="width: 100%">
            <ElOption
              v-for="tenant in tenants"
              :key="tenant.id"
              :label="tenant.name"
              :value="tenant.id"
            />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="名称" prop="name">
          <ElInput v-model="formData.name" placeholder="请输入Key名称" />
        </ElFormItem>
        <ElFormItem label="配额">
          <ElInputNumber v-model="formData.quota_total" :min="0" :precision="2" style="width: 100%">
            <template #prefix>$</template>
          </ElInputNumber>
        </ElFormItem>
        <ElFormItem label="RPM限制">
          <ElInputNumber v-model="formData.rpm_limit" :min="1" style="width: 100%" />
        </ElFormItem>
        <ElFormItem label="TPM限制">
          <ElInputNumber v-model="formData.tpm_limit" :min="1" style="width: 100%" />
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
.keys-view {
  max-width: 1400px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.page-header h2 {
  margin: 0;
  color: #303133;
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

.tenant-id {
  font-family: monospace;
  color: #909399;
  font-size: 12px;
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

.pagination {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}
</style>
