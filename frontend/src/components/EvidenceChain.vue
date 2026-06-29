<template>
  <div class="evidence-chain">
    <el-timeline v-if="evidence.length > 0">
      <el-timeline-item
        v-for="(item, index) in evidence"
        :key="index"
        :timestamp="formatTime(item.published_at)"
        placement="top"
        :color="sentimentColor(item.sentiment)"
      >
        <el-card shadow="hover" class="evidence-card">
          <div class="evidence-header">
            <el-avatar :size="32" :style="{ backgroundColor: avatarColor(index) }">
              {{ item.vstar_nickname?.charAt(0) || '?' }}
            </el-avatar>
            <div class="evidence-meta">
              <span class="vstar-name">{{ item.vstar_nickname }}</span>
              <el-tag size="small" type="info">{{ item.vstar_platform }}</el-tag>
            </div>
            <el-tag
              :type="sentimentTagType(item.sentiment)"
              effect="dark"
              size="small"
            >
              {{ sentimentLabel(item.sentiment) }}
            </el-tag>
          </div>
          <div class="evidence-title">
            <el-icon><Link /></el-icon>
            <a v-if="item.article_url" :href="item.article_url" target="_blank" class="article-link">
              {{ item.article_title }}
            </a>
            <span v-else>{{ item.article_title }}</span>
          </div>
          <div class="evidence-text">
            <el-icon><ChatLineSquare /></el-icon>
            <span>"...{{ truncateText(item.mentioned_text, 120) }}..."</span>
          </div>
        </el-card>
      </el-timeline-item>
    </el-timeline>

    <el-empty v-else description="暂无证据数据" :image-size="80" />
  </div>
</template>

<script setup>
defineProps({
  evidence: { type: Array, default: () => [] },
})

const avatarColors = ['#409EFF', '#67C23A', '#E6A23C', '#F56C6C', '#909399', '#00D4FF', '#8B5CF6', '#F97316']

function avatarColor(index) {
  return avatarColors[index % avatarColors.length]
}

function sentimentColor(sentiment) {
  if (sentiment === 'positive') return '#67c23a'
  if (sentiment === 'negative') return '#f56c6c'
  return '#e6a23c'
}

function sentimentTagType(sentiment) {
  if (sentiment === 'positive') return 'success'
  if (sentiment === 'negative') return 'danger'
  return 'warning'
}

function sentimentLabel(sentiment) {
  if (sentiment === 'positive') return '看多 👍'
  if (sentiment === 'negative') return '看空 👎'
  return '中性'
}

function formatTime(t) {
  if (!t) return '-'
  return new Date(t).toLocaleDateString('zh-CN')
}

function truncateText(text, maxLen) {
  if (!text) return ''
  return text.length > maxLen ? text.substring(0, maxLen) + '...' : text
}
</script>

<style scoped>
.evidence-chain {
  padding: 8px 0;
}

.evidence-card {
  margin-bottom: 4px;
  border-radius: 8px;
}

.evidence-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.evidence-meta {
  flex: 1;
}

.vstar-name {
  font-weight: 700;
  font-size: 15px;
  margin-right: 8px;
}

.evidence-title {
  font-size: 14px;
  color: #606266;
  margin-bottom: 8px;
  display: flex;
  align-items: flex-start;
  gap: 6px;
}

.article-link {
  color: #409EFF;
  text-decoration: none;
  word-break: break-all;
}

.article-link:hover {
  text-decoration: underline;
}

.evidence-text {
  font-size: 13px;
  color: #909399;
  line-height: 1.6;
  background-color: #f5f7fa;
  padding: 10px;
  border-radius: 6px;
  display: flex;
  gap: 6px;
  font-style: italic;
}
</style>
