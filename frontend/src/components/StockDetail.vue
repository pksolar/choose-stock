<template>
  <div class="stock-detail" v-loading="loading">
    <el-row :gutter="20">
      <!-- 左侧：K线图 -->
      <el-col :span="14">
        <div class="kline-section">
          <div class="section-header">
            <h3><el-icon><DataLine /></el-icon> K线图</h3>
            <el-radio-group v-model="klinePeriod" size="small" @change="loadKLine">
              <el-radio-button value="1m">近1月</el-radio-button>
              <el-radio-button value="3m">近3月</el-radio-button>
            </el-radio-group>
          </div>
          <KLineChart
            :data="klineData"
            :mark-date="markLineDate"
            :stock-name="stockName"
            height="400px"
          />
        </div>
        <!-- 统计摘要 -->
        <div class="stats-row" v-if="detail">
          <el-statistic title="热度值" :value="detail.hotness_score" :precision="1" />
          <el-statistic title="提及人数" :value="detail.mention_count" />
          <el-statistic title="看多👍">
            <template #default>
              <span class="stat-positive">{{ detail.positive_count }}</span>
            </template>
          </el-statistic>
          <el-statistic title="看空👎">
            <template #default>
              <span class="stat-negative">{{ detail.negative_count }}</span>
            </template>
          </el-statistic>
        </div>
      </el-col>

      <!-- 右侧：证据链 -->
      <el-col :span="10">
        <div class="evidence-section">
          <div class="section-header">
            <h3><el-icon><Document /></el-icon> 证据链</h3>
            <el-tag size="small" type="info">共 {{ detail?.evidence_chain?.length || 0 }} 条</el-tag>
          </div>
          <EvidenceChain :evidence="detail?.evidence_chain || []" />
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { getStockDetail, getKLineData } from '../api'
import KLineChart from './KLineChart.vue'
import EvidenceChain from './EvidenceChain.vue'

const props = defineProps({
  taskId: { type: String, required: true },
  stockCode: { type: String, required: true },
  stockName: { type: String, default: '' },
})

const loading = ref(false)
const detail = ref(null)
const klinePeriod = ref('1m')
const klineData = ref([])
const markLineDate = ref(null)

function loadDetail() {
  loading.value = true
  getStockDetail(props.taskId, props.stockCode)
    .then(res => {
      detail.value = res.data
    })
    .catch(err => {
      console.error('Failed to load stock detail:', err)
    })
    .finally(() => { loading.value = false })
}

function loadKLine() {
  getKLineData(props.stockCode, klinePeriod.value, props.taskId)
    .then(res => {
      klineData.value = res.data.data || []
      markLineDate.value = res.data.mark_line_date || null
    })
    .catch(err => {
      console.error('Failed to load K-line data:', err)
    })
}

onMounted(() => {
  loadDetail()
  loadKLine()
})
</script>

<style scoped>
.stock-detail {
  min-height: 500px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.section-header h3 {
  font-size: 16px;
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0;
}

.stats-row {
  display: flex;
  gap: 32px;
  margin-top: 20px;
  padding: 16px;
  background-color: #f5f7fa;
  border-radius: 8px;
}

.stat-positive { color: #67c23a; font-weight: 700; }
.stat-negative { color: #f56c6c; font-weight: 700; }

.evidence-section {
  border-left: 1px solid #ebeef5;
  padding-left: 20px;
  max-height: 550px;
  overflow-y: auto;
}
</style>
