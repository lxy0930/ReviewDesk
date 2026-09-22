<template>
  <div class="dashboard">
    <div class="welcome">
      <div>
        <p class="welcome-label">今天想先处理什么？</p>
        <h2>欢迎回来，{{ auth.user?.username ?? auth.user?.userId }}</h2>
      </div>
      <div class="welcome-status">
        <span class="status-dot" />
        <span>工作台已就绪</span>
      </div>
    </div>

    <!-- AI 助手入口（突出展示） -->
    <el-row :gutter="18" style="margin-bottom: 18px">
      <el-col :span="24">
        <el-card
          class="ai-assistant-card"
          shadow="never"
          @click="router.push('/chat')"
        >
          <div class="ai-card-content">
            <div class="ai-card-left">
              <span class="ai-icon">
                <el-icon><MagicStick /></el-icon>
              </span>
              <div>
                <div class="ai-title">AI 助手</div>
                <div class="ai-desc">直接描述需求，系统会自动判断该进入试卷批改还是简历审查。</div>
              </div>
            </div>
            <el-button class="ai-action" size="default">
              开始对话
              <el-icon><ArrowRight /></el-icon>
            </el-button>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 已实现的独立功能入口 -->
    <div class="section-heading">
      <h3>独立工具</h3>
      <span>需要直接处理时，从这里进入</span>
    </div>
    <el-row :gutter="18" class="feature-cards">
      <el-col :span="12" v-for="card in featureCards" :key="card.route">
        <el-card
          class="feature-card"
          shadow="never"
          @click="router.push(card.route)"
        >
          <div class="card-top">
            <div class="card-icon">
              <el-icon><component :is="card.icon" /></el-icon>
            </div>
            <el-icon class="card-arrow"><ArrowRight /></el-icon>
          </div>
          <div class="card-title">{{ card.title }}</div>
          <div class="card-desc">{{ card.desc }}</div>
          <div class="card-action">{{ card.action }}</div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import {
  ArrowRight,
  DocumentChecked,
  Files,
  MagicStick,
} from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()

const featureCards = [
  {
    icon: Files,
    title: '试卷批改',
    desc: '上传 Word 答卷，获得 AI 预批改、知识薄弱点和教师复核流程。',
    action: '提交试卷',
    route: '/exam',
  },
  {
    icon: DocumentChecked,
    title: '简历审查',
    desc: '结合目标岗位描述，从六个维度定位问题并给出修改建议。',
    action: '上传简历',
    route: '/resume',
  },
]
</script>

<style scoped>
.dashboard {
  max-width: 1180px;
}
.welcome {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 24px;
}
.welcome-label {
  margin: 0 0 6px;
  color: var(--rd-primary);
  font-size: 13px;
  font-weight: 650;
}
.welcome h2 {
  margin: 0;
  color: var(--rd-ink);
  font-size: 30px;
  font-weight: 750;
  letter-spacing: -0.035em;
}
.welcome-status {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 7px 11px;
  border: 1px solid var(--rd-border);
  border-radius: 999px;
  color: var(--rd-muted);
  background: #fafafa;
  font-size: 12px;
}
.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #22c55e;
  box-shadow: 0 0 0 3px rgba(34, 197, 94, 0.12);
}
.ai-assistant-card {
  cursor: pointer;
  color: #fff;
  background: #34448f;
  border-color: #34448f;
}
.ai-assistant-card:hover {
  border-color: #4053b5;
  box-shadow: 0 18px 40px rgba(41, 53, 121, 0.18);
  transform: translateY(-1px);
}
.ai-assistant-card :deep(.el-card__body) {
  padding: 24px 26px;
}
.ai-card-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
}
.ai-card-left {
  display: flex;
  align-items: center;
  gap: 18px;
}
.ai-icon {
  width: 48px;
  height: 48px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.13);
  border: 1px solid rgba(255, 255, 255, 0.14);
  font-size: 23px;
}
.ai-title {
  margin-bottom: 5px;
  font-size: 18px;
  font-weight: 700;
}
.ai-desc {
  max-width: 620px;
  color: rgba(255, 255, 255, 0.72);
  font-size: 14px;
  line-height: 1.55;
}
.ai-action {
  color: var(--rd-primary-deep);
  border-color: #fff;
  background: #fff;
}
.ai-action:hover {
  color: var(--rd-primary-deep);
  border-color: #f4f4f5;
  background: #f4f4f5;
}
.ai-action .el-icon {
  margin-left: 6px;
}
.section-heading {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin: 30px 0 14px;
}
.section-heading h3 {
  margin: 0;
  color: var(--rd-ink);
  font-size: 17px;
  font-weight: 700;
}
.section-heading span {
  color: var(--rd-muted);
  font-size: 13px;
}
.feature-card {
  height: 100%;
  cursor: pointer;
}
.feature-card:hover {
  border-color: #c9cede;
  box-shadow: var(--rd-shadow-soft);
  transform: translateY(-2px);
}
.feature-card :deep(.el-card__body) {
  padding: 24px;
}
.card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
}
.card-icon {
  width: 48px;
  height: 48px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 16px;
  color: var(--rd-primary);
  background: var(--rd-primary-soft);
  font-size: 22px;
}
.card-arrow {
  color: #a1a1aa;
  font-size: 18px;
}
.card-title {
  margin-bottom: 9px;
  color: var(--rd-ink);
  font-size: 19px;
  font-weight: 700;
}
.card-desc {
  min-height: 46px;
  color: var(--rd-muted);
  font-size: 14px;
  line-height: 1.65;
}
.card-action {
  margin-top: 20px;
  color: var(--rd-primary);
  font-size: 13px;
  font-weight: 650;
}

@media (max-width: 760px) {
  .welcome {
    align-items: flex-start;
    flex-direction: column;
  }
  .welcome h2 {
    font-size: 25px;
  }
  .ai-card-content {
    align-items: flex-start;
    flex-direction: column;
  }
  .ai-card-left {
    align-items: flex-start;
  }
  .feature-cards :deep(.el-col) {
    max-width: 100%;
    flex: 0 0 100%;
  }
}
</style>
