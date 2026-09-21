<template>
  <el-container class="app-layout">
    <el-aside width="200px" class="sidebar-aside">
      <Sidebar />
    </el-aside>
    <el-container direction="vertical">
      <el-header class="app-header">
        <span class="header-title">ReviewDesk 工作台</span>
        <div class="header-right">
          <span class="username">{{ auth.user?.username ?? auth.user?.userId }}</span>
          <el-dropdown @command="handleCommand">
            <el-button text :icon="ArrowDown" />
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
import { ref, onErrorCaptured } from 'vue'
import { ArrowDown } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import Sidebar from './Sidebar.vue'

const auth = useAuthStore()
const router = useRouter()

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
}
.sidebar-aside {
  background: #101828;
  overflow: hidden;
}
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border-bottom: 1px solid #f0f0f0;
  padding: 0 24px;
  height: 56px;
}
.header-title {
  font-size: 18px;
  font-weight: 700;
  color: #0f766e;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}
.username {
  font-size: 14px;
  color: #595959;
}
/* 路由进度条：高度 3px，懒加载期间动态扫描动画 */
.nav-progress-bar {
  height: 3px;
  background: transparent;
  overflow: hidden;
  flex-shrink: 0;
}
.nav-progress-bar.active {
  background: #e6f6f4;
}
.nav-progress-bar.active::after {
  content: '';
  display: block;
  height: 100%;
  width: 40%;
  background: #0f766e;
  animation: nav-scan 0.9s ease-in-out infinite;
}
@keyframes nav-scan {
  0%   { transform: translateX(-100%); }
  100% { transform: translateX(350%); }
}
.app-main {
  display: flex;
  justify-content: center;
  background: #f5f6f7;
  overflow-y: auto;
  padding: 24px;
}

.app-main > * {
  width: 100%;
  max-width: 1100px;
  margin-left: auto;
  margin-right: auto;
}
</style>
