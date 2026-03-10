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
  ElSelect,
  ElMessage,
  ElMessageBox,
  ElDescriptions,
  ElDescriptionsItem,
  ElTabs,
  ElTabPane,
  ElSwitch
} from 'element-plus'
import { Plus, Delete, Refresh, Link, Tools } from '@element-plus/icons-vue'
import { mcpApi } from '@/api/mcp'
import { tenantsApi } from '@/api/tenants'
import type { MCPServer, MCPTool, CreateMCPServerRequest, Tenant } from '@/api/types'

const loading = ref(false)
const servers = ref<MCPServer[]>([])
const tenants = ref<Tenant[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(10)

const dialogVisible = ref(false)
const formLoading = ref(false)
const formRef = ref()
const formData = ref<CreateMCPServerRequest>({
  tenant_id: '',
  name: '',
  description: '',
  config_type: 'openapi',
  openapi_url: '',
  transport: 'sse'
})

const toolsDialogVisible = ref(false)
const currentServer = ref<MCPServer | null>(null)
const tools = ref<MCPTool[]>([])

const rules = {
  tenant_id: [{ required: true, message: '请选择租户', trigger: 'change' }],
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
  config_type: [{ required: true, message: '请选择配置类型', trigger: 'change' }]
}

async function fetchData() {
  loading.value = true
  try {
    const response = await mcpApi.listServers({ page: page.value, page_size: pageSize.value })
    servers.value = response.items
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
  formData.value = {
    tenant_id: '',
    name: '',
    description: '',
    config_type: 'openapi',
    openapi_url: '',
    transport: 'sse'
  }
  dialogVisible.value = true
}

async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  formLoading.value = true
  try {
    await mcpApi.createServer(formData.value)
    ElMessage.success('创建成功')
    dialogVisible.value = false
    fetchData()
  } finally {
    formLoading.value = false
  }
}

async function handleDelete(server: MCPServer) {
  await ElMessageBox.confirm(`确定要删除MCP服务器 "${server.name}" 吗？`, '确认删除', {
    type: 'warning'
  })
  await mcpApi.deleteServer(server.id)
  ElMessage.success('删除成功')
  fetchData()
}

async function handleGenerateFromOpenApi(server: MCPServer) {
  if (!server.openapi_url) {
    ElMessage.warning('请先配置OpenAPI URL')
    return
  }
  try {
    ElMessage.info('正在从OpenAPI生成工具...')
    const generatedTools = await mcpApi.generateFromOpenApi(server.id)
    ElMessage.success(`成功生成 ${generatedTools.length} 个工具`)
  } catch {
    // Error handled
  }
}

async function viewTools(server: MCPServer) {
  currentServer.value = server
  try {
    tools.value = await mcpApi.listTools(server.id)
  } catch {
    tools.value = []
  }
  toolsDialogVisible.value = true
}

async function handleUpdateToolRoles(tool: MCPTool, roles: string[]) {
  if (!currentServer.value) return
  try {
    await mcpApi.updateTool(currentServer.value.id, tool.id, { allowed_roles: roles })
    ElMessage.success('权限更新成功')
  } catch {
    // Error handled
  }
}

function getStatusTagType(status: string) {
  switch (status) {
    case 'active':
      return 'success'
    case 'inactive':
      return 'info'
    case 'error':
      return 'danger'
    default:
      return 'info'
  }
}

function getSSEUrl(server: MCPServer) {
  return `/mcp/${server.id}/sse`
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
  <div class="mcp-view">
    <div class="page-header">
      <h2>MCP管理</h2>
      <ElButton type="primary" :icon="Plus" @click="handleCreate">创建服务器</ElButton>
    </div>

    <ElCard shadow="never">
      <ElTable :data="servers" v-loading="loading" stripe>
        <ElTableColumn prop="name" label="名称" min-width="120" />
        <ElTableColumn prop="description" label="描述" min-width="150">
          <template #default="{ row }">
            {{ row.description || '-' }}
          </template>
        </ElTableColumn>
        <ElTableColumn prop="config_type" label="配置类型" width="100">
          <template #default="{ row }">
            <ElTag>{{ row.config_type === 'openapi' ? 'OpenAPI' : '自定义' }}</ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn prop="transport" label="传输方式" width="100">
          <template #default="{ row }">
            <ElTag type="info">{{ row.transport.toUpperCase() }}</ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn label="状态" width="100">
          <template #default="{ row }">
            <ElTag :type="getStatusTagType(row.status)">
              {{ row.status }}
            </ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn label="SSE端点" min-width="200">
          <template #default="{ row }">
            <code class="sse-url">{{ getSSEUrl(row) }}</code>
          </template>
        </ElTableColumn>
        <ElTableColumn label="创建时间" width="180">
          <template #default="{ row }">
            {{ new Date(row.created_at).toLocaleString() }}
          </template>
        </ElTableColumn>
        <ElTableColumn label="操作" width="280" fixed="right">
          <template #default="{ row }">
            <ElButton link type="primary" :icon="Tools" @click="viewTools(row)">工具</ElButton>
            <ElButton
              v-if="row.config_type === 'openapi'"
              link
              type="primary"
              :icon="Refresh"
              @click="handleGenerateFromOpenApi(row)"
            >
              生成
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
    <ElDialog v-model="dialogVisible" title="创建MCP服务器" width="600px">
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
          <ElInput v-model="formData.name" placeholder="请输入服务器名称" />
        </ElFormItem>
        <ElFormItem label="描述">
          <ElInput v-model="formData.description" type="textarea" :rows="2" placeholder="可选描述" />
        </ElFormItem>
        <ElFormItem label="配置类型" prop="config_type">
          <ElSelect v-model="formData.config_type" style="width: 100%">
            <ElOption label="OpenAPI" value="openapi" />
            <ElOption label="自定义" value="custom" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem v-if="formData.config_type === 'openapi'" label="OpenAPI URL">
          <ElInput v-model="formData.openapi_url" placeholder="OpenAPI规范URL">
            <template #prefix>
              <ElIcon><Link /></ElIcon>
            </template>
          </ElInput>
        </ElFormItem>
        <ElFormItem label="传输方式">
          <ElSelect v-model="formData.transport" style="width: 100%">
            <ElOption label="SSE" value="sse" />
            <ElOption label="HTTP" value="http" />
          </ElSelect>
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="dialogVisible = false">取消</ElButton>
        <ElButton type="primary" :loading="formLoading" @click="handleSubmit">确定</ElButton>
      </template>
    </ElDialog>

    <!-- Tools Dialog -->
    <ElDialog v-model="toolsDialogVisible" :title="`工具列表 - ${currentServer?.name}`" width="800px">
      <ElTable :data="tools" stripe>
        <ElTableColumn prop="name" label="工具名称" min-width="120" />
        <ElTableColumn prop="description" label="描述" min-width="200" />
        <ElTableColumn prop="required_permission" label="所需权限" width="120">
          <template #default="{ row }">
            <ElTag v-if="row.required_permission" size="small">{{ row.required_permission }}</ElTag>
            <span v-else>-</span>
          </template>
        </ElTableColumn>
        <ElTableColumn label="允许角色" min-width="200">
          <template #default="{ row }">
            <ElSelect
              :model-value="row.allowed_roles"
              multiple
              placeholder="选择角色"
              size="small"
              @change="(val: string[]) => handleUpdateToolRoles(row, val)"
            >
              <ElOption label="管理员" value="admin" />
              <ElOption label="开发者" value="developer" />
              <ElOption label="用户" value="user" />
            </ElSelect>
          </template>
        </ElTableColumn>
      </ElTable>
      <div v-if="tools.length === 0" class="empty-state">
        <p>暂无工具，请通过OpenAPI生成或手动添加</p>
      </div>
    </ElDialog>
  </div>
</template>

<style scoped>
.mcp-view {
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

.sse-url {
  font-family: monospace;
  font-size: 12px;
  background-color: #f5f5f5;
  padding: 2px 6px;
  border-radius: 4px;
}

.pagination {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}

.empty-state {
  padding: 40px;
  text-align: center;
  color: #909399;
}
</style>
