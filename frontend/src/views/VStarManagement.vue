<template>
  <div class="vstar-management">
    <el-card shadow="hover">
      <template #header>
        <div class="card-header">
          <span><el-icon><UserFilled /></el-icon> 大V管理</span>
          <div class="header-actions">
            <el-button type="primary" @click="showAddDialog">
              <el-icon><Plus /></el-icon> 添加大V
            </el-button>
          </div>
        </div>
      </template>

      <el-table :data="vstars" stripe style="width: 100%">
        <el-table-column prop="nickname" label="昵称" width="160">
          <template #default="{ row }">
            <span :class="{ 'stale-text': row.is_stale && row.is_active }">{{ row.nickname }}</span>
            <el-tooltip v-if="row.is_stale && row.is_active" content="超过7天未更新" placement="top">
              <el-tag type="warning" size="small" style="margin-left: 4px;">待更新</el-tag>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column prop="platform" label="平台" width="110">
          <template #default="{ row }">
            <el-tag>{{ row.platform }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="文章数" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.article_count > 0 ? 'success' : 'info'" size="small" round>
              {{ row.article_count || 0 }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="weight_coefficient" label="权重" width="70" align="center" />
        <el-table-column label="上次发文" width="170">
          <template #default="{ row }">
            <span v-if="row.last_article_time" :class="{ 'stale-text': row.is_stale }">
              {{ formatTime(row.last_article_time) }}
            </span>
            <span v-else class="no-data-text">暂无数据</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-switch
              v-model="row.is_active"
              @change="toggleActive(row)"
              size="small"
            />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="280" fixed="right">
          <template #default="{ row }">
            <el-button type="success" link size="small" @click="handleRefresh(row)" :loading="row._refreshing">
              <el-icon><Refresh /></el-icon> 刷新
            </el-button>
            <el-button type="primary" link size="small" @click="showArticles(row)">
              <el-icon><Document /></el-icon> 文章
            </el-button>
            <el-button type="primary" link size="small" @click="showEditDialog(row)">编辑</el-button>
            <el-button type="danger" link size="small" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 添加/编辑大V弹窗 -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEditing ? '编辑大V' : '添加大V'"
      width="500px"
    >
      <el-form :model="form" label-width="100px" :rules="rules" ref="formRef">
        <el-form-item label="昵称" prop="nickname">
          <el-input v-model="form.nickname" placeholder="请输入大V昵称（如：聪明小阿姨）" />
        </el-form-item>
        <el-form-item label="平台" prop="platform">
          <el-select v-model="form.platform" placeholder="选择平台" style="width: 100%">
            <el-option
              v-for="p in platforms"
              :key="p.value"
              :label="p.label"
              :value="p.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="数据源模式">
          <el-radio-group v-model="form.data_source_mode">
            <el-radio value="auto">自动抓取</el-radio>
            <el-radio value="manual">手动导入</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="权重系数">
          <el-input-number v-model="form.weight_coefficient" :min="0.1" :max="5.0" :step="0.1" />
          <span class="form-hint">越高该大V的提及权重越大</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit">确定</el-button>
      </template>
    </el-dialog>

    <!-- 文章列表弹窗 -->
    <el-dialog
      v-model="articlesDialogVisible"
      :title="`${articlesVStar?.nickname} 的文章列表`"
      width="800px"
      top="5vh"
    >
      <div v-if="articlesLoading" style="text-align: center; padding: 40px;">
        <el-icon class="is-loading" :size="32"><Loading /></el-icon>
        <p>加载中...</p>
      </div>
      <div v-else-if="articlesList.length === 0" style="text-align: center; padding: 40px; color: #909399;">
        <p>暂无文章数据</p>
        <el-button type="primary" style="margin-top: 12px;" @click="handleRefreshFromArticles">立即抓取</el-button>
      </div>
      <div v-else class="articles-list">
        <div v-for="a in articlesList" :key="a.id" class="article-item">
          <div class="article-title">{{ a.title }}</div>
          <div class="article-meta">
            <span>{{ formatTime(a.published_at) }}</span>
            <el-button v-if="a.url" type="primary" link size="small" @click="openUrl(a.url)">查看原文</el-button>
          </div>
          <div class="article-summary" v-if="a.summary">{{ a.summary }}</div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getVStars, createVStar, updateVStar, deleteVStar, getPlatforms, refreshVStar, getVStarArticles } from '../api'

const vstars = ref([])
const platforms = ref([])
const dialogVisible = ref(false)
const isEditing = ref(false)
const editingId = ref(null)
const formRef = ref(null)

const articlesDialogVisible = ref(false)
const articlesLoading = ref(false)
const articlesList = ref([])
const articlesVStar = ref(null)

const form = reactive({
  nickname: '',
  platform: '',
  data_source_mode: 'auto',
  weight_coefficient: 1.0,
})

const rules = {
  nickname: [{ required: true, message: '请输入昵称', trigger: 'blur' }],
  platform: [{ required: true, message: '请选择平台', trigger: 'change' }],
}

function loadVStars() {
  getVStars().then(res => {
    vstars.value = (res.data || []).map(v => ({ ...v, _refreshing: false }))
  }).catch(() => {
    ElMessage.error('加载大V列表失败')
  })
}

function loadPlatforms() {
  getPlatforms().then(res => { platforms.value = res.data })
}

function showAddDialog() {
  isEditing.value = false
  editingId.value = null
  form.nickname = ''
  form.platform = ''
  form.data_source_mode = 'auto'
  form.weight_coefficient = 1.0
  dialogVisible.value = true
}

function showEditDialog(row) {
  isEditing.value = true
  editingId.value = row.id
  form.nickname = row.nickname
  form.platform = row.platform
  form.data_source_mode = row.data_source_mode
  form.weight_coefficient = row.weight_coefficient
  dialogVisible.value = true
}

function handleSubmit() {
  formRef.value?.validate(valid => {
    if (!valid) return

    const data = { ...form }
    if (isEditing.value) {
      updateVStar(editingId.value, data).then(() => {
        ElMessage.success('更新成功')
        dialogVisible.value = false
        loadVStars()
      }).catch(err => {
        ElMessage.error(err.response?.data?.detail || '更新失败')
      })
    } else {
      createVStar(data).then(() => {
        ElMessage.success('添加成功')
        dialogVisible.value = false
        loadVStars()
      }).catch(err => {
        ElMessage.error(err.response?.data?.detail || '添加失败')
      })
    }
  })
}

function handleRefresh(row) {
  row._refreshing = true
  refreshVStar(row.id).then(res => {
    const data = res.data
    ElMessage.success(data.message || '刷新成功')
    loadVStars()
  }).catch(err => {
    ElMessage.error(err.response?.data?.detail || '刷新失败')
  }).finally(() => {
    row._refreshing = false
  })
}

function handleRefreshFromArticles() {
  if (!articlesVStar.value) return
  const vstarId = articlesVStar.value.id
  refreshVStar(vstarId).then(res => {
    ElMessage.success(res.data.message || '刷新成功')
    loadVStars()
    // 重新加载文章列表
    loadArticles(vstarId)
  }).catch(err => {
    ElMessage.error(err.response?.data?.detail || '刷新失败')
  })
}

function showArticles(row) {
  articlesVStar.value = row
  articlesDialogVisible.value = true
  loadArticles(row.id)
}

function loadArticles(vstarId) {
  articlesLoading.value = true
  articlesList.value = []
  getVStarArticles(vstarId).then(res => {
    articlesList.value = res.data.articles || []
  }).catch(() => {
    ElMessage.error('加载文章列表失败')
  }).finally(() => {
    articlesLoading.value = false
  })
}

function toggleActive(row) {
  updateVStar(row.id, { is_active: row.is_active }).then(() => {
    ElMessage.success(row.is_active ? '已启用' : '已停用')
  })
}

function handleDelete(row) {
  ElMessageBox.confirm(`确定删除大V「${row.nickname}」吗？相关数据将被清除。`, '确认删除', {
    type: 'warning',
    confirmButtonText: '删除',
    cancelButtonText: '取消',
  }).then(() => {
    deleteVStar(row.id).then(() => {
      ElMessage.success('已删除')
      loadVStars()
    })
  })
}

function openUrl(url) {
  if (url) window.open(url, '_blank')
}

function formatTime(t) {
  if (!t) return '-'
  const d = new Date(t)
  return d.toLocaleDateString('zh-CN') + ' ' + d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

onMounted(() => {
  loadVStars()
  loadPlatforms()
})
</script>

<style scoped>
.vstar-management {
  max-width: 1300px;
  margin: 0 auto;
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

.header-actions {
  display: flex;
  gap: 8px;
}

.stale-text {
  color: #c0c4cc;
}

.no-data-text {
  color: #c0c4cc;
  font-style: italic;
}

.form-hint {
  color: #909399;
  font-size: 12px;
  margin-left: 8px;
}

.articles-list {
  max-height: 500px;
  overflow-y: auto;
}

.article-item {
  padding: 14px 0;
  border-bottom: 1px solid #ebeef5;
}

.article-item:last-child {
  border-bottom: none;
}

.article-title {
  font-size: 15px;
  font-weight: 500;
  color: #303133;
  margin-bottom: 6px;
  line-height: 1.5;
}

.article-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 13px;
  color: #909399;
  margin-bottom: 4px;
}

.article-summary {
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
</style>
