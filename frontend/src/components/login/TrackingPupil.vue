<template>
  <span ref="pupilEl" class="tracking-pupil" :style="pupilStyle" />
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

const props = withDefaults(
  defineProps<{
    size?: number
    maxDistance?: number
    color?: string
    mouseX: number
    mouseY: number
    forceX?: number
    forceY?: number
  }>(),
  {
    size: 12,
    maxDistance: 5,
    color: '#2d2d2d',
  },
)

const pupilEl = ref<HTMLElement | null>(null)

const position = computed(() => {
  if (props.forceX !== undefined && props.forceY !== undefined) {
    return { x: props.forceX, y: props.forceY }
  }

  const pupil = pupilEl.value
  if (!pupil) return { x: 0, y: 0 }

  const rect = pupil.getBoundingClientRect()
  const centerX = rect.left + rect.width / 2
  const centerY = rect.top + rect.height / 2
  const deltaX = props.mouseX - centerX
  const deltaY = props.mouseY - centerY
  const distance = Math.min(Math.hypot(deltaX, deltaY), props.maxDistance)
  const angle = Math.atan2(deltaY, deltaX)

  return {
    x: Math.cos(angle) * distance,
    y: Math.sin(angle) * distance,
  }
})

const pupilStyle = computed(() => ({
  width: `${props.size}px`,
  height: `${props.size}px`,
  backgroundColor: props.color,
  transform: `translate(${position.value.x}px, ${position.value.y}px)`,
}))
</script>

<style scoped>
.tracking-pupil {
  display: block;
  flex-shrink: 0;
  border-radius: 50%;
  transition: transform 100ms ease-out;
}
</style>
