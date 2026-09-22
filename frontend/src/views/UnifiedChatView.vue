<template>
  <div class="chat-page">
    <div class="chat-panel">
      <div class="chat-header-hint">
        <span class="chat-title-icon">
          <el-icon><ChatDotRound /></el-icon>
        </span>
        <div>
          <b>AI 助手</b>
          <span>描述需求，我会自动判断是试卷批改还是简历审查。</span>
        </div>
      </div>

      <div class="chat-messages" ref="messagesEl">
        <div v-if="messages.length === 0 && !isStreaming" class="empty-hint">
          <AiAvatar class="empty-ai-avatar" />
          <p>您好！我是 ReviewDesk AI 助手</p>
          <p>请直接告诉我您的需求，例如：</p>
          <div class="example-queries">
            <el-tag
              v-for="q in exampleQueries"
              :key="q"
              class="example-tag"
              @click="sendExample(q)"
            >{{ q }}</el-tag>
          </div>
        </div>

        <template v-for="(msg, i) in messages" :key="i">
          <RoutingDecisionCard
            v-if="msg.routingDecision"
            :agent-type="msg.routingDecision.agent_type"
            :agent-display="msg.routingDecision.agent_display"
            :confidence="msg.routingDecision.confidence"
            :reason="msg.routingDecision.reason"
            execution-mode="single"
          />

          <ChatBubble :role="msg.role" :sources="msg.sources">
            <template v-if="msg.guidance">
              <MarkdownRenderer :content="msg.guidance.message" />
              <el-button
                v-if="msg.guidance.action_label"
                type="primary"
                size="small"
                @click="router.push(msg.guidance.action_url)"
              >
                {{ msg.guidance.action_label }} →
              </el-button>
            </template>
            <MarkdownRenderer v-else :content="msg.content" />
          </ChatBubble>
        </template>

        <template v-if="isStreaming">
          <RoutingDecisionCard
            v-if="streamingRouting"
            :agent-type="streamingRouting.agent_type"
            :agent-display="streamingRouting.agent_display"
            :confidence="streamingRouting.confidence"
            :reason="streamingRouting.reason"
            execution-mode="single"
          />
          <ChatBubble role="assistant">
            <MarkdownRenderer v-if="streamingText" :content="streamingText" />
            <span v-else-if="progressStage" class="progress-hint">
              <span class="dot" /><span class="dot" /><span class="dot" />
              {{ progressStage }}
            </span>
            <span v-else class="thinking">
              <span class="dot" /><span class="dot" /><span class="dot" />
            </span>
          </ChatBubble>
        </template>
      </div>

      <div class="chat-input-area">
        <el-input
          ref="inputRef"
          v-model="inputText"
          type="textarea"
          :rows="3"
          placeholder="直接描述您的需求，Enter 发送，Shift+Enter 换行"
          resize="none"
          :disabled="isStreaming"
          @keydown="handleKeydown"
        />
        <div class="input-actions">
          <el-button
            type="primary"
            :loading="isStreaming"
            :disabled="!inputText.trim() || isStreaming"
            @click="sendMessage"
          >
            发送
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ChatDotRound } from '@element-plus/icons-vue'
import ChatBubble from '@/components/chat/ChatBubble.vue'
import AiAvatar from '@/components/chat/AiAvatar.vue'
import MarkdownRenderer from '@/components/chat/MarkdownRenderer.vue'
import RoutingDecisionCard from '@/components/chat/RoutingDecisionCard.vue'
import { useAuthStore } from '@/stores/auth'

interface RoutingDecision {
  agent_type: string
  agent_display: string
  confidence: number
  reason: string
}

interface GuidanceInfo {
  message: string
  action_label: string
  action_url: string
}

interface Message {
  role: 'user' | 'assistant'
  content: string
  sources?: string[]
  routingDecision?: RoutingDecision
  guidance?: GuidanceInfo
}

const router = useRouter()
const auth = useAuthStore()

const messages = ref<Message[]>([])
const inputText = ref('')
const messagesEl = ref<HTMLElement>()
const sessionId = ref(`unified_${auth.user?.userId ?? 'guest'}`)
const isStreaming = ref(false)
const streamingText = ref('')
const streamingRouting = ref<RoutingDecision | null>(null)
const progressStage = ref('')
const lastSources = ref<string[]>([])

const exampleQueries = [
  '我想提交试卷批改',
  '帮我审查一下简历',
  '你好',
]

function sendExample(q: string) {
  inputText.value = q
  sendMessage()
}

function handleKeydown(e: KeyboardEvent) {
  if (e.isComposing) return
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendMessage()
  }
}

async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || isStreaming.value) return

  inputText.value = ''
  messages.value.push({ role: 'user', content: text })
  await scrollToBottom()

  isStreaming.value = true
  streamingText.value = ''
  streamingRouting.value = null
  progressStage.value = ''
  lastSources.value = []

  let pendingRouting: RoutingDecision | null = null
  let pendingGuidance: GuidanceInfo | null = null

  try {
    const apiBase = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://localhost:8000'
    const resp = await fetch(`${apiBase}/api/v1/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${auth.token}`,
      },
      body: JSON.stringify({
        session_id: sessionId.value,
        message: text,
      }),
    })

    if (resp.status === 401) {
      localStorage.removeItem('edu-agent-token')
      localStorage.removeItem('edu-agent-user')
      router.push('/login')
      return
    }
    if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`)

    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop() ?? ''

      for (const line of lines) {
        if (!line.startsWith('data:')) continue
        const raw = line.slice(5).trim()
        if (!raw) continue

        try {
          const evt = JSON.parse(raw)
          if (evt.type === 'routing_decision') {
            pendingRouting = {
              agent_type: evt.agent_type,
              agent_display: evt.agent_display,
              confidence: evt.confidence,
              reason: evt.reason,
            }
            streamingRouting.value = pendingRouting
            await scrollToBottom()
          } else if (evt.type === 'progress') {
            progressStage.value = evt.stage
          } else if (evt.type === 'token') {
            progressStage.value = ''
            streamingText.value += evt.content
            await scrollToBottom()
          } else if (evt.type === 'guidance') {
            pendingGuidance = {
              message: evt.message,
              action_label: evt.action_label ?? '',
              action_url: evt.action_url ?? '',
            }
          } else if (evt.type === 'meta') {
            lastSources.value = evt.sources ?? []
          } else if (evt.type === 'error') {
            throw new Error(evt.message ?? 'SSE error')
          }
        } catch {
          // Ignore non-JSON lines.
        }
      }
    }

    messages.value.push({
      role: 'assistant',
      content: pendingGuidance?.message ?? streamingText.value,
      sources: lastSources.value,
      routingDecision: pendingRouting ?? undefined,
      guidance: pendingGuidance ?? undefined,
    })
  } finally {
    isStreaming.value = false
    streamingText.value = ''
    streamingRouting.value = null
    progressStage.value = ''
    await scrollToBottom()
  }
}

async function scrollToBottom() {
  await nextTick()
  if (messagesEl.value) {
    messagesEl.value.scrollTop = messagesEl.value.scrollHeight
  }
}
</script>

<style scoped>
.chat-page {
  display: flex;
  height: calc(100vh - 150px);
  min-height: 560px;
}
.chat-panel {
  flex: 1;
  border: 1px solid var(--rd-border);
  border-radius: var(--rd-radius-xl);
  background: #fff;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.chat-header-hint {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 15px 20px;
  font-size: 13px;
  color: var(--rd-muted);
  border-bottom: 1px solid var(--rd-border-soft);
  background: #fff;
}
.chat-header-hint > div {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.chat-header-hint b {
  color: var(--rd-ink);
  font-size: 14px;
  font-weight: 700;
}
.chat-title-icon {
  width: 36px;
  height: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  border-radius: 12px;
  color: var(--rd-primary);
  background: var(--rd-primary-soft);
  font-size: 18px;
}
.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  background: #fafafa;
}
.empty-hint {
  text-align: center;
  color: var(--rd-muted);
  margin-top: 60px;
  font-size: 15px;
  line-height: 2;
}
.empty-ai-avatar {
  margin-bottom: 8px;
}
.example-queries {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
  margin-top: 12px;
}
.example-tag {
  cursor: pointer;
  transition: transform 0.15s, border-color 0.15s;
}
.example-tag:hover {
  transform: translateY(-1px);
  border-color: var(--rd-primary);
}
.chat-input-area {
  border-top: 1px solid var(--rd-border-soft);
  padding: 14px 16px 16px;
  background: #fff;
}
.input-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 8px;
}
.thinking,
.progress-hint {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 0;
  font-size: 13px;
  color: var(--rd-muted);
}
.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #a1a1aa;
  animation: bounce 1.2s infinite ease-in-out;
}
.dot:nth-child(2) {
  animation-delay: 0.2s;
}
.dot:nth-child(3) {
  animation-delay: 0.4s;
}
@keyframes bounce {
  0%,
  80%,
  100% {
    transform: scale(0.7);
    opacity: 0.4;
  }
  40% {
    transform: scale(1.1);
    opacity: 1;
  }
}

@media (max-width: 720px) {
  .chat-page {
    height: calc(100vh - 120px);
    min-height: 520px;
  }
  .chat-messages {
    padding: 16px;
  }
}
</style>
