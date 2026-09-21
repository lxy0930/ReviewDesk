<template>
  <div class="exam-result">
    <el-page-header @back="router.push('/exam')" title="返回" content="批改结果" />

    <div v-if="loading" class="loading-state">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else-if="review">
      <!-- 状态提示 -->
      <el-alert
        v-if="review.pre_review_summary"
        :title="statusTitle"
        :type="statusAlertType"
        :closable="false"
        style="margin: 16px 0"
      />

      <!-- 总分卡片 -->
      <el-row :gutter="16" style="margin-bottom: 16px">
        <el-col :span="6">
          <el-card class="score-card">
            <div class="score-num">
              {{ review.pre_review_summary?.total_score ?? '--' }}
              <span class="score-full">/ {{ review.pre_review_summary?.full_score ?? '--' }}</span>
            </div>
            <div class="score-label">{{ review.status === 'published' ? '最终得分' : 'AI 预评分' }}</div>
          </el-card>
        </el-col>
        <el-col :span="18" v-if="review.weak_points?.length">
          <el-card>
            <div class="weak-title">知识薄弱点</div>
            <div class="weak-tags">
              <el-tag
                v-for="wp in review.weak_points"
                :key="wp.tag"
                type="danger"
                size="small"
                style="margin: 4px"
              >
                {{ wp.tag }}（错 {{ wp.wrong_count }} 题）
              </el-tag>
            </div>
            <div v-if="review.weak_points_summary" class="weak-summary">
              {{ review.weak_points_summary }}
            </div>
          </el-card>
        </el-col>
      </el-row>

      <!-- 逐题详情 -->
      <el-card>
        <template #header>逐题批改详情</template>
        <el-collapse>
          <el-collapse-item
            v-for="q in review.pre_review_summary?.by_question"
            :key="q.question_id"
            :name="q.question_id"
          >
            <template #title>
              <div class="q-title">
                <span>第 {{ q.question_no }} 题（{{ typeLabel(q.question_type) }}）</span>
                <el-tag
                  type="success"
                  size="small"
                  style="margin-left: 8px"
                >
                  {{ q.final_score ?? q.score }} / {{ q.full_score }} 分
                </el-tag>
              </div>
            </template>

            <div class="q-detail">
              <div v-if="q.content" class="q-row">
                <b>题目：</b>
                <span class="q-content">{{ q.content }}</span>
              </div>
              <div class="q-row"><b>学员答案：</b>{{ q.student_answer }}</div>
              <div v-if="q.correct_answer" class="q-row"><b>参考答案：</b>{{ q.correct_answer }}</div>
              <div class="q-row"><b>AI 反馈：</b>{{ q.ai_feedback }}</div>
              <div v-if="q.teacher_comment" class="q-row teacher-comment">
                <b>教师批注：</b>{{ q.teacher_comment }}
              </div>
              <div v-if="q.final_score !== undefined" class="q-row">
                <b>最终得分：</b>{{ q.final_score }} 分
              </div>
            </div>
          </el-collapse-item>
        </el-collapse>
      </el-card>
    </template>

    <el-empty v-else description="暂无批改结果，请稍后刷新" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { examApi, type ReviewDetail } from '@/api/exam'

const route = useRoute()
const router = useRouter()
const loading = ref(true)
const review = ref<ReviewDetail | null>(null)
let pollTimer: ReturnType<typeof setTimeout> | null = null

const statusTitle = computed(() => {
  if (!review.value) return ''
  if (review.value.status === 'published') return '✅ 教师已确认发布，以下为最终成绩'
  if (review.value.status === 'pending_review') return '⏳ AI 批改完成，等待教师确认'
  return '🔄 AI 正在批改中，请稍候...'
})

const statusAlertType = computed(() => {
  if (review.value?.status === 'published') return 'success'
  if (review.value?.status === 'pending_review') return 'warning'
  return 'info'
})

function typeLabel(type: string) {
  const map: Record<string, string> = {
    single_choice: '单选',
    multi_choice: '多选',
    judge: '判断',
    short_answer: '简答',
    code: '代码',
  }
  return map[type] ?? type
}

async function fetchReview() {
  try {
    const { data } = await examApi.getSubmissionReview(route.params.submissionId as string)
    review.value = data
    // 已发布或有结果时停止轮询
    if (data.status === 'published' || data.pre_review_summary) {
      stopPoll()
    }
  } catch {
    stopPoll()
  } finally {
    loading.value = false
  }
}

function stopPoll() {
  if (pollTimer) { clearTimeout(pollTimer); pollTimer = null }
}

onMounted(() => {
  fetchReview()
  // 使用递归setTimeout替代setInterval，避免请求堆积
  const schedulePoll = () => {
    pollTimer = setTimeout(async () => {
      await fetchReview()
      // 只有在仍在处理中时才继续轮询
      if (review.value?.status !== 'published' && !review.value?.pre_review_summary) {
        schedulePoll()
      }
    }, 8_000) // 缩短到8秒，更快响应完成状态
  }
  schedulePoll()
})

onUnmounted(stopPoll)
</script>

<style scoped>
.exam-result { max-width: 900px; }
.loading-state { margin-top: 24px; }
.score-card { text-align: center; padding: 8px 0; }
.score-num { font-size: 36px; font-weight: 700; color: #1677ff; }
.score-full { font-size: 18px; color: #8c8c8c; }
.score-label { font-size: 13px; color: #8c8c8c; margin-top: 4px; }
.weak-title { font-weight: 500; margin-bottom: 8px; }
.weak-tags { margin-bottom: 8px; }
.weak-summary { font-size: 13px; color: #595959; }
.q-title { display: flex; align-items: center; }
.q-detail { padding: 8px 0; }
.q-row { margin-bottom: 8px; font-size: 14px; line-height: 1.6; }
.q-content { white-space: pre-wrap; }
.teacher-comment { color: #d46b08; background: #fff7e6; padding: 6px 10px; border-radius: 4px; }
</style>
