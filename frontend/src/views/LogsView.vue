<script setup lang="ts">
import { ref, onMounted } from 'vue'
import {
  ElCard,
  ElTable,
  ElTableColumn,
  ElButton,
  ElTag,
  ElPagination,
  ElForm,
  ElFormItem,
  ElInput,
  ElSelect,
  ElDatePicker,
  ElMessage,
  ElDialog,
  ElDescriptions,
  ElDescriptionsItem,
  ElTooltip
} from 'element-plus'
import { Search, Download, View } from '@element-plus/icons-vue'
import { logsApi } from '@/api/logs'
import { keysApi } from '@/api/keys'
import { channelsApi } from '@/api/channels'
import type { UsageLog, UsageLogQuery, APIKey, Channel } from '@/api/types'

const loading = ref(false)
const logs = ref<UsageLog[]>([])
const total = ref(0)

const queryParams = ref<UsageLogQuery>({
  page: 1,
  page_size: 20,
  status: undefined,
  model_name: '',
  start_time: '',
  end_time: ''
})

const keys = ref<APIKey[]>([])
const channels = ref<Channel[]>([])

const detailDialogVisible = ref(false)
const currentLog = ref<UsageLog | null>(null)

async function fetchData() {
  loading.value = true
  try {
    const response = await logsApi.list(queryParams.value)
    logs.value = response.items
    total.value = response.total
  } finally {
    loading.value = false
  }
}

async function fetchFilters() {
  try {
    const [keysResponse, channelsResponse] = await Promise.all([
      keysApi.list({ page_size: 100 }),
      channelsApi.list({ page_size: 100 })
    ])
    keys.value = keysResponse.items
    channels.value = channelsResponse.items
  } catch {
    // Error handled
  }
}

function handleSearch() {
  queryParams.value.page = 1
  fetchData()
}

function handleReset() {
  queryParams.value = {
    page: 1,
    page_size: 20,
    status: undefined,
    model_name: '',
    start_time: '',
    end_time: ''
  }
  fetchData()
}

async function handleExport() {
  try {
    const blob = await logsApi.export({
      status: queryParams.value.status,
      start_time: queryParams.value.start_time,
      end_time: queryParams.value.end_time
    })
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `usage_logs_${new Date().toISOString().split('T')[0]}.csv`
    link.click()
    window.URL.revokeObjectURL(url)
    ElMessage.success('导出成功')
  } catch {
    // Error handled
  }
}

function viewDetail(log: UsageLog) {
  currentLog.value = log
  detailDialogVisible.value = true
}

function handlePageChange(val: number) {
  queryParams.value.page = val
  fetchData()
}

function handleDateChange(val: [Date, Date] | null) {
  if (val) {
    queryParams.value.start_time = val[0].toISOString()
    queryParams.value.end_time = val[1].toISOString()
  } else {
    queryParams.value.start_time = ''
    queryParams.value.end_time = ''
  }
}

onMounted(() => {
  fetchData()
  fetchFilters()
})
</script>

<template>
  <div class="logs-view">
    <div class="page-header">
      <h2>日志查询</h2>
    </div>

    <ElCard shadow="never" class="filter-card">
      <ElForm :inline="true" :model="queryParams" class="filter-form">
        <ElFormItem label="状态">
          <ElSelect v-model="queryParams.status" placeholder="全部" clearable style="width: 120px">
            <ElOption label="成功" value="success" />
            <ElOption label="失败" value="error" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="模型">
          <ElInput v-model="queryParams.model_name" placeholder="模型名称" clearable style="width: 150px" />
        </ElFormItem>
        <ElFormItem label="时间范围">
          <ElDatePicker
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            @change="handleDateChange"
            style="width: 240px"
          />
        </ElFormItem>
        <ElFormItem>
          <ElButton type="primary" :icon="Search" @click="handleSearch">查询</ElButton>
          <ElButton @click="handleReset">重置</ElButton>
          <ElButton type="success" :icon="Download" @click="handleExport">导出</ElButton>
        </ElFormItem>
      </ElForm>
    </ElCard>

    <ElCard shadow="never" class="table-card">
      <ElTable :data="logs" v-loading="loading" stripe>
        <ElTableColumn prop="request_id" label="请求ID" min-width="180">
          <template #default="{ row }">
            <ElTooltip :content="row.request_id" placement="top">
              <span class="id-text">{{ row.request_id.substring(0, 8) }}...</span>
            </ElTooltip>
          </template>
        </ElTableColumn>
        <ElTableColumn prop="model_name" label="模型" min-width="120" />
        <ElTableColumn label="Token" min-width="120">
          <template #default="{ row }">
            {{ row.prompt_tokens }} / {{ row.completion_tokens }}
          </template>
        </ElTableColumn>
        <ElTableColumn prop="total_tokens" label="总Token" width="100" />
        <ElTableColumn prop="cost_usd" label="成本(USD)" width="100">
          <template #default="{ row }">
            ${{ row.cost_usd.toFixed(6) }}
          </template>
        </ElTableColumn>
        <ElTableColumn prop="latency_ms" label="延迟(ms)" width="100" />
        <ElTableColumn label="状态" width="80">
          <template #default="{ row }">
            <ElTag :type="row.status === 'success' ? 'success' : 'danger'">
              {{ row.status === 'success' ? '成功' : '失败' }}
            </ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn label="时间" width="180">
          <template #default="{ row }">
            {{ new Date(row.created_at).toLocaleString() }}
          </template>
        </ElTableColumn>
        <ElTableColumn label="操作" width="80" fixed="right">
          <template #default="{ row }">
            <ElButton link type="primary" :icon="View" @click="viewDetail(row)">详情</ElButton>
          </template>
        </ElTableColumn>
      </ElTable>

      <div class="pagination">
        <ElPagination
          v-model:current-page="queryParams.page"
          :page-size="queryParams.page_size"
          :total="total"
          layout="total, prev, pager, next"
          @current-change="handlePageChange"
        />
      </div>
    </ElCard>

    <!-- Detail Dialog -->
    <ElDialog v-model="detailDialogVisible" title="日志详情" width="600px">
      <ElDescriptions v-if="currentLog" :column="2" border>
        <ElDescriptionsItem label="请求ID" :span="2">{{ currentLog.request_id }}</ElDescriptionsItem>
        <ElDescriptionsItem label="租户ID">{{ currentLog.tenant_id }}</ElDescriptionsItem>
        <ElDescriptionsItem label="API Key ID">{{ currentLog.api_key_id }}</ElDescriptionsItem>
        <ElDescriptionsItem label="渠道ID">{{ currentLog.channel_id }}</ElDescriptionsItem>
        <ElDescriptionsItem label="模型">{{ currentLog.model_name }}</ElDescriptionsItem>
        <ElDescriptionsItem label="Prompt Tokens">{{ currentLog.prompt_tokens }}</ElDescriptionsItem>
        <ElDescriptionsItem label="Completion Tokens">{{ currentLog.completion_tokens }}</ElDescriptionsItem>
        <ElDescriptionsItem label="总Token">{{ currentLog.total_tokens }}</ElDescriptionsItem>
        <ElDescriptionsItem label="成本">${{ currentLog.cost_usd.toFixed(6) }}</ElDescriptionsItem>
        <ElDescriptionsItem label="延迟">{{ currentLog.latency_ms }}ms</ElDescriptionsItem>
        <ElDescriptionsItem label="状态">
          <ElTag :type="currentLog.status === 'success' ? 'success' : 'danger'">
            {{ currentLog.status === 'success' ? '成功' : '失败' }}
          </ElTag>
        </ElDescriptionsItem>
        <ElDescriptionsItem label="时间" :span="2">
          {{ new Date(currentLog.created_at).toLocaleString() }}
        </ElDescriptionsItem>
        <ElDescriptionsItem v-if="currentLog.error_message" label="错误信息" :span="2">
          <span class="error-text">{{ currentLog.error_message }}</span>
        </ElDescriptionsItem>
      </ElDescriptions>
    </ElDialog>
  </div>
</template>

<style scoped>
.logs-view {
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

.filter-card {
  margin-bottom: 20px;
}

.filter-form {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.id-text {
  font-family: monospace;
  color: #606266;
}

.pagination {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}

.error-text {
  color: #f56c6c;
}
</style>
