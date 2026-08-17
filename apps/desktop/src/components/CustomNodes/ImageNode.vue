<template>
   <n-image
    lazy
    width="100%"
    class="image-node"
    :src="node.src"
    :alt="node.alt"
    :render-toolbar="renderToolbar"
  />
</template>

<script setup lang="ts">
import { h } from 'vue'
import { NIcon, NImage } from 'naive-ui'
import type { ImageRenderToolbarProps } from 'naive-ui'
import { DownloadOutline } from '@vicons/ionicons5'

const props = defineProps<{
  node: {
    type: 'image'
    src?: string
    title?: string
    loading?: boolean
    alt?: string
  }
}>()

function renderToolbar({ nodes }: ImageRenderToolbarProps) {
  return [
    nodes.rotateCounterclockwise,
    nodes.rotateClockwise,
    nodes.resizeToOriginalSize,
    nodes.zoomIn,
    nodes.zoomOut,
    h(NIcon, {
      size: 24,
      onClick: async () => {
        const url = props.node.src
        if (!url) return
        const fullUrl = url.startsWith('/') ? window.location.origin + url : url
        const suffix = fullUrl.split('.').pop()?.split('?')[0]
        const fileName = `download.${suffix}`
        if (window.pywebview?.api?.download_file) {
          await window.pywebview.api.download_file(fullUrl, fileName)
        } else {
          const a = document.createElement('a')
          a.href = fullUrl
          a.download = fileName
          a.click()
        }
      },
      style: {
        cursor: 'pointer',
        padding: '4px',
        borderRadius: '4px',
      },
    }, {
      default: () => h(DownloadOutline)
    }),
    nodes.close
  ]
}

</script>

<style scoped>
.image-node {
  display: flex;
  margin: 0 auto;
  max-width: 620px;
  border-radius: 8px;
  cursor: pointer;
}
</style>
