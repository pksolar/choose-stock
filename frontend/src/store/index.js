import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useAppStore = defineStore('app', () => {
  // 分析任务状态
  const taskId = ref(null)
  const taskStatus = ref('idle') // idle | pending | running | completed | failed
  const taskProgress = ref(0)
  const taskError = ref('')
  const analysisResults = ref([])
  const resultSummary = ref(null)

  // 分析配置
  const timeWindow = ref('1w')
  const minMentionCount = ref(3)

  // 轮询定时器
  const pollingInterval = ref(null)

  const isAnalyzing = computed(() =>
    taskStatus.value === 'pending' || taskStatus.value === 'running'
  )

  function setAnalysisConfig(window, count) {
    timeWindow.value = window
    minMentionCount.value = count
  }

  function setTaskId(id) {
    taskId.value = id
    taskStatus.value = 'pending'
    taskProgress.value = 0
    taskError.value = ''
  }

  function updateTaskStatus(status) {
    taskStatus.value = status.status
    taskProgress.value = status.progress || 0
    if (status.error_message) {
      taskError.value = status.error_message
    }
    if (status.result_summary) {
      resultSummary.value = status.result_summary
    }
  }

  function setResults(results) {
    analysisResults.value = results
  }

  function reset() {
    taskId.value = null
    taskStatus.value = 'idle'
    taskProgress.value = 0
    taskError.value = ''
    analysisResults.value = []
    resultSummary.value = null
  }

  return {
    taskId, taskStatus, taskProgress, taskError,
    analysisResults, resultSummary,
    timeWindow, minMentionCount, isAnalyzing,
    setAnalysisConfig, setTaskId, updateTaskStatus,
    setResults, reset,
  }
})
