<template>
  <div class="dashboard">
    <!-- 分析配置面板 -->
    <el-card class="config-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <span><el-icon><DataAnalysis /></el-icon> 分析配置</span>
        </div>
      </template>
      <div class="config-body">
        <div class="config-item">
          <label>时间窗口</label>
          <el-radio-group v-model="timeWindow" size="large" :disabled="store.isAnalyzing">
            <el-radio-button value="3d">最近 3 天</el-radio-button>
            <el-radio-button value="1w">最近 1 周</el-radio-button>
            <el-radio-button value="1m">最近 1 个月</el-radio-button>
          </el-radio-group>
        </div>
        <div class="config-item">
          <label>最低提及人数</label>
          <el-input-number v-model="minCount" :min="2" :max="20" :disabled="store.isAnalyzing" size="large" />
          <span class="hint">只有同时被至少 N 位大V提及的股票才进入榜单</span>
        </div>
        <div class="config-action">
          <el-button
            type="primary"
            size="large"
            :loading="store.isAnalyzing"
            @click="startAnalysis"
            :disabled="store.isAnalyzing"
          >
            <el-icon><VideoPlay /></el-icon>
            {{ store.isAnalyzing ? '分析中...' : '开始分析' }}
          </el-button>
          <el-button v-if="store.analysisResults.length > 0" size="large" @click="store.reset()">
            清除结果
          </el-button>
        </div>
      </div>

      <!-- 进度条 -->
      <div v-if="store.isAnalyzing" class="progress-section">
        <el-progress :percentage="store.taskProgress" :status="store.taskStatus === 'failed' ? 'exception' : undefined" />
        <p class="progress-text">
          {{ store.taskStatus === 'pending' ? '任务排队中...' : `分析中 ${store.taskProgress}%` }}
        </p>
      </div>
      <div v-if="store.taskStatus === 'failed'" class="error-section">
        <el-alert :title="'分析失败: ' + store.taskError" type="error" show-icon :closable="false" />
      </div>
    </el-card>

    <!-- 结果摘要 -->
    <div v-if="store.resultSummary" class="result-summary">
      <el-tag type="success" size="large">
        分析完成：共分析 {{ store.resultSummary.analyzed_articles }} 篇文章，
        发现 {{ store.resultSummary.total_results }} 只满足阈值的股票
      </el-tag>
    </div>

    <!-- 榜单表格 -->
    <el-card v-if="store.analysisResults.length > 0" class="result-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <span><el-icon><Trophy /></el-icon> 大V舆情榜单（仅展示正向提及）</span>
          <span class="card-hint">按热度降序 | 点击行查看证据链</span>
        </div>
      </template>

      <el-table
        :data="store.analysisResults"
        stripe
        highlight-current-row
        @row-click="showDetail"
        style="width: 100%; cursor: pointer;"
        :default-sort="{ prop: 'hotness_score', order: 'descending' }"
      >
        <el-table-column prop="stock_name" label="股票名称" width="140">
          <template #default="{ row }">
            <span class="stock-name">{{ row.stock_name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="stock_code" label="代码" width="100" />
        <el-table-column prop="hotness_score" label="热度值" width="100" sortable>
          <template #default="{ row }">
            <el-tag :type="row.hotness_score > 5 ? 'danger' : 'warning'" effect="dark">
              {{ row.hotness_score.toFixed(1) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="mention_count" label="提及人数" width="100" sortable />
        <el-table-column label="看多/看空" width="130">
          <template #default="{ row }">
            <span class="sentiment-ratio">
              <span class="positive">{{ row.positive_count }}👍</span>
              <span class="divider">/</span>
              <span class="negative">{{ row.negative_count }}👎</span>
            </span>
          </template>
        </el-table-column>
        <el-table-column label="提及大V" min-width="250">
          <template #default="{ row }">
            <el-tag
              v-for="name in row.vstar_list"
              :key="name"
              size="small"
              style="margin: 2px;"
            >{{ name }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link @click.stop="showDetail(row)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 空状态提示 -->
    <el-empty
      v-if="!store.isAnalyzing && store.analysisResults.length === 0 && store.taskStatus !== 'failed'"
      description="点击「开始分析」发现大V共同看多的股票"
    />

    <!-- 个股详情弹窗 -->
    <el-dialog
      v-model="detailVisible"
      :title="`${detailStock.stock_name || ''} (${detailStock.stock_code || ''}) - 证据链`"
      width="90%"
      top="5vh"
      destroy-on-close
    >
      <StockDetail
        v-if="detailVisible"
        :task-id="store.taskId"
        :stock-code="detailStock.stock_code"
        :stock-name="detailStock.stock_name"
      />
    </el-dialog>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useAppStore } from '../store'
import { startAnalysis as apiStartAnalysis, getTaskStatus, getAnalysisResults } from '../api'
import StockDetail from '../components/StockDetail.vue'

const store = useAppStore()

const timeWindow = ref(store.timeWindow)
const minCount = ref(store.minMentionCount)
const detailVisible = ref(false)
const detailStock = ref({})

let pollingTimer = null

function startAnalysis() {
  store.setAnalysisConfig(timeWindow.value, minCount.value)

  apiStartAnalysis(timeWindow.value, minCount.value)
    .then(res => {
      store.setTaskId(res.data.task_id)
      ElMessage.success('分析任务已启动')
      startPolling()
    })
    .catch(err => {
      ElMessage.error('启动分析失败: ' + (err.response?.data?.detail || err.message))
    })
}

function startPolling() {
  if (pollingTimer) clearInterval(pollingTimer)

  pollingTimer = setInterval(() => {
    if (!store.taskId) {
      clearInterval(pollingTimer)
      return
    }

    getTaskStatus(store.taskId)
      .then(res => {
        store.updateTaskStatus(res.data)

        if (res.data.status === 'completed') {
          clearInterval(pollingTimer)
          loadResults()
        } else if (res.data.status === 'failed') {
          clearInterval(pollingTimer)
          ElMessage.error('分析失败: ' + (res.data.error_message || '未知错误'))
        }
      })
      .catch(() => {})
  }, 2000) // 每2秒轮询一次
}

function loadResults() {
  if (!store.taskId) return

  getAnalysisResults(store.taskId)
    .then(res => {
      store.setResults(res.data)
      ElMessage.success(`分析完成！共发现 ${res.data.length} 只满足阈值的股票`)
    })
    .catch(err => {
      ElMessage.error('获取结果失败: ' + err.message)
    })
}

function showDetail(row) {
  detailStock.value = row
  detailVisible.value = true
}
</script>

<style scoped>
.dashboard {
  max-width: 1400px;
  margin: 0 auto;
}

.config-card {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 16px;
  font-weight: 600;
}

.card-header span {
  display: flex;
  align-items: center;
  gap: 6px;
}

.card-hint {
  font-size: 13px;
  color: #909399;
  font-weight: normal;
}

.config-body {
  display: flex;
  align-items: center;
  gap: 32px;
  flex-wrap: wrap;
}

.config-item {
  display: flex;
  align-items: center;
  gap: 10px;
}

.config-item label {
  font-weight: 600;
  color: #606266;
  white-space: nowrap;
}

.hint {
  color: #909399;
  font-size: 13px;
  margin-left: 8px;
}

.config-action {
  margin-left: auto;
}

.progress-section {
  margin-top: 20px;
}

.progress-text {
  text-align: center;
  color: #409EFF;
  margin-top: 8px;
  font-size: 14px;
}

.error-section {
  margin-top: 16px;
}

.result-summary {
  margin-bottom: 16px;
}

.result-card {
  margin-bottom: 20px;
}

.stock-name {
  font-weight: 700;
  color: #303133;
}

.sentiment-ratio {
  font-size: 14px;
}

.positive { color: #67c23a; font-weight: 600; }
.negative { color: #f56c6c; font-weight: 600; }
.divider { margin: 0 4px; color: #c0c4cc; }
</style>
