import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

// ===== 大V管理 =====

export function getVStars() {
  return api.get('/vstars/')
}

export function createVStar(data) {
  return api.post('/vstars/', data)
}

export function updateVStar(id, data) {
  return api.put(`/vstars/${id}`, data)
}

export function deleteVStar(id) {
  return api.delete(`/vstars/${id}`)
}

export function getPlatforms() {
  return api.get('/vstars/platforms')
}

export function refreshVStar(id) {
  return api.post(`/vstars/${id}/refresh`)
}

export function getVStarArticles(id) {
  return api.get(`/vstars/${id}/articles`)
}

// ===== 分析任务 =====

export function startAnalysis(timeWindow, minMentionCount) {
  return api.post('/analysis/start', {
    time_window: timeWindow,
    min_mention_count: minMentionCount,
  })
}

export function getTaskStatus(taskId) {
  return api.get(`/analysis/task/${taskId}`)
}

export function getAnalysisResults(taskId) {
  return api.get(`/analysis/results/${taskId}`)
}

export function getStockDetail(taskId, stockCode) {
  return api.get(`/analysis/stock-detail/${taskId}/${stockCode}`)
}

// ===== 股票数据 =====

export function getKLineData(stockCode, period, taskId) {
  const params = { period, task_id: taskId }
  return api.get(`/stocks/kline/${stockCode}`, { params })
}

export function searchStocks(q) {
  return api.get('/stocks/search', { params: { q } })
}

// ===== 凭据管理 =====

export function getCredentials() {
  return api.get('/credentials/')
}

export function loginPlatform(platform) {
  return api.post(`/credentials/${platform}/login`)
}

export function loginPlatformVisible(platform) {
  return api.post(`/credentials/${platform}/login-visible`)
}

export default api
