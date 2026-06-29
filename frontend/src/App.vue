<template>
  <div id="app-container">
    <el-container>
      <!-- 顶部导航 -->
      <el-header class="app-header">
        <div class="header-left">
          <el-icon :size="28" color="#409EFF"><TrendCharts /></el-icon>
          <span class="app-title">V-Stock Radar</span>
          <span class="app-subtitle">大V舆情聚合器</span>
        </div>
        <div class="header-right">
          <el-button type="primary" size="large" @click="goAnalyze">
            <el-icon><Search /></el-icon> 开始分析
          </el-button>
          <el-button size="large" @click="$router.push('/vstars')">
            <el-icon><Setting /></el-icon> 大V管理
          </el-button>
        </div>
      </el-header>

      <!-- 主内容区 -->
      <el-main>
        <router-view />
      </el-main>

      <!-- 底部免责声明 -->
      <el-footer class="app-footer">
        <div class="disclaimer">
          <el-icon><WarningFilled /></el-icon>
          <strong>免责声明：</strong>本系统仅汇总网络公开言论，所有数据仅供参考，不构成任何投资建议。股票投资有风险，入市需谨慎。系统分析结果基于公开文章的 NLP 自动处理，可能存在误判，请用户自行判断。
        </div>
      </el-footer>
    </el-container>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'

const router = useRouter()

function goAnalyze() {
  router.push('/')
}
</script>

<style>
#app-container {
  min-height: 100vh;
  background-color: #f5f7fa;
}

.app-header {
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  height: 64px !important;
  box-shadow: 0 2px 8px rgba(0,0,0,0.15);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.app-title {
  font-size: 22px;
  font-weight: 700;
  letter-spacing: 1px;
  color: #409EFF;
}

.app-subtitle {
  font-size: 14px;
  color: #909399;
  margin-left: 8px;
}

.header-right {
  display: flex;
  gap: 12px;
}

.app-footer {
  background-color: #fff;
  border-top: 1px solid #ebeef5;
  padding: 16px 24px;
  text-align: center;
}

.disclaimer {
  color: #909399;
  font-size: 13px;
  line-height: 1.6;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

.disclaimer strong {
  color: #e6a23c;
}

.el-main {
  min-height: calc(100vh - 64px - 80px);
  padding: 24px;
}
</style>
