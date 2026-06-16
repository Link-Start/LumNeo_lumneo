<template>
   <n-image
    lazy
    width="100%"
    show-toolbar-tooltip
    class="image-node"
    :src="node.src"
    :alt="node.alt"
  />
</template>

<script setup lang="ts">
import { NImage } from 'naive-ui'

const props = defineProps<{
  node: {
    type: 'image'
    src?: string
    title?: string
    loading?: boolean
    alt?: string
  }
}>()
</script>

<style scoped>
.image-node {
  max-width: 512px;
  border-radius: 8px;
  cursor: pointer;
}
</style>
