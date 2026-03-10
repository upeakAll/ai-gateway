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
  ElMessage,
  ElMessageBox,
  ElTabs,
  ElTabPane,
  ElDescriptions,
  ElDescriptionsItem,
  ElSwitch
} from 'element-plus'
import { Plus, Edit, Delete, VideoPlay, RefreshRight } from '@element-plus/icons-vue'
import { channelsApi } from '@/api/channels'
import type { Channel, CreateChannelRequest, ModelConfig, ChannelTestResult } from '@/api/types'

const loading = ref(false)
const channels = ref<Channel[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(10)

const dialogVisible = ref(false)
const dialogTitle = ref('创建渠道')
const formLoading = ref(false)
const formRef = ref()
const formData = ref<CreateChannelRequest>({
  provider: '',
  name: '',
  api_key: '',
  api_base: '',
  weight: 100,
  priority: 1
})

const currentChannel = ref<Channel | null>(null)
const modelDialogVisible = ref(false)
const models = ref<ModelConfig[]>([])
const modelFormRef = ref()
const modelFormData = ref({
  model_name: '',
  real_model_name: '',
  input_price_per_1k: 0.01,
  output_price_per_1k: 0.03,
  max_tokens: 4096
})

const providers = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'azure', label: 'Azure OpenAI' },
  { value: 'bedrock', label: 'AWS Bedrock' },
  { value: 'aliyun', label: '阿里云通义' },
  { value: 'baidu', label: '百度文心' },
  { value: 'zhipu', label: '智谱AI' },
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'ollama', label: 'Ollama' }
]

const rules = {
  provider: [{ required: true, message: '请选择提供商', trigger: 'change' }],
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
  api_key: [{ required: true, message: '请输入API Key', trigger: 'blur' }]
}

async function fetchData() {
  loading.value = true
  try {
    const response = await channelsApi.list({ page: page.value, page_size: pageSize.value })
    channels.value = response.items
    total.value = response.total
  } finally {
    loading.value = false
  }
}

function handleCreate() {
  dialogTitle.value = '创建渠道'
  formData.value = {
    provider: '',
    name: '',
    api_key: '',
    api_base: '',
    weight: 100,
    priority: 1
  }
  dialogVisible.value = true
}

async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  formLoading.value = true
  try {
    await channelsApi.create(formData.value)
    ElMessage.success('创建成功')
    dialogVisible.value = false
    fetchData()
  } finally {
    formLoading.value = false
  }
}

async function handleDelete(channel: Channel) {
  await ElMessageBox.confirm(`确定要删除渠道 "${channel.name}" 吗？`, '确认删除', {
    type: 'warning'
  })
  await channelsApi.delete(channel.id)
  ElMessage.success('删除成功')
  fetchData()
}

async function handleTest(channel: Channel) {
  ElMessage.info('正在测试渠道...')
  try {
    const result: ChannelTestResult = await channelsApi.test(channel.id)
    if (result.success) {
      ElMessage.success(`测试成功，延迟: ${result.latency_ms}ms`)
    } else {
      ElMessage.error(`测试失败: ${result.error}`)
    }
  } catch {
    // Error handled by interceptor
  }
}

async function handleResetCircuitBreaker(channel: Channel) {
  await channelsApi.resetCircuitBreaker(channel.id)
  ElMessage.success('熔断器已重置')
  fetchData()
}

async function openModelDialog(channel: Channel) {
  currentChannel.value = channel
  try {
    models.value = await channelsApi.listModelConfigs(channel.id)
  } catch {
    models.value = []
  }
  modelDialogVisible.value = true
}

async function handleCreateModel() {
  if (!currentChannel.value) return
  try {
    await channelsApi.createModelConfig(currentChannel.value.id, modelFormData.value)
    ElMessage.success('模型配置创建成功')
    models.value = await channelsApi.listModelConfigs(currentChannel.value.id)
    modelFormData.value = {
      model_name: '',
      real_model_name: '',
      input_price_per_1k: 0.01,
      output_price_per_1k: 0.03,
      max_tokens: 4096
    }
  } catch {
    // Error handled
  }
}

async function handleDeleteModel(modelId: string) {
  if (!currentChannel.value) return
  await ElMessageBox.confirm('确定要删除此模型配置吗？', '确认删除', { type: 'warning' })
  await channelsApi.deleteModelConfig(currentChannel.value.id, modelId)
  ElMessage.success('删除成功')
  models.value = await channelsApi.listModelConfigs(currentChannel.value.id)
}

function getHealthTagType(status: string) {
  switch (status) {
    case 'healthy':
      return 'success'
    case 'degraded':
      return 'warning'
    case 'unhealthy':
      return 'danger'
    default:
      return 'info'
  }
}

function getCircuitBreakerTagType(state: string) {
  switch (state) {
    case 'closed':
      return 'success'
    case 'open':
      return 'danger'
    case 'half_open':
      return 'warning'
    default:
      return 'info'
  }
}

function handlePageChange(val: number) {
  page.value = val
  fetchData()
}

onMounted(() => {
  fetchData()
})
</script>

<template>
  <div class="channels-view">
    <div class="page-header">
      <h2>渠道管理</h2>
      <ElButton type="primary" :icon="Plus" @click="handleCreate">创建渠道</ElButton>
    </div>

    <ElCard shadow="never">
      <ElTable :data="channels" v-loading="loading" stripe>
        <ElTableColumn prop="name" label="名称" min-width="120" />
        <ElTableColumn prop="provider" label="提供商" width="120">
          <template #default="{ row }">
            <ElTag>{{ row.provider }}</ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn prop="weight" label="权重" width="80" />
        <ElTableColumn prop="priority" label="优先级" width="80" />
        <ElTableColumn label="健康状态" width="100">
          <template #default="{ row }">
            <ElTag :type="getHealthTagType(row.health_status)">
              {{ row.health_status }}
            </ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn label="熔断器" width="100">
          <template #default="{ row }">
            <ElTag :type="getCircuitBreakerTagType(row.circuit_breaker_state)">
              {{ row.circuit_breaker_state }}
            </ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn prop="avg_response_time" label="平均延迟(ms)" width="110" />
        <ElTableColumn label="成功率" width="100">
          <template #default="{ row }">
            {{ row.total_requests > 0
              ? ((row.success_requests / row.total_requests) * 100).toFixed(1) + '%'
              : '-' }}
          </template>
        </ElTableColumn>
        <ElTableColumn label="状态" width="80">
          <template #default="{ row }">
            <ElTag :type="row.is_active ? 'success' : 'danger'">
              {{ row.is_active ? '启用' : '禁用' }}
            </ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn label="操作" width="280" fixed="right">
          <template #default="{ row }">
            <ElButton link type="primary" @click="openModelDialog(row)">模型</ElButton>
            <ElButton link type="primary" :icon="VideoPlay" @click="handleTest(row)">测试</ElButton>
            <ElButton
              v-if="row.circuit_breaker_state === 'open'"
              link
              type="warning"
              :icon="RefreshRight"
              @click="handleResetCircuitBreaker(row)"
            >
              重置
            </ElButton>
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

    <!-- Create Dialog -->
    <ElDialog v-model="dialogVisible" :title="dialogTitle" width="500px">
      <ElForm ref="formRef" :model="formData" :rules="rules" label-width="100px">
        <ElFormItem label="提供商" prop="provider">
          <ElSelect v-model="formData.provider" placeholder="请选择提供商" style="width: 100%">
            <ElOption
              v-for="provider in providers"
              :key="provider.value"
              :label="provider.label"
              :value="provider.value"
            />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="名称" prop="name">
          <ElInput v-model="formData.name" placeholder="请输入渠道名称" />
        </ElFormItem>
        <ElFormItem label="API Key" prop="api_key">
          <ElInput v-model="formData.api_key" type="password" show-password placeholder="请输入API Key" />
        </ElFormItem>
        <ElFormItem label="API Base">
          <ElInput v-model="formData.api_base" placeholder="可选，自定义API端点" />
        </ElFormItem>
        <ElFormItem label="权重">
          <ElInputNumber v-model="formData.weight" :min="1" :max="1000" style="width: 100%" />
        </ElFormItem>
        <ElFormItem label="优先级">
          <ElInputNumber v-model="formData.priority" :min="1" :max="100" style="width: 100%" />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="dialogVisible = false">取消</ElButton>
        <ElButton type="primary" :loading="formLoading" @click="handleSubmit">确定</ElButton>
      </template>
    </ElDialog>

    <!-- Model Config Dialog -->
    <ElDialog v-model="modelDialogVisible" title="模型配置" width="800px">
      <ElTabs>
        <ElTabPane label="已配置模型">
          <ElTable :data="models" stripe>
            <ElTableColumn prop="model_name" label="模型名称" />
            <ElTableColumn prop="real_model_name" label="实际模型" />
            <ElTableColumn label="输入价格($/1K)">
              <template #default="{ row }">
                ${{ row.input_price_per_1k }}
              </template>
            </ElTableColumn>
            <ElTableColumn label="输出价格($/1K)">
              <template #default="{ row }">
                ${{ row.output_price_per_1k }}
              </template>
            </ElTableColumn>
            <ElTableColumn prop="max_tokens" label="最大Token" />
            <ElTableColumn label="操作" width="100">
              <template #default="{ row }">
                <ElButton link type="danger" @click="handleDeleteModel(row.id)">删除</ElButton>
              </template>
            </ElTableColumn>
          </ElTable>
        </ElTabPane>
        <ElTabPane label="添加模型">
          <ElForm ref="modelFormRef" :model="modelFormData" label-width="120px">
            <ElFormItem label="模型名称" required>
              <ElInput v-model="modelFormData.model_name" placeholder="如 gpt-4o" />
            </ElFormItem>
            <ElFormItem label="实际模型名">
              <ElInput v-model="modelFormData.real_model_name" placeholder="留空则同模型名称" />
            </ElFormItem>
            <ElFormItem label="输入价格">
              <ElInputNumber
                v-model="modelFormData.input_price_per_1k"
                :min="0"
                :precision="4"
                style="width: 100%"
              />
            </ElFormItem>
            <ElFormItem label="输出价格">
              <ElInputNumber
                v-model="modelFormData.output_price_per_1k"
                :min="0"
                :precision="4"
                style="width: 100%"
              />
            </ElFormItem>
            <ElFormItem label="最大Token">
              <ElInputNumber v-model="modelFormData.max_tokens" :min="1" style="width: 100%" />
            </ElFormItem>
            <ElFormItem>
              <ElButton type="primary" @click="handleCreateModel">添加模型</ElButton>
            </ElFormItem>
          </ElForm>
        </ElTabPane>
      </ElTabs>
    </ElDialog>
  </div>
</template>

<style scoped>
.channels-view {
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

.pagination {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}
</style>
