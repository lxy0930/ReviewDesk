<template>
  <el-container class="app-layout">
    <el-aside width="200px" class="sidebar-aside">
      <Sidebar />
    </el-aside>
    <el-container direction="vertical">
      <el-header class="app-header">
        <div class="header-left">
          <span class="header-kicker">ReviewDesk</span>
          <span class="header-title">工作台</span>
        </div>
        <div class="header-right">
          <div class="user-chip">
            <span class="user-avatar">{{ userInitial }}</span>
            <span class="username">{{ auth.user?.username ?? auth.user?.userId }}</span>
          </div>
          <el-dropdown @command="handleCommand">
            <el-button class="account-button" text :icon="ArrowDown" />
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="logout">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>
      <!-- 路由懒加载进度条：点击菜单项后立即可见，消除"没反应"假象 -->
      <div class="nav-progress-bar" :class="{ active: navigating }" />
      <el-main class="app-main">
        <!-- routerViewKey 变化（错误恢复）时会销毁缓存，这是可接受的折中。 -->
        <router-view v-slot="{ Component }" :key="routerViewKey">
          <component :is="Component" />
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed, ref, onErrorCaptured } from 'vue'
import { ArrowDown } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import Sidebar from './Sidebar.vue'

const auth = useAuthStore()
const router = useRouter()
const userInitial = computed(() => {
  const name = auth.user?.username ?? auth.user?.userId ?? 'R'
  return name.slice(0, 1).toUpperCase()
})

// 路由切换期间（含懒加载 JS chunk 下载）显示顶部进度条
const navigating = ref(false)
router.beforeEach(() => { navigating.value = true })
router.afterEach(() => { navigating.value = false })

// 错误边界：捕获 RouterView 及所有子组件的渲染崩溃。
// 当 RouterView 的 componentUpdateFn 因 DOM 状态异常（el = null）抛出时，
// 通过更换 key 强制 RouterView 重新挂载，使其渲染当前正确路由，避免页面永久卡死。
const routerViewKey = ref(0)
let lastRecoveryAt = 0
onErrorCaptured((_err, _instance, _info) => {
  const now = Date.now()
  // 500ms 冷却，防止同一错误循环触发
  if (now - lastRecoveryAt > 500) {
    lastRecoveryAt = now
    routerViewKey.value++
  }
  return false // 阻止错误继续向上冒泡
})

function handleCommand(cmd: string) {
  if (cmd === 'logout') {
    auth.logout()
    router.push('/login')
  }
}
</script>

<style scoped>
.app-layout {
  height: 100vh;
  gap: 8px;
  padding: 8px 0 8px 8px;
  background: var(--rd-shell);
}
.sidebar-aside {
  background: transparent;
  overflow: hidden;
  flex-shrink: 0;
}
.app-layout > .el-container {
  min-width: 0;
  overflow: hidden;
  border: 1px solid var(--rd-border);
  border-radius: var(--rd-radius-xl) 0 0 var(--rd-radius-xl);
  background: var(--rd-surface);
}
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 64px;
  padding: 0 28px;
  background: var(--rd-surface);
  border-bottom: 1px solid var(--rd-border-soft);
}
.header-left {
  display: flex;
  align-items: baseline;
  gap: 10px;
}
.header-kicker {
  color: var(--rd-primary);
  font-size: 13px;
  font-weight: 750;
  letter-spacing: -0.01em;
}
.header-title {
  color: var(--rd-ink);
  font-size: 16px;
  font-weight: 650;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}
.user-chip {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 5px 8px 5px 5px;
  border: 1px solid var(--rd-border);
  border-radius: 999px;
  background: #fafafa;
}
.user-avatar {
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: var(--rd-primary);
  color: #fff;
  font-size: 12px;
  font-weight: 750;
}
.username {
  font-size: 14px;
  color: var(--rd-text);
  font-weight: 550;
}
.account-button {
  width: 34px;
  min-height: 34px;
  padding: 0;
  border-radius: 50%;
  color: var(--rd-muted);
}
/* 路由进度条：高度 3px，懒加载期间动态扫描动画 */
.nav-progress-bar {
  height: 3px;
  background: transparent;
  overflow: hidden;
  flex-shrink: 0;
}
.nav-progress-bar.active {
  background: var(--rd-primary-soft);
}
.nav-progress-bar.active::after {
  content: '';
  display: block;
  height: 100%;
  width: 40%;
  background: var(--rd-primary);
  animation: nav-scan 0.9s ease-in-out infinite;
}
@keyframes nav-scan {
  0%   { transform: translateX(-100%); }
  100% { transform: translateX(350%); }
}
.app-main {
  display: flex;
  justify-content: center;
  background: var(--rd-surface);
  overflow-y: auto;
  padding: 28px 32px 40px;
}

.app-main > * {
  width: 100%;
  max-width: 1180px;
  margin-left: auto;
  margin-right: auto;
}

@media (max-width: 900px) {
  .app-layout {
    gap: 0;
    padding: 0;
  }
  .sidebar-aside {
    --el-aside-width: 72px !important;
    width: 72px !important;
  }
  .app-layout > .el-container {
    border-left: 0;
    border-radius: 0;
  }
  .app-header {
    height: 58px;
    padding: 0 16px;
  }
  .header-kicker,
  .username {
    display: none;
  }
  .user-chip {
    padding: 3px;
    border: 0;
    background: transparent;
  }
  .app-main {
    padding: 20px 16px 32px;
  }
}
</style>
