<template>
  <div class="chat-bubble" :class="role">
    <div class="avatar">
      <AiAvatar v-if="role === 'assistant'" />
      <span v-else>👤</span>
    </div>
    <div class="bubble-body">
      <div class="bubble-content">
        <slot />
      </div>
      <div v-if="role === 'assistant' && sources?.length" class="sources">
        <el-collapse>
          <el-collapse-item title="参考来源" name="sources">
            <ul>
              <li v-for="(src, i) in sources" :key="i">{{ src }}</li>
            </ul>
          </el-collapse-item>
        </el-collapse>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import AiAvatar from './AiAvatar.vue'

defineProps<{
  role: 'user' | 'assistant'
  sources?: string[]
}>()
</script>

<style scoped>
.chat-bubble {
  display: flex;
  gap: 12px;
  margin-bottom: 18px;
}
.chat-bubble.user {
  flex-direction: row-reverse;
}
.avatar {
  font-size: 24px;
  flex-shrink: 0;
  width: 38px;
  height: 38px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.bubble-body {
  max-width: 72%;
}
.bubble-content {
  padding: 12px 16px;
  border-radius: 18px;
  font-size: 14px;
  line-height: 1.68;
  word-break: break-word;
}
.user .bubble-content {
  background: var(--rd-primary);
  color: #fff;
  border-bottom-right-radius: 6px;
  box-shadow: 0 8px 18px rgba(64, 83, 181, 0.16);
}
.assistant .bubble-content {
  background: #fff;
  border: 1px solid var(--rd-border);
  border-bottom-left-radius: 6px;
  box-shadow: 0 8px 24px rgba(24, 24, 27, 0.04);
}
.sources {
  margin-top: 6px;
  font-size: 12px;
}
.sources ul {
  margin: 0;
  padding-left: 16px;
  color: var(--rd-muted);
}
</style>
