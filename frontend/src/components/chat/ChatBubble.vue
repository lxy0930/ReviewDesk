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
  gap: 10px;
  margin-bottom: 16px;
}
.chat-bubble.user {
  flex-direction: row-reverse;
}
.avatar {
  font-size: 24px;
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.bubble-body {
  max-width: 72%;
}
.bubble-content {
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.6;
  word-break: break-word;
}
.user .bubble-content {
  background: #1677ff;
  color: #fff;
  border-bottom-right-radius: 4px;
}
.assistant .bubble-content {
  background: #fff;
  border: 1px solid #f0f0f0;
  border-bottom-left-radius: 4px;
}
.sources {
  margin-top: 6px;
  font-size: 12px;
}
.sources ul {
  margin: 0;
  padding-left: 16px;
  color: #595959;
}
</style>
