<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import {
  ElRow,
  ElCol,
  ElCard,
  ElStatistic,
  ElProgress,
  ElTable,
  ElTableColumn,
  ElTag,
  ElSkeleton
} from 'element-plus'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, PieChart } from 'echarts/charts'
import {
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent
} from 'echarts/components'
import VChart from 'vue-echarts'
import { usageApi } from '@/api/usage'
import { healthApi } from '@/api/health'
import type { UsageStatistics } from '@/api/types'

use([
  CanvasRenderer,
  LineChart,
  PieChart,
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent
])

const loading = ref(true)
const statistics = ref<UsageStatistics | null>(null)
const systemHealthy = ref(true)

async function fetchData() {
  loading.value = true
  try {
    const [statsResponse, healthResponse] = await Promise.all([
      usageApi.getStatistics({ group_by: 'date' }),
      healthApi.check()
    ])
    statistics.value = statsResponse
    systemHealthy.value = healthResponse.status === 'healthy'
  } catch {
    // Error handled
  } finally {
    loading.value = false
  }
}

const chartOption = computed(() => {
  if (!statistics.value) return {}

  const dates = statistics.value.by_date.map((d) => d.date)
  const requests = statistics.value.by_date.map((d) => d.requests)
  const costs = statistics.value.by_date.map((d) => d.cost)

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' }
    },
    legend: {
      data: ['请求数', '成本(USD)']
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: dates
    },
    yAxis: [
      {
        type: 'value',
        name: '请求数',
        position: 'left'
      },
      {
        type: 'value',
        name: '成本',
        position: 'right'
      }
    ],
    series: [
      {
        name: '请求数',
        type: 'line',
        smooth: true,
        data: requests
      },
      {
        name: '成本(USD)',
        type: 'line',
        smooth: true,
        yAxisIndex: 1,
        data: costs
      }
    ]
  }
})

const pieOption = computed(() => {
  if (!statistics.value) return {}

  const data = statistics.value.by_model.map((m) => ({
    name: m.model_name,
    value: m.cost
  }))

  return {
    tooltip: {
      trigger: 'item',
      formatter: '{b}: ${c} ({d}%)'
    },
    legend: {
      orient: 'vertical',
      left: 'left'
    },
    series: [
      {
        name: '成本分布',
        type: 'pie',
        radius: ['40%', '70%'],
        avoidLabelOverlap: false,
        itemStyle: {
          borderRadius: 10,
          borderColor: '#fff',
          borderWidth: 2
        },
        label: {
          show: false,
          position: 'center'
        },
        emphasis: {
          label: {
            show: true,
            fontSize: 20,
            fontWeight: 'bold'
          }
        },
        labelLine: {
          show: false
        },
        data
      }
    ]
  }
})

onMounted(() => {
  fetchData()
})
</script>

<template>
  <div class="dashboard">
    <h2 class="page-title">仪表盘</h2>

    <ElSkeleton :loading="loading" animated :rows="5">
      <template #default>
        <!-- Statistics Cards -->
        <ElRow :gutter="20" class="stat-cards">
          <ElCol :xs="24" :sm="12" :md="6">
            <ElCard shadow="hover">
              <ElStatistic title="总请求数" :value="statistics?.total_requests || 0">
                <template #suffix>
                  <span class="stat-suffix">次</span>
                </template>
              </ElStatistic>
            </ElCard>
          </ElCol>
          <ElCol :xs="24" :sm="12" :md="6">
            <ElCard shadow="hover">
              <ElStatistic title="总Token数" :value="statistics?.total_tokens || 0">
                <template #suffix>
                  <span class="stat-suffix">tokens</span>
                </template>
              </ElStatistic>
            </ElCard>
          </ElCol>
          <ElCol :xs="24" :sm="12" :md="6">
            <ElCard shadow="hover">
              <ElStatistic title="总成本" :value="statistics?.total_cost || 0" :precision="2">
                <template #prefix>
                  <span class="stat-prefix">$</span>
                </template>
              </ElStatistic>
            </ElCard>
          </ElCol>
          <ElCol :xs="24" :sm="12" :md="6">
            <ElCard shadow="hover">
              <ElStatistic title="平均延迟" :value="statistics?.avg_latency_ms || 0">
                <template #suffix>
                  <span class="stat-suffix">ms</span>
                </template>
              </ElStatistic>
            </ElCard>
          </ElCol>
        </ElRow>

        <!-- System Status -->
        <ElRow :gutter="20" class="status-section">
          <ElCol :span="24">
            <ElCard shadow="hover">
              <template #header>
                <div class="card-header">
                  <span>系统状态</span>
                  <ElTag :type="systemHealthy ? 'success' : 'danger'">
                    {{ systemHealthy ? '正常' : '异常' }}
                  </ElTag>
                </div>
              </template>
              <ElRow :gutter="20">
                <ElCol :span="8">
                  <div class="status-item">
                    <span class="status-label">成功率</span>
                    <ElProgress
                      :percentage="(statistics?.success_rate || 0) * 100"
                      :color="(statistics?.success_rate || 0) > 0.99 ? '#67c23a' : '#e6a23c'"
                    />
                  </div>
                </ElCol>
                <ElCol :span="8">
                  <div class="status-item">
                    <span class="status-label">API服务</span>
                    <ElTag :type="systemHealthy ? 'success' : 'danger'">
                      {{ systemHealthy ? '运行中' : '异常' }}
                    </ElTag>
                  </div>
                </ElCol>
                <ElCol :span="8">
                  <div class="status-item">
                    <span class="status-label">数据库</span>
                    <ElTag :type="systemHealthy ? 'success' : 'danger'">
                      {{ systemHealthy ? '已连接' : '断开' }}
                    </ElTag>
                  </div>
                </ElCol>
              </ElRow>
            </ElCard>
          </ElCol>
        </ElRow>

        <!-- Charts -->
        <ElRow :gutter="20" class="chart-section">
          <ElCol :xs="24" :lg="16">
            <ElCard shadow="hover">
              <template #header>
                <span>请求趋势</span>
              </template>
              <v-chart v-if="statistics" :option="chartOption" autoresize style="height: 300px" />
              <div v-else class="empty-chart">暂无数据</div>
            </ElCard>
          </ElCol>
          <ElCol :xs="24" :lg="8">
            <ElCard shadow="hover">
              <template #header>
                <span>模型成本分布</span>
              </template>
              <v-chart v-if="statistics" :option="pieOption" autoresize style="height: 300px" />
              <div v-else class="empty-chart">暂无数据</div>
            </ElCard>
          </ElCol>
        </ElRow>

        <!-- Top Models -->
        <ElRow :gutter="20">
          <ElCol :span="24">
            <ElCard shadow="hover">
              <template #header>
                <span>模型使用排行</span>
              </template>
              <ElTable :data="statistics?.by_model || []" stripe>
                <ElTableColumn prop="model_name" label="模型名称" />
                <ElTableColumn prop="requests" label="请求数" sortable />
                <ElTableColumn prop="tokens" label="Token数" sortable />
                <ElTableColumn prop="cost" label="成本(USD)" sortable>
                  <template #default="{ row }">
                    ${{ row.cost.toFixed(4) }}
                  </template>
                </ElTableColumn>
              </ElTable>
            </ElCard>
          </ElCol>
        </ElRow>
      </template>
    </ElSkeleton>
  </div>
</template>

<style scoped>
.dashboard {
  max-width: 1400px;
}

.page-title {
  margin-bottom: 20px;
  color: #303133;
}

.stat-cards {
  margin-bottom: 20px;
}

.stat-cards .el-card {
  margin-bottom: 10px;
}

.stat-prefix,
.stat-suffix {
  font-size: 14px;
  color: #909399;
}

.status-section {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.status-item {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.status-label {
  color: #606266;
  font-size: 14px;
}

.chart-section {
  margin-bottom: 20px;
}

.chart-section .el-card {
  margin-bottom: 10px;
}

.empty-chart {
  height: 300px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #909399;
}
</style>
