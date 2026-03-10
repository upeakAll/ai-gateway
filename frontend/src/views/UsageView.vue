<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import {
  ElCard,
  ElRow,
  ElCol,
  ElForm,
  ElFormItem,
  ElSelect,
  ElDatePicker,
  ElButton,
  ElStatistic,
  ElTable,
  ElTableColumn,
  ElSkeleton
} from 'element-plus'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, BarChart } from 'echarts/charts'
import {
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent
} from 'echarts/components'
import VChart from 'vue-echarts'
import { usageApi } from '@/api/usage'
import type { UsageStatistics, UsageQuery } from '@/api/types'

use([
  CanvasRenderer,
  LineChart,
  BarChart,
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent
])

const loading = ref(false)
const statistics = ref<UsageStatistics | null>(null)

const queryParams = ref<UsageQuery>({
  group_by: 'date'
})

async function fetchData() {
  loading.value = true
  try {
    const response = await usageApi.getStatistics(queryParams.value)
    statistics.value = response
  } finally {
    loading.value = false
  }
}

const chartOption = computed(() => {
  if (!statistics.value?.by_date) return {}

  const dates = statistics.value.by_date.map((d) => d.date)
  const requests = statistics.value.by_date.map((d) => d.requests)
  const tokens = statistics.value.by_date.map((d) => d.tokens)

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' }
    },
    legend: {
      data: ['请求数', 'Token数']
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
        name: 'Token数',
        position: 'right'
      }
    ],
    series: [
      {
        name: '请求数',
        type: 'bar',
        data: requests
      },
      {
        name: 'Token数',
        type: 'line',
        smooth: true,
        yAxisIndex: 1,
        data: tokens
      }
    ]
  }
})

const modelChartOption = computed(() => {
  if (!statistics.value?.by_model) return {}

  const models = statistics.value.by_model.map((m) => m.model_name)
  const costs = statistics.value.by_model.map((m) => m.cost)

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: '{b}: ${c}'
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: models,
      axisLabel: {
        rotate: 30
      }
    },
    yAxis: {
      type: 'value',
      name: '成本 (USD)'
    },
    series: [
      {
        name: '成本',
        type: 'bar',
        data: costs,
        itemStyle: {
          color: '#409EFF'
        }
      }
    ]
  }
})

function handleDateChange(val: [Date, Date] | null) {
  if (val) {
    queryParams.value.start_date = val[0].toISOString().split('T')[0]
    queryParams.value.end_date = val[1].toISOString().split('T')[0]
  } else {
    queryParams.value.start_date = undefined
    queryParams.value.end_date = undefined
  }
}

function handleSearch() {
  fetchData()
}

onMounted(() => {
  fetchData()
})
</script>

<template>
  <div class="usage-view">
    <div class="page-header">
      <h2>用量统计</h2>
    </div>

    <ElCard shadow="never" class="filter-card">
      <ElForm :inline="true" class="filter-form">
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
        <ElFormItem label="分组方式">
          <ElSelect v-model="queryParams.group_by" style="width: 120px">
            <ElOption label="按日期" value="date" />
            <ElOption label="按模型" value="model" />
            <ElOption label="按渠道" value="channel" />
            <ElOption label="按Key" value="key" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem>
          <ElButton type="primary" @click="handleSearch">查询</ElButton>
        </ElFormItem>
      </ElForm>
    </ElCard>

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
              <ElStatistic title="成功率" :value="(statistics?.success_rate || 0) * 100" :precision="1">
                <template #suffix>
                  <span class="stat-suffix">%</span>
                </template>
              </ElStatistic>
            </ElCard>
          </ElCol>
        </ElRow>

        <!-- Charts -->
        <ElRow :gutter="20" class="chart-section">
          <ElCol :xs="24" :lg="12">
            <ElCard shadow="hover">
              <template #header>
                <span>用量趋势</span>
              </template>
              <v-chart v-if="statistics" :option="chartOption" autoresize style="height: 300px" />
              <div v-else class="empty-chart">暂无数据</div>
            </ElCard>
          </ElCol>
          <ElCol :xs="24" :lg="12">
            <ElCard shadow="hover">
              <template #header>
                <span>模型成本对比</span>
              </template>
              <v-chart v-if="statistics" :option="modelChartOption" autoresize style="height: 300px" />
              <div v-else class="empty-chart">暂无数据</div>
            </ElCard>
          </ElCol>
        </ElRow>

        <!-- Detail Table -->
        <ElCard shadow="hover" class="table-section">
          <template #header>
            <span>详细数据</span>
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
      </template>
    </ElSkeleton>
  </div>
</template>

<style scoped>
.usage-view {
  max-width: 1400px;
}

.page-header {
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

.table-section {
  margin-bottom: 20px;
}
</style>
