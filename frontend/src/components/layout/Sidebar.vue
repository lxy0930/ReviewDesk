<template>
  <div class="sidebar">
    <div class="logo">
      <span>ReviewDesk 工作台</span>
    </div>
    <nav class="nav-list">
      <RouterLink to="/dashboard" class="nav-item" :class="{ 'nav-item--active': isActive('/dashboard') }">
        <el-icon><Monitor /></el-icon>
        <span>工作台</span>
      </RouterLink>

      <RouterLink to="/exam" class="nav-item" :class="{ 'nav-item--active': isActive('/exam') }">
        <el-icon><Files /></el-icon>
        <span>试卷批改</span>
      </RouterLink>

      <RouterLink to="/resume" class="nav-item" :class="{ 'nav-item--active': isActive('/resume') }">
        <el-icon><DocumentChecked /></el-icon>
        <span>简历审查</span>
      </RouterLink>

      <!-- 教师端菜单（仅 teacher/admin 可见） -->
      <template v-if="auth.isTeacher">
        <div class="nav-divider" />
        <RouterLink to="/teacher/exam-review" class="nav-item" :class="{ 'nav-item--active': isActive('/teacher/exam-review') }">
          <el-icon><CircleCheck /></el-icon>
          <span>批改确认</span>
        </RouterLink>
      </template>
    </nav>
  </div>
</template>

<script setup lang="ts">
import { useRoute } from 'vue-router'
import { Monitor, Files, DocumentChecked, CircleCheck } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const route = useRoute()

// 仅用于子路由高亮（纯视觉反馈，不参与导航逻辑）
// RouterLink 的 active-class 基于路由记录层级，不覆盖平级子路由（如 /resume/:id）
function isActive(prefix: string) {
  return route.path === prefix || route.path.startsWith(prefix + '/')
}
</script>

<style scoped>
.sidebar {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.logo {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #f8fafc;
  font-size: 16px;
  font-weight: 650;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  flex-shrink: 0;
}

.nav-list {
  display: flex;
  flex-direction: column;
  padding: 4px 0;
  flex: 1;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 13px 20px;
  color: rgba(248, 250, 252, 0.66);
  text-decoration: none;
  font-size: 14px;
  cursor: pointer;
  transition: background-color 0.2s, color 0.2s;
  user-select: none;
}

.nav-item:hover {
  background-color: rgba(255, 255, 255, 0.08);
  color: #f8fafc;
}

.nav-item--active {
  background-color: #0f766e;
  color: #fff;
  border-left: 3px solid #5eead4;
}

.nav-item .el-icon {
  font-size: 16px;
  flex-shrink: 0;
}

.nav-divider {
  border: none;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
  margin: 8px 0;
}
</style>
