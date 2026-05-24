<template>
    <svg :class="svgClass" aria-hidden="true" :width="fontSize" :height="fontSize">
        <use class="svg-use" :href="symbolId" />
    </svg>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

const props = defineProps<{name: string, className?: string, size?: number | string}>()

const fontSize = ref(props.size || 16)
const svgClass = computed(() => {
    if (props.className) {
        return `svg-iocn ${props.className}`
    }
    return 'svg-icon'
})
const symbolId = computed(() => {
    return `#${props.name}`
})
</script>

<style scoped>
.svg-icon {fill:currentColor; overflow:hidden;}
</style>