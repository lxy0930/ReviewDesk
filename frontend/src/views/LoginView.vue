<template>
  <div class="login-page">
    <section class="login-story">
      <div class="story-brand">
        <span class="brand-mark">RD</span>
        <span>ReviewDesk</span>
      </div>
      <div class="story-copy">
        <p class="story-label">私人工作台</p>
        <h1>把重复工作交给 AI，把判断留给自己。</h1>
        <p>
          集中处理试卷预批改、教师复核和简历诊断，让每一次反馈都更快一步。
        </p>
      </div>
      <div class="story-cards">
        <div>
          <b>Exam Agent</b>
          <span>三轨批改与薄弱点分析</span>
        </div>
        <div>
          <b>Resume Agent</b>
          <span>六维度岗位匹配诊断</span>
        </div>
      </div>
    </section>

    <section class="login-panel">
      <div class="login-form-wrap">
        <div class="mobile-brand">
          <span class="brand-mark">RD</span>
          <span>ReviewDesk</span>
        </div>

        <div class="login-header">
          <h2>欢迎回来</h2>
          <p>登录后继续处理今天的任务</p>
        </div>

        <el-form
          ref="formRef"
          :model="form"
          :rules="rules"
          label-position="top"
          @submit.prevent="handleLogin"
        >
          <el-form-item label="用户名" prop="username">
            <el-input
              v-model="form.username"
              placeholder="请输入用户名"
              size="large"
              :prefix-icon="User"
            />
          </el-form-item>
          <el-form-item label="密码" prop="password">
            <el-input
              v-model="form.password"
              type="password"
              placeholder="请输入密码"
              size="large"
              :prefix-icon="Lock"
              show-password
              @keyup.enter="handleLogin"
            />
          </el-form-item>
          <el-button
            type="primary"
            size="large"
            :loading="loading"
            class="login-button"
            @click="handleLogin"
          >
            登录
          </el-button>
        </el-form>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { User, Lock } from '@element-plus/icons-vue'
import { authApi } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()

const formRef = ref<FormInstance>()
const loading = ref(false)
const form = reactive({ username: '', password: '' })

const rules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function handleLogin() {
  await formRef.value?.validate()
  loading.value = true
  try {
    const { data } = await authApi.login({
      username: form.username,
      password: form.password,
    })
    auth.login(data.access_token, {
      userId: data.user_id,
      role: data.role as 'student' | 'teacher' | 'admin',
      username: form.username,
    })
    router.push('/dashboard')
  } catch {
    ElMessage.error('用户名或密码错误')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: grid;
  grid-template-columns: minmax(420px, 0.95fr) minmax(420px, 1.05fr);
  background: var(--rd-surface);
}

.login-story {
  position: relative;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 48px;
  background:
    linear-gradient(rgba(255, 255, 255, 0.055) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.055) 1px, transparent 1px),
    linear-gradient(145deg, #34448f 0%, #273273 58%, #1e275c 100%);
  background-size:
    24px 24px,
    24px 24px,
    auto;
  color: #fff;
}

.story-brand,
.mobile-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 700;
}

.brand-mark {
  width: 38px;
  height: 38px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 13px;
  background: rgba(255, 255, 255, 0.15);
  border: 1px solid rgba(255, 255, 255, 0.18);
  color: #fff;
  font-size: 13px;
  font-weight: 800;
}

.story-copy {
  position: relative;
  z-index: 1;
  max-width: 520px;
}

.story-label {
  margin: 0 0 16px;
  color: rgba(255, 255, 255, 0.72);
  font-size: 14px;
  font-weight: 550;
}

.story-copy h1 {
  margin: 0;
  font-size: clamp(38px, 4.2vw, 62px);
  line-height: 1.06;
  font-weight: 750;
  letter-spacing: -0.055em;
}

.story-copy > p:last-child {
  max-width: 460px;
  margin: 22px 0 0;
  color: rgba(255, 255, 255, 0.74);
  font-size: 16px;
  line-height: 1.75;
}

.story-cards {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.story-cards > div {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 15px 16px;
  border: 1px solid rgba(255, 255, 255, 0.13);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.07);
  backdrop-filter: blur(10px);
}

.story-cards b {
  font-size: 13px;
}

.story-cards span {
  color: rgba(255, 255, 255, 0.66);
  font-size: 12px;
}

.login-panel {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
  background: var(--rd-surface);
}

.login-form-wrap {
  width: 100%;
  max-width: 420px;
}

.mobile-brand {
  display: none;
  margin-bottom: 38px;
  color: var(--rd-ink);
}

.mobile-brand .brand-mark {
  background: var(--rd-primary);
  border-color: var(--rd-primary);
}

.login-header {
  margin-bottom: 30px;
}
.login-header h2 {
  margin: 0 0 8px;
  color: var(--rd-ink);
  font-size: 32px;
  font-weight: 750;
  letter-spacing: -0.035em;
}
.login-header p {
  margin: 0;
  color: var(--rd-muted);
  font-size: 14px;
}

.login-form-wrap :deep(.el-form-item) {
  margin-bottom: 22px;
}

.login-form-wrap :deep(.el-form-item__label) {
  color: var(--rd-text);
  font-weight: 600;
}

.login-form-wrap :deep(.el-input__wrapper) {
  min-height: 48px;
  padding: 1px 14px;
}

.login-button {
  width: 100%;
  min-height: 48px;
  margin-top: 6px;
}

@media (max-width: 900px) {
  .login-page {
    grid-template-columns: 1fr;
  }
  .login-story {
    display: none;
  }
  .login-panel {
    min-height: 100vh;
    padding: 28px 20px;
  }
  .mobile-brand {
    display: flex;
  }
}
</style>
