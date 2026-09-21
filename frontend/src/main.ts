import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import 'element-plus/dist/index.css'
import 'highlight.js/styles/github.css'
import './styles/theme.css'

import App from './App.vue'
import router from './router'

const app = createApp(App)

// 注册所有 Element Plus 图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

// 全局错误兜底：防止 Vue 调度器或组件更新过程中的错误以 unhandled rejection 形式
// 崩溃整个应用。具体恢复逻辑由 AppLayout 的 onErrorCaptured 处理。
app.config.errorHandler = (err, _instance, info) => {
  console.error('[ReviewDesk] Vue error:', info, err)
}

app.use(createPinia())
app.use(router)
app.use(ElementPlus, { locale: undefined })

app.mount('#app')
