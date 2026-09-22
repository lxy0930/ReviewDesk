<template>
  <div class="sidebar">
    <div class="logo">
      <span class="logo-mark">RD</span>
      <span class="logo-copy">
        <b>ReviewDesk</b>
        <small>个人提效工作台</small>
      </span>
    </div>
    <nav class="nav-list">
      <RouterLink to="/dashboard" class="nav-item" :class="{ 'nav-item--active': isActive('/dashboard') }">
        <span class="nav-icon"><el-icon><Monitor /></el-icon></span>
        <span>工作台</span>
      </RouterLink>

      <RouterLink to="/exam" class="nav-item" :class="{ 'nav-item--active': isActive('/exam') }">
        <span class="nav-icon"><el-icon><Files /></el-icon></span>
        <span>试卷批改</span>
      </RouterLink>

      <RouterLink to="/resume" class="nav-item" :class="{ 'nav-item--active': isActive('/resume') }">
        <span class="nav-icon"><el-icon><DocumentChecked /></el-icon></span>
        <span>简历审查</span>
      </RouterLink>

      <!-- 教师端菜单（仅 teacher/admin 可见） -->
      <template v-if="auth.isTeacher">
        <div class="nav-divider" />
        <RouterLink to="/teacher/exam-review" class="nav-item" :class="{ 'nav-item--active': isActive('/teacher/exam-review') }">
          <span class="nav-icon"><el-icon><CircleCheck /></el-icon></span>
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
  padding: 8px 10px 12px 0;
  background: transparent;
}

.logo {
  min-height: 64px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 10px 14px;
  color: var(--rd-ink);
  flex-shrink: 0;
}
.logo-mark {
  width: 38px;
  height: 38px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  border-radius: 13px;
  background: var(--rd-primary);
  color: #fff;
  font-size: 13px;
  font-weight: 800;
  box-shadow: 0 8px 18px rgba(64, 83, 181, 0.22);
}
.logo-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  line-height: 1.15;
}
.logo-copy b {
  font-size: 14px;
  font-weight: 750;
  letter-spacing: -0.02em;
}
.logo-copy small {
  margin-top: 3px;
  color: var(--rd-muted);
  font-size: 10px;
  font-weight: 500;
}

.nav-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 0;
  flex: 1;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 46px;
  padding: 8px 10px;
  border: 1px solid transparent;
  border-radius: 15px;
  color: #52525b;
  text-decoration: none;
  font-size: 14px;
  font-weight: 550;
  cursor: pointer;
  transition:
    background-color 180ms ease,
    border-color 180ms ease,
    color 180ms ease;
  user-select: none;
}

.nav-item:hover {
  border-color: var(--rd-border);
  background-color: var(--rd-surface);
  color: var(--rd-ink);
}

.nav-item--active {
  border-color: #d8dbea;
  background-color: #e4e5ea;
  color: var(--rd-primary-deep);
}

.nav-icon {
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  border-radius: 10px;
  color: #71717a;
  transition:
    background-color 180ms ease,
    color 180ms ease;
}

.nav-item:hover .nav-icon,
.nav-item--active .nav-icon {
  background: rgba(64, 83, 181, 0.1);
  color: var(--rd-primary);
}

.nav-item .el-icon {
  font-size: 17px;
}

.nav-divider {
  border: none;
  border-top: 1px solid var(--rd-border);
  margin: 8px 6px;
}

@media (max-width: 900px) {
  .sidebar {
    padding: 10px 8px;
  }
  .logo {
    justify-content: center;
    padding: 2px 0 14px;
  }
  .logo-copy,
  .nav-item > span:last-child {
    display: none;
  }
  .nav-list {
    align-items: center;
  }
  .nav-item {
    width: 48px;
    min-height: 48px;
    justify-content: center;
    padding: 0;
    border-radius: 14px;
  }
  .nav-icon {
    width: 32px;
    height: 32px;
  }
  .nav-divider {
    width: 36px;
  }
}
</style>
