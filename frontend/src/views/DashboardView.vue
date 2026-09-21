<template>
  <div class="dashboard">
    <div class="welcome">
      <h2>欢迎回来，{{ auth.user?.username ?? auth.user?.userId }}</h2>
      <p>选择今天要处理的任务</p>
    </div>

    <!-- AI 助手入口（突出展示） -->
    <el-row :gutter="16" style="margin-bottom: 16px">
      <el-col :span="24">
        <el-card
          class="ai-assistant-card"
          shadow="hover"
          @click="router.push('/chat')"
        >
          <div class="ai-card-content">
            <div class="ai-card-left">
              <span class="ai-icon">⌁</span>
              <div>
                <div class="ai-title">AI 助手</div>
                <div class="ai-desc">描述需求，自动判断是试卷批改还是简历审查</div>
              </div>
            </div>
            <el-button type="primary" size="default">开始对话</el-button>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 已实现的独立功能入口 -->
    <el-row :gutter="16" class="feature-cards">
      <el-col :span="12" v-for="card in featureCards" :key="card.route">
        <el-card
          class="feature-card"
          shadow="hover"
          @click="router.push(card.route)"
        >
          <div class="card-icon">{{ card.icon }}</div>
          <div class="card-title">{{ card.title }}</div>
          <div class="card-desc">{{ card.desc }}</div>
          <el-button type="primary" plain size="small" style="margin-top: 12px">
            {{ card.action }}
          </el-button>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()

const featureCards = [
  {
    icon: '✍️',
    title: '试卷批改',
    desc: 'AI 预批改、薄弱点分析，教师确认后发布',
    action: '提交试卷',
    route: '/exam',
  },
  {
    icon: '🗂️',
    title: '简历审查',
    desc: '六维度评审，定位原文问题并给出修改建议',
    action: '上传简历',
    route: '/resume',
  },
]
</script>

<style scoped>
.dashboard {
  max-width: 1100px;
}
.welcome {
  margin-bottom: 24px;
}
.welcome h2 {
  margin: 0 0 4px;
  font-size: 22px;
}
.welcome p {
  margin: 0;
  color: #8c8c8c;
}
.ai-assistant-card {
  cursor: pointer;
  background: #eaf5f3;
  border: 1px solid #cce8e5;
}
.ai-card-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 0;
}
.ai-card-left {
  display: flex;
  align-items: center;
  gap: 16px;
}
.ai-icon { font-size: 36px; }
.ai-title {
  font-size: 17px;
  font-weight: 600;
  color: #0f766e;
  margin-bottom: 4px;
}
.ai-desc {
  font-size: 13px;
  color: #595959;
}
.feature-card {
  cursor: pointer;
  text-align: center;
  padding: 8px 0;
}
.card-icon {
  font-size: 40px;
  margin-bottom: 12px;
}
.card-title {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 8px;
}
.card-desc {
  font-size: 13px;
  color: #8c8c8c;
  line-height: 1.5;
  min-height: 48px;
}
</style>
