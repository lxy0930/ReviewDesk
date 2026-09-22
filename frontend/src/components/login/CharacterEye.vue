<template>
  <span
    class="character-eye"
    :class="{ 'character-eye--blinking': isBlinking }"
    :style="eyeStyle"
  >
    <TrackingPupil
      v-if="!isBlinking"
      :size="pupilSize"
      :max-distance="maxDistance"
      :color="pupilColor"
      :mouse-x="mouseX"
      :mouse-y="mouseY"
      :force-x="forceX"
      :force-y="forceY"
    />
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import TrackingPupil from './TrackingPupil.vue'

const props = withDefaults(
  defineProps<{
    size?: number
    pupilSize?: number
    maxDistance?: number
    eyeColor?: string
    pupilColor?: string
    isBlinking?: boolean
    mouseX: number
    mouseY: number
    forceX?: number
    forceY?: number
  }>(),
  {
    size: 18,
    pupilSize: 7,
    maxDistance: 5,
    eyeColor: '#fff',
    pupilColor: '#2d2d2d',
    isBlinking: false,
  },
)

const eyeStyle = computed(() => ({
  width: `${props.size}px`,
  height: props.isBlinking ? '2px' : `${props.size}px`,
  backgroundColor: props.eyeColor,
}))
</script>

<style scoped>
.character-eye {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  flex-shrink: 0;
  border-radius: 50%;
  transition:
    width 150ms ease,
    height 150ms ease,
    background-color 150ms ease;
}
</style>
