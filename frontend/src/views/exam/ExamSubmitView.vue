<template>
  <div class="exam-submit">
    <el-card>
      <template #header>
        <span>📝 提交试卷</span>
      </template>

      <el-form :model="form" label-width="100px" style="max-width: 560px">
        <el-form-item label="试卷 ID">
          <el-input v-model="form.examId" placeholder="请输入试卷 ID（由教师提供）" />
        </el-form-item>
        <el-form-item label="答题文件">
          <el-upload
            ref="uploadRef"
            :auto-upload="false"
            :limit="1"
            accept=".docx"
            :on-change="handleFileChange"
            :on-remove="() => (form.file = null)"
          >
            <el-button :icon="Upload">选择文件</el-button>
            <template #tip>
              <div class="upload-tip">仅支持 .docx 格式，最大 20MB</div>
            </template>
          </el-upload>
        </el-form-item>
        <el-form-item>
          <el-button
            type="primary"
            :loading="loading"
            :disabled="!form.examId || !form.file"
            @click="handleSubmit"
          >
            提交批改
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 历史提交记录 -->
    <el-card style="margin-top: 16px">
      <template #header>
        <span>历史提交</span>
      </template>
      <el-empty v-if="!recentSubmissions.length" description="暂无提交记录" />
      <el-table v-else :data="recentSubmissions" size="small">
        <el-table-column prop="exam_title" label="试卷" />
        <el-table-column label="提交时间" width="180">
          <template #default="{ row }">
            {{ formatDateTime(row.submitted_at) }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="140">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100">
          <template #default="{ row }">
            <el-button
              text
              type="primary"
              size="small"
              @click="router.push(`/exam/${row.submission_id}`)"
            >
              查看结果
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, type UploadFile } from 'element-plus'
import { Upload } from '@element-plus/icons-vue'
import { examApi, type MySubmissionItem } from '@/api/exam'
import { formatDateTime } from '@/utils/date'

const router = useRouter()
const loading = ref(false)
const form = reactive({ examId: '', file: null as File | null })
const recentSubmissions = ref<MySubmissionItem[]>([])

async function fetchSubmissions() {
  try {
    const { data } = await examApi.listMySubmissions()
    recentSubmissions.value = data.items
  } catch {
    // 忽略
  }
}

function handleFileChange(file: UploadFile) {
  form.file = file.raw ?? null
}

function statusType(status: string) {
  if (status === 'published') return 'success'
  if (status === 'pending_review') return 'warning'
  if (status === 'submitted') return 'danger'
  return 'info'
}

function statusLabel(status: string) {
  if (status === 'published') return '已发布'
  if (status === 'pending_review') return '等待教师确认'
  if (status === 'ai_processing') return 'AI 批改中'
  if (status === 'submitted') return '处理失败，请重新提交'
  return status
}

async function handleSubmit() {
  if (!form.examId || !form.file) return
  loading.value = true
  try {
    const { data } = await examApi.submit(form.examId, form.file)
    if (data.already_submitted) {
      ElMessage.info('该试卷已经提交，正在打开已有记录...')
      router.push(`/exam/${data.submission_id}`)
      return
    }
    ElMessage.success('提交成功，AI 正在批改中...')
    form.examId = ''
    form.file = null
    await fetchSubmissions()
  } catch {
    // 错误已由 client 拦截器处理
  } finally {
    loading.value = false
  }
}

onMounted(fetchSubmissions)
</script>

<style scoped>
.exam-submit { max-width: 800px; }
.upload-tip { font-size: 12px; color: #8c8c8c; margin-top: 4px; }
</style>
