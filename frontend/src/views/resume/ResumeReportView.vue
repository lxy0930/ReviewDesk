<template>
  <div class="resume-report">
    <el-page-header @back="router.push('/resume')" title="返回" content="简历审查报告" />

    <div v-if="loading" style="margin-top: 24px">
      <el-skeleton :rows="10" animated />
    </div>

    <template v-else-if="review?.status === 'done' && review.dimension_scores">
      <!-- 综合评分 -->
      <el-card style="margin: 16px 0; text-align: center">
        <div class="total-score">{{ review.weighted_score?.toFixed(1) }}</div>
        <div class="total-label">综合评分（满分 100）</div>
        <div class="total-comment" v-if="review.summary?.overall_comment">
          {{ review.summary.overall_comment }}
        </div>
      </el-card>

      <el-card style="margin-bottom: 16px">
        <template #header>目标岗位</template>
        <div style="font-weight: 600; margin-bottom: 8px">
          {{ review.target_position || '未填写' }}
        </div>
        <div style="color: #595959; line-height: 1.7; white-space: pre-wrap">
          {{ review.job_description || '未填写岗位描述' }}
        </div>
      </el-card>

      <!-- 六维度评分 -->
      <el-row :gutter="16" style="margin-bottom: 16px">
        <el-col
          :span="8"
          v-for="dim in review.dimension_scores"
          :key="dim.key"
          style="margin-bottom: 16px"
        >
          <DimensionScoreCard
            :dimension="dim.dimension"
            :score="dim.score"
            :weight="dim.weight"
            :issues="dim.issues"
            :suggestions="dim.suggestions"
          />
        </el-col>
      </el-row>

      <!-- 问题清单 -->
      <el-card v-if="review.issues?.length" style="margin-bottom: 16px">
        <template #header>问题清单（按优先级排序）</template>
        <el-table :data="visibleIssues" size="small">
          <el-table-column label="优先级" width="80">
            <template #default="{ row }">
              <el-tag :type="priorityType(row.priority)" size="small">{{ row.priority }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="dimension" label="维度" width="100" />
          <el-table-column prop="description" label="问题描述" />
          <el-table-column prop="location" label="原文位置" width="160" />
          <el-table-column prop="suggestion" label="修改建议" />
        </el-table>
        <el-button
          v-if="review.issues.length > 3"
          class="issue-toggle"
          text
          type="primary"
          size="small"
          @click="issuesExpanded = !issuesExpanded"
        >
          {{ issuesExpanded ? '收起' : `展开全部（${review.issues.length} 条）` }}
        </el-button>
      </el-card>

      <!-- 总结 -->
      <el-card v-if="review.summary">
        <template #header>综合建议</template>
        <el-row :gutter="16">
          <el-col :span="12">
            <div class="summary-section">
              <div class="summary-title">✅ 亮点</div>
              <ul>
                <li v-for="(h, i) in review.summary.highlights" :key="i">{{ h }}</li>
              </ul>
            </div>
          </el-col>
          <el-col :span="12">
            <div class="summary-section">
              <div class="summary-title">🔧 核心改进项</div>
              <ul>
                <li v-for="(c, i) in review.summary.core_improvements" :key="i">{{ c }}</li>
              </ul>
            </div>
          </el-col>
        </el-row>
        <div class="fit-assessment" v-if="review.summary.fit_assessment">
          <b>岗位匹配度评估：</b>{{ review.summary.fit_assessment }}
        </div>
      </el-card>
    </template>

    <el-card v-else-if="review?.status === 'processing'" style="margin-top: 16px; text-align: center">
      <el-icon class="is-loading" style="font-size: 32px; color: #1677ff"><Loading /></el-icon>
      <p>AI 正在审查中，请稍候...</p>
      <p style="color: #8c8c8c; font-size: 13px">通常需要 30-60 秒</p>
      <p v-if="transientError" style="color: #d46b08; font-size: 13px">{{ transientError }}</p>
    </el-card>

    <el-card v-else-if="review?.status === 'failed'" style="margin-top: 16px; text-align: center">
      <el-result icon="error" title="审查失败" :sub-title="review?.error_msg || '请重新上传简历'">
        <template #extra>
          <el-button type="primary" @click="router.push('/resume')">重新上传</el-button>
        </template>
      </el-result>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Loading } from '@element-plus/icons-vue'
import { resumeApi, type ReviewDetail } from '@/api/resume'
import DimensionScoreCard from '@/components/resume/DimensionScoreCard.vue'

const route = useRoute()
const router = useRouter()
const loading = ref(true)
const review = ref<ReviewDetail | null>(null)
const transientError = ref('')
const issuesExpanded = ref(false)
let pollTimer: ReturnType<typeof setTimeout> | null = null
let mounted = false

const visibleIssues = computed(() => {
  const issues = review.value?.issues ?? []
  return issuesExpanded.value ? issues : issues.slice(0, 3)
})

function priorityType(p: string) {
  if (p === 'high') return 'danger'
  if (p === 'medium') return 'warning'
  return 'info'
}

async function fetchReview() {
  if (!mounted) return
  try {
    const { data } = await resumeApi.getReview(route.params.reviewId as string)
    if (!mounted) return  // navigated away while request was in-flight
    transientError.value = ''
    review.value = data
    if (data.status !== 'processing') stopPoll()
  } catch {
    if (mounted) transientError.value = '服务短暂不可用，正在自动重试...'
  } finally {
    if (mounted) loading.value = false
  }
}

function stopPoll() {
  if (pollTimer) { clearTimeout(pollTimer); pollTimer = null }
}

onMounted(() => {
  mounted = true
  fetchReview()
  // 使用递归setTimeout替代setInterval，避免请求堆积
  // 同时减轻浏览器并发连接压力
  const schedulePoll = () => {
    if (!mounted) return
    pollTimer = setTimeout(async () => {
      await fetchReview()
      // 仅在未拿到终态时继续轮询（处理中的短暂请求失败也会继续）
      if (mounted && (!review.value || review.value.status === 'processing')) {
        schedulePoll()
      }
    }, 5_000) // 缩短到5秒，更快响应完成状态
  }
  schedulePoll()
})
onUnmounted(() => {
  mounted = false
  stopPoll()
})
</script>

<style scoped>
.resume-report { max-width: 1100px; }
.total-score { font-size: 56px; font-weight: 700; color: #1677ff; line-height: 1; }
.total-label { font-size: 14px; color: #8c8c8c; margin: 4px 0 8px; }
.total-comment { font-size: 14px; color: #595959; max-width: 600px; margin: 0 auto; }
.summary-section { margin-bottom: 12px; }
.summary-title { font-weight: 500; margin-bottom: 6px; }
.summary-section ul { padding-left: 20px; margin: 0; font-size: 14px; line-height: 1.8; }
.fit-assessment { margin-top: 12px; font-size: 14px; color: #595959; }
.issue-toggle { margin-top: 10px; }
</style>
