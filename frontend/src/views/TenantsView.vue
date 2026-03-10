<script setup lang="ts">
import { ref, onMounted } from 'vue'
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
import { Plus, Edit, Delete, Wallet } from '@element-plus/icons-vue'
import { tenantsApi } from '@/api/tenants'
import { channelsApi } from '@/api/channels'
import type { Tenant, CreateTenantRequest, Channel } from '@/api/types'

const loading = ref(false)
const tenants = ref<Tenant[]>([])
const channels = ref<Channel[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(10)

const dialogVisible = ref(false)
const dialogTitle = ref('创建租户')
const formLoading = ref(false)
const formRef = ref()
const isEdit = ref(false)
const currentId = ref('')
const formData = ref<CreateTenantRequest>({
  name: '',
  slug: '',
  quota_total: 100,
  billing_mode: 'prepaid',
  routing_strategy: 'weighted',
  fixed_channel_id: ''
})

const quotaDialogVisible = ref(false)
const quotaAmount = ref(0)

const rules = {
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
  slug: [
    { required: true, message: '请输入标识', trigger: 'blur' },
    { pattern: /^[a-z0-9-]+$/, message: '只能包含小写字母、数字和横线', trigger: 'blur' }
  ]
}

async function fetchData() {
  loading.value = true
  try {
    const response = await tenantsApi.list({ page: page.value, page_size: pageSize.value })
    tenants.value = response.items
    total.value = response.total
  } finally {
    loading.value = false
  }
}

async function fetchChannels() {
  try {
    const response = await channelsApi.list({ page_size: 100 })
    channels.value = response.items
  } catch {
    // Error handled
  }
}

function handleCreate() {
  isEdit.value = false
  dialogTitle.value = '创建租户'
  formData.value = {
    name: '',
    slug: '',
    quota_total: 100,
    billing_mode: 'prepaid',
    routing_strategy: 'weighted',
    fixed_channel_id: ''
  }
  dialogVisible.value = true
}

function handleEdit(tenant: Tenant) {
  isEdit.value = true
  dialogTitle.value = '编辑租户'
  currentId.value = tenant.id
  formData.value = {
    name: tenant.name,
    slug: tenant.slug,
    quota_total: tenant.quota_total,
    billing_mode: tenant.billing_mode,
    routing_strategy: tenant.routing_strategy,
    fixed_channel_id: tenant.fixed_channel_id || ''
  }
  dialogVisible.value = true
}

async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  formLoading.value = true
  try {
    if (isEdit.value) {
      await tenantsApi.update(currentId.value, formData.value)
      ElMessage.success('更新成功')
    } else {
      await tenantsApi.create(formData.value)
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    fetchData()
  } finally {
    formLoading.value = false
  }
}

async function handleDelete(tenant: Tenant) {
  await ElMessageBox.confirm(`确定要删除租户 "${tenant.name}" 吗？`, '确认删除', {
    type: 'warning'
  })
  await tenantsApi.delete(tenant.id)
  ElMessage.success('删除成功')
  fetchData()
}

function openQuotaDialog(tenant: Tenant) {
  currentId.value = tenant.id
  quotaAmount.value = 0
  quotaDialogVisible.value = true
}

async function handleAddQuota() {
  if (quotaAmount.value <= 0) {
    ElMessage.warning('请输入有效的金额')
    return
  }
  try {
    await tenantsApi.addQuota(currentId.value, quotaAmount.value)
    ElMessage.success('充值成功')
    quotaDialogVisible.value = false
    fetchData()
  } catch {
    // Error handled
  }
}

function getQuotaPercent(tenant: Tenant) {
  return tenant.quota_total > 0 ? (tenant.quota_used / tenant.quota_total) * 100 : 0
}

function getBillingModeTag(mode: string) {
  return mode === 'prepaid' ? 'success' : 'warning'
}

function getRoutingStrategyLabel(strategy: string) {
  const labels: Record<string, string> = {
    weighted: '加权轮询',
    cost_optimized: '成本优先',
    fixed: '固定路由'
  }
  return labels[strategy] || strategy
}

function handlePageChange(val: number) {
  page.value = val
  fetchData()
}

onMounted(() => {
  fetchData()
  fetchChannels()
})
</script>

<template>
  <div class="tenants-view">
    <div class="page-header">
      <h2>租户管理</h2>
      <ElButton type="primary" :icon="Plus" @click="handleCreate">创建租户</ElButton>
    </div>

    <ElCard shadow="never">
      <ElTable :data="tenants" v-loading="loading" stripe>
        <ElTableColumn prop="name" label="名称" min-width="120" />
        <ElTableColumn prop="slug" label="标识" min-width="100">
          <template #default="{ row }">
            <code class="slug-text">{{ row.slug }}</code>
          </template>
        </ElTableColumn>
        <ElTableColumn label="配额" min-width="180">
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
        <ElTableColumn prop="billing_mode" label="计费模式" width="100">
          <template #default="{ row }">
            <ElTag :type="getBillingModeTag(row.billing_mode)" size="small">
              {{ row.billing_mode === 'prepaid' ? '预付费' : '后付费' }}
            </ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn prop="routing_strategy" label="路由策略" width="100">
          <template #default="{ row }">
            <ElTag size="small">{{ getRoutingStrategyLabel(row.routing_strategy) }}</ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn label="状态" width="80">
          <template #default="{ row }">
            <ElTag :type="row.is_active ? 'success' : 'danger'" size="small">
              {{ row.is_active ? '启用' : '禁用' }}
            </ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn label="创建时间" width="180">
          <template #default="{ row }">
            {{ new Date(row.created_at).toLocaleString() }}
          </template>
        </ElTableColumn>
        <ElTableColumn label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <ElButton link type="primary" :icon="Edit" @click="handleEdit(row)">编辑</ElButton>
            <ElButton link type="success" :icon="Wallet" @click="openQuotaDialog(row)">充值</ElButton>
            <ElButton link type="danger" :icon="Delete" @click="handleDelete(row)">删除</ElButton>
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

    <!-- Create/Edit Dialog -->
    <ElDialog v-model="dialogVisible" :title="dialogTitle" width="500px">
      <ElForm ref="formRef" :model="formData" :rules="rules" label-width="100px">
        <ElFormItem label="名称" prop="name">
          <ElInput v-model="formData.name" placeholder="请输入租户名称" />
        </ElFormItem>
        <ElFormItem label="标识" prop="slug">
          <ElInput v-model="formData.slug" placeholder="如: my-company" :disabled="isEdit" />
        </ElFormItem>
        <ElFormItem label="配额">
          <ElInputNumber v-model="formData.quota_total" :min="0" :precision="2" style="width: 100%">
            <template #prefix>$</template>
          </ElInputNumber>
        </ElFormItem>
        <ElFormItem label="计费模式">
          <ElSelect v-model="formData.billing_mode" style="width: 100%">
            <ElOption label="预付费" value="prepaid" />
            <ElOption label="后付费" value="postpaid" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="路由策略">
          <ElSelect v-model="formData.routing_strategy" style="width: 100%">
            <ElOption label="加权轮询" value="weighted" />
            <ElOption label="成本优先" value="cost_optimized" />
            <ElOption label="固定路由" value="fixed" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem v-if="formData.routing_strategy === 'fixed'" label="固定渠道">
          <ElSelect v-model="formData.fixed_channel_id" placeholder="选择渠道" style="width: 100%">
            <ElOption
              v-for="channel in channels"
              :key="channel.id"
              :label="channel.name"
              :value="channel.id"
            />
          </ElSelect>
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="dialogVisible = false">取消</ElButton>
        <ElButton type="primary" :loading="formLoading" @click="handleSubmit">确定</ElButton>
      </template>
    </ElDialog>

    <!-- Quota Dialog -->
    <ElDialog v-model="quotaDialogVisible" title="充值配额" width="400px">
      <ElForm label-width="100px">
        <ElFormItem label="充值金额">
          <ElInputNumber v-model="quotaAmount" :min="0.01" :precision="2" style="width: 100%">
            <template #prefix>$</template>
          </ElInputNumber>
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="quotaDialogVisible = false">取消</ElButton>
        <ElButton type="primary" @click="handleAddQuota">确认充值</ElButton>
      </template>
    </ElDialog>
  </div>
</template>

<style scoped>
.tenants-view {
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

.slug-text {
  font-family: monospace;
  font-size: 12px;
  background-color: #f5f5f5;
  padding: 2px 6px;
  border-radius: 4px;
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
