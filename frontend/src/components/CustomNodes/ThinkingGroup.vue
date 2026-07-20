<!-- src/components/CustomNodes/ThinkingGroup.vue -->
<template>
  <details class="thinking-group" open>
    <summary class="thinking-summary">
      🧠 思考过程（{{ steps.length }} 步）
    </summary>
    <div class="thinking-body">
      <template v-for="(node, idx) in steps" :key="idx">
        <!-- 思考块 -->
        <reasoningNode
          v-if="node.type === 'reasoning'"
          :time="node.time"
          :content="node.content"
        />
        <!-- 合并后的工具调用 -->
        <ToolCallsNode
          v-else-if="node.type === 'toolcalls'"
          :tools="node.tools"
          :count="node.count"
          :loading="node.loading"
        />
      </template>
    </div>
  </details>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import ReasoningNode from '@/components/CustomNodes/ReasoningNode.vue'
import ToolCallsNode from '@/components/CustomNodes/ToolCallsNode.vue'

const props = defineProps<{ items: string }>()

const steps = computed(() => {
  try {
    // 安全解码 Base64 → JSON
    const json = decodeURIComponent(escape(atob(props.items)))
    return JSON.parse(json)
  } catch (e) {
    console.error('ThinkingGroup 解码失败', e)
    return []
  }
})
</script>

<style scoped>
.thinking-group {
  margin: 12px 0;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-card);
  overflow: hidden;
}
.thinking-summary {
  cursor: pointer;
  padding: 10px 14px;
  font-weight: 500;
  user-select: none;
  color: var(--text-secondary);
}
.thinking-body {
  padding: 0 14px 12px;
}
</style>