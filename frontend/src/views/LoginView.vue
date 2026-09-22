<template>
  <div class="login-page">
    <section class="login-story">
      <div class="story-brand">
        <span class="brand-mark">RD</span>
        <span>ReviewDesk</span>
      </div>
      <div class="character-scene">
        <AnimatedCharacters
          :is-typing="isTyping"
          :show-password="showPassword"
          :password-length="form.password.length"
        />
      </div>
      <div class="story-footer">
        <div>
          <b>让批改更快，让建议更具体</b>
          <span>试卷预批改、教师复核与简历诊断都集中在这里。</span>
        </div>
        <span class="story-status">Private workspace</span>
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
              @focus="focusedField = 'username'"
              @blur="focusedField = null"
            />
          </el-form-item>
          <el-form-item label="密码" prop="password">
            <el-input
              v-model="form.password"
              :type="showPassword ? 'text' : 'password'"
              placeholder="请输入密码"
              size="large"
              :prefix-icon="Lock"
              @focus="focusedField = 'password'"
              @blur="focusedField = null"
              @keyup.enter="handleLogin"
            >
              <template #suffix>
                <el-icon
                  class="password-toggle"
                  @mousedown.prevent
                  @click="showPassword = !showPassword"
                >
                  <View v-if="showPassword" />
                  <Hide v-else />
                </el-icon>
              </template>
            </el-input>
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
import { computed, ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { Hide, Lock, User, View } from '@element-plus/icons-vue'
import { authApi } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'
import AnimatedCharacters from '@/components/login/AnimatedCharacters.vue'

const router = useRouter()
const auth = useAuthStore()

const formRef = ref<FormInstance>()
const loading = ref(false)
const focusedField = ref<'username' | 'password' | null>(null)
const showPassword = ref(false)
const form = reactive({ username: '', password: '' })
const isTyping = computed(() => focusedField.value !== null)

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

.character-scene {
  position: relative;
  z-index: 1;
  min-height: 430px;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  overflow: hidden;
}

.story-footer {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  padding-top: 18px;
  border-top: 1px solid rgba(255, 255, 255, 0.13);
}

.story-footer > div {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.story-footer b {
  font-size: 14px;
  font-weight: 650;
}

.story-footer span {
  color: rgba(255, 255, 255, 0.64);
  font-size: 12px;
}

.story-status {
  padding: 5px 9px;
  border: 1px solid rgba(255, 255, 255, 0.13);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.07);
  white-space: nowrap;
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

.password-toggle {
  cursor: pointer;
  color: var(--rd-muted);
  transition: color 160ms ease;
}

.password-toggle:hover {
  color: var(--rd-primary);
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
