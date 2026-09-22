<template>
  <div ref="stageEl" class="animated-characters">
    <div class="character character--purple" :style="purpleStyle">
      <div class="eye-pair eye-pair--purple" :style="purpleEyePairStyle">
        <CharacterEye
          :size="18"
          :pupil-size="7"
          :max-distance="5"
          :is-blinking="isPurpleBlinking"
          :mouse-x="mouseX"
          :mouse-y="mouseY"
          :force-x="purpleForceX"
          :force-y="purpleForceY"
        />
        <CharacterEye
          :size="18"
          :pupil-size="7"
          :max-distance="5"
          :is-blinking="isPurpleBlinking"
          :mouse-x="mouseX"
          :mouse-y="mouseY"
          :force-x="purpleForceX"
          :force-y="purpleForceY"
        />
      </div>
    </div>

    <div class="character character--black" :style="blackStyle">
      <div class="eye-pair eye-pair--black" :style="blackEyePairStyle">
        <CharacterEye
          :size="16"
          :pupil-size="6"
          :max-distance="4"
          :is-blinking="isBlackBlinking"
          :mouse-x="mouseX"
          :mouse-y="mouseY"
          :force-x="blackForceX"
          :force-y="blackForceY"
        />
        <CharacterEye
          :size="16"
          :pupil-size="6"
          :max-distance="4"
          :is-blinking="isBlackBlinking"
          :mouse-x="mouseX"
          :mouse-y="mouseY"
          :force-x="blackForceX"
          :force-y="blackForceY"
        />
      </div>
    </div>

    <div class="character character--orange" :style="orangeStyle">
      <div class="pupil-pair pupil-pair--orange" :style="orangeEyePairStyle">
        <TrackingPupil
          :size="12"
          :max-distance="5"
          :mouse-x="mouseX"
          :mouse-y="mouseY"
          :force-x="simpleForceX"
          :force-y="simpleForceY"
        />
        <TrackingPupil
          :size="12"
          :max-distance="5"
          :mouse-x="mouseX"
          :mouse-y="mouseY"
          :force-x="simpleForceX"
          :force-y="simpleForceY"
        />
      </div>
    </div>

    <div class="character character--yellow" :style="yellowStyle">
      <div class="pupil-pair pupil-pair--yellow" :style="yellowEyePairStyle">
        <TrackingPupil
          :size="12"
          :max-distance="5"
          :mouse-x="mouseX"
          :mouse-y="mouseY"
          :force-x="simpleForceX"
          :force-y="simpleForceY"
        />
        <TrackingPupil
          :size="12"
          :max-distance="5"
          :mouse-x="mouseX"
          :mouse-y="mouseY"
          :force-x="simpleForceX"
          :force-y="simpleForceY"
        />
      </div>
      <span class="yellow-mouth" :style="yellowMouthStyle" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import CharacterEye from './CharacterEye.vue'
import TrackingPupil from './TrackingPupil.vue'

const props = withDefaults(
  defineProps<{
    isTyping?: boolean
    showPassword?: boolean
    passwordLength?: number
  }>(),
  {
    isTyping: false,
    showPassword: false,
    passwordLength: 0,
  },
)

const stageEl = ref<HTMLElement | null>(null)
const purpleEl = ref<HTMLElement | null>(null)
const blackEl = ref<HTMLElement | null>(null)
const orangeEl = ref<HTMLElement | null>(null)
const yellowEl = ref<HTMLElement | null>(null)

const mouseX = ref(0)
const mouseY = ref(0)
const isPurpleBlinking = ref(false)
const isBlackBlinking = ref(false)
const isLookingAtEachOther = ref(false)
const isPurplePeeking = ref(false)

const timers = new Set<number>()

function later(callback: () => void, delay: number) {
  const id = window.setTimeout(() => {
    timers.delete(id)
    callback()
  }, delay)
  timers.add(id)
  return id
}

function handleMouseMove(event: MouseEvent) {
  mouseX.value = event.clientX
  mouseY.value = event.clientY
}

function scheduleBlink(target: typeof isPurpleBlinking) {
  later(() => {
    target.value = true
    later(() => {
      target.value = false
      scheduleBlink(target)
    }, 150)
  }, Math.random() * 4000 + 3000)
}

function schedulePeek() {
  if (!props.showPassword || props.passwordLength <= 0) return
  later(() => {
    if (!props.showPassword || props.passwordLength <= 0) return
    isPurplePeeking.value = true
    later(() => {
      isPurplePeeking.value = false
      schedulePeek()
    }, 800)
  }, Math.random() * 3000 + 2000)
}

onMounted(() => {
  window.addEventListener('mousemove', handleMouseMove, { passive: true })
  scheduleBlink(isPurpleBlinking)
  scheduleBlink(isBlackBlinking)
})

onBeforeUnmount(() => {
  window.removeEventListener('mousemove', handleMouseMove)
  timers.forEach((timer) => window.clearTimeout(timer))
  timers.clear()
})

watch(
  () => props.isTyping,
  (typing) => {
    isLookingAtEachOther.value = typing
    if (typing) {
      later(() => {
        isLookingAtEachOther.value = false
      }, 800)
    }
  },
)

watch(
  () => [props.passwordLength, props.showPassword] as const,
  ([length, visible]) => {
    isPurplePeeking.value = false
    if (length > 0 && visible) schedulePeek()
  },
)

function calculatePosition(element: HTMLElement | null) {
  if (!element) return { faceX: 0, faceY: 0, bodySkew: 0 }

  const rect = element.getBoundingClientRect()
  const centerX = rect.left + rect.width / 2
  const centerY = rect.top + rect.height / 3
  const deltaX = mouseX.value - centerX
  const deltaY = mouseY.value - centerY

  return {
    faceX: Math.max(-15, Math.min(15, deltaX / 20)),
    faceY: Math.max(-10, Math.min(10, deltaY / 30)),
    bodySkew: Math.max(-6, Math.min(6, -deltaX / 120)),
  }
}

const purplePos = computed(() => calculatePosition(purpleEl.value))
const blackPos = computed(() => calculatePosition(blackEl.value))
const orangePos = computed(() => calculatePosition(orangeEl.value))
const yellowPos = computed(() => calculatePosition(yellowEl.value))

const isHidingPassword = computed(
  () => props.passwordLength > 0 && !props.showPassword,
)
const isPurpleLifted = computed(
  () => props.isTyping || isHidingPassword.value,
)

const purpleStyle = computed(() => ({
  height: isPurpleLifted.value ? '440px' : '400px',
  transform: props.passwordLength > 0 && props.showPassword
    ? 'skewX(0deg)'
    : isPurpleLifted.value
      ? `skewX(${purplePos.value.bodySkew - 12}deg) translateX(40px)`
      : `skewX(${purplePos.value.bodySkew}deg)`,
}))

const blackStyle = computed(() => ({
  transform: props.passwordLength > 0 && props.showPassword
    ? 'skewX(0deg)'
    : isLookingAtEachOther.value
      ? `skewX(${blackPos.value.bodySkew * 1.5 + 10}deg) translateX(20px)`
      : isPurpleLifted.value
        ? `skewX(${blackPos.value.bodySkew * 1.5}deg)`
        : `skewX(${blackPos.value.bodySkew}deg)`,
}))

const orangeStyle = computed(() => ({
  transform: props.passwordLength > 0 && props.showPassword
    ? 'skewX(0deg)'
    : `skewX(${orangePos.value.bodySkew}deg)`,
}))

const yellowStyle = computed(() => ({
  transform: props.passwordLength > 0 && props.showPassword
    ? 'skewX(0deg)'
    : `skewX(${yellowPos.value.bodySkew}deg)`,
}))

const purpleEyePairStyle = computed(() => ({
  left: props.passwordLength > 0 && props.showPassword
    ? '20px'
    : isLookingAtEachOther.value
      ? '55px'
      : `${45 + purplePos.value.faceX}px`,
  top: props.passwordLength > 0 && props.showPassword
    ? '35px'
    : isLookingAtEachOther.value
      ? '65px'
      : `${40 + purplePos.value.faceY}px`,
}))

const blackEyePairStyle = computed(() => ({
  left: props.passwordLength > 0 && props.showPassword
    ? '10px'
    : isLookingAtEachOther.value
      ? '32px'
      : `${26 + blackPos.value.faceX}px`,
  top: props.passwordLength > 0 && props.showPassword
    ? '28px'
    : isLookingAtEachOther.value
      ? '12px'
      : `${32 + blackPos.value.faceY}px`,
}))

const orangeEyePairStyle = computed(() => ({
  left: props.passwordLength > 0 && props.showPassword
    ? '50px'
    : `${82 + orangePos.value.faceX}px`,
  top: props.passwordLength > 0 && props.showPassword
    ? '85px'
    : `${90 + orangePos.value.faceY}px`,
}))

const yellowEyePairStyle = computed(() => ({
  left: props.passwordLength > 0 && props.showPassword
    ? '20px'
    : `${52 + yellowPos.value.faceX}px`,
  top: props.passwordLength > 0 && props.showPassword
    ? '35px'
    : `${40 + yellowPos.value.faceY}px`,
}))

const yellowMouthStyle = computed(() => ({
  left: props.passwordLength > 0 && props.showPassword
    ? '10px'
    : `${40 + yellowPos.value.faceX}px`,
  top: props.passwordLength > 0 && props.showPassword
    ? '88px'
    : `${88 + yellowPos.value.faceY}px`,
}))

const purpleForceX = computed(() => {
  if (props.passwordLength > 0 && props.showPassword) {
    return isPurplePeeking.value ? 4 : -4
  }
  return isLookingAtEachOther.value ? 3 : undefined
})

const purpleForceY = computed(() => {
  if (props.passwordLength > 0 && props.showPassword) {
    return isPurplePeeking.value ? 5 : -4
  }
  return isLookingAtEachOther.value ? 4 : undefined
})

const blackForceX = computed(() => {
  if (props.passwordLength > 0 && props.showPassword) return -4
  return isLookingAtEachOther.value ? 0 : undefined
})

const blackForceY = computed(() => {
  if (props.passwordLength > 0 && props.showPassword) return -4
  return isLookingAtEachOther.value ? -4 : undefined
})

const simpleForceX = computed(() =>
  props.passwordLength > 0 && props.showPassword ? -5 : undefined,
)
const simpleForceY = computed(() =>
  props.passwordLength > 0 && props.showPassword ? -4 : undefined,
)
</script>

<style scoped>
.animated-characters {
  position: relative;
  width: 550px;
  height: 400px;
  transform-origin: bottom center;
}

.character {
  position: absolute;
  bottom: 0;
  transform-origin: bottom center;
  transition:
    transform 700ms ease-in-out,
    height 700ms ease-in-out;
}

.character--purple {
  left: 70px;
  z-index: 1;
  width: 180px;
  background: #6c3ff5;
  border-radius: 10px 10px 0 0;
}

.character--black {
  left: 240px;
  z-index: 2;
  width: 120px;
  height: 310px;
  background: #2d2d2d;
  border-radius: 8px 8px 0 0;
}

.character--orange {
  left: 0;
  z-index: 3;
  width: 240px;
  height: 200px;
  background: #ff9b6b;
  border-radius: 120px 120px 0 0;
}

.character--yellow {
  left: 310px;
  z-index: 4;
  width: 140px;
  height: 230px;
  background: #e8d754;
  border-radius: 70px 70px 0 0;
}

.eye-pair,
.pupil-pair {
  position: absolute;
  display: flex;
  transition:
    left 700ms ease-in-out,
    top 700ms ease-in-out;
}

.eye-pair--purple {
  gap: 32px;
}

.eye-pair--black {
  gap: 24px;
}

.pupil-pair {
  gap: 32px;
  transition:
    left 200ms ease-out,
    top 200ms ease-out;
}

.pupil-pair--yellow {
  gap: 24px;
}

.yellow-mouth {
  position: absolute;
  width: 80px;
  height: 4px;
  border-radius: 999px;
  background: #2d2d2d;
  transition:
    left 200ms ease-out,
    top 200ms ease-out;
}

@media (max-width: 1280px) {
  .animated-characters {
    transform: scale(0.84);
  }
}

@media (max-width: 1050px) {
  .animated-characters {
    transform: scale(0.75);
  }
}

@media (prefers-reduced-motion: reduce) {
  .character,
  .eye-pair,
  .pupil-pair,
  .yellow-mouth {
    transition-duration: 0.01ms !important;
  }
}
</style>
