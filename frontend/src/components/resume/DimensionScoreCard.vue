<template>
  <el-card class="dimension-card">
    <div class="dim-header">
      <span class="dim-name">{{ dimension }}</span>
      <div class="dim-score">
        <span class="score-val">{{ score }}</span>
        <span class="score-max">/100</span>
      </div>
    </div>
    <el-progress
      :percentage="score"
      :color="progressColor"
      :stroke-width="8"
      :show-text="false"
      style="margin: 8px 0"
    />
    <div class="dim-weight">权重 {{ (weight * 100).toFixed(0) }}%</div>

    <div v-if="issues.length" class="issue-list">
      <div v-for="(issue, i) in visibleIssues" :key="i" class="issue-item">
        <el-icon color="#ff4d4f"><Warning /></el-icon>
        <span>{{ issue }}</span>
      </div>
    </div>

    <div v-if="suggestions.length" class="suggestion-list">
      <div v-for="(s, i) in visibleSuggestions" :key="i" class="suggestion-item">
        <el-icon color="#52c41a"><CircleCheck /></el-icon>
        <span>{{ s }}</span>
      </div>
    </div>

    <el-button
      v-if="hasMore"
      text
      type="primary"
      size="small"
      @click="expanded = !expanded"
    >
      {{ expanded ? '收起' : '展开更多' }}
    </el-button>
  </el-card>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Warning, CircleCheck } from '@element-plus/icons-vue'

const props = defineProps<{
  dimension: string
  score: number
  weight: number
  issues: string[]
  suggestions: string[]
}>()
const expanded = ref(false)
const visibleIssues = computed(() =>
  expanded.value ? props.issues : props.issues.slice(0, 1)
)
const visibleSuggestions = computed(() =>
  expanded.value ? props.suggestions : props.suggestions.slice(0, 1)
)
const hasMore = computed(() =>
  props.issues.length > 1 || props.suggestions.length > 1
)

const progressColor = computed(() => {
  if (props.score >= 80) return '#52c41a'
  if (props.score >= 60) return '#faad14'
  return '#ff4d4f'
})
</script>

<style scoped>
.dimension-card { height: 100%; }
.dim-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.dim-name { font-weight: 500; font-size: 14px; }
.dim-score { display: flex; align-items: baseline; gap: 2px; }
.score-val { font-size: 22px; font-weight: 700; color: #1677ff; }
.score-max { font-size: 13px; color: #8c8c8c; }
.dim-weight { font-size: 12px; color: #8c8c8c; margin-bottom: 8px; }
.issue-list, .suggestion-list { margin-top: 8px; }
.issue-item, .suggestion-item {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  font-size: 13px;
  line-height: 1.5;
  margin-bottom: 4px;
}
</style>
