<template>
  <div class="thinking-group" :class="{ 'expanded': isExpanded }">
    <div class="thinking-summary no-select" @click="toggle">
      <span class="summary-icon"><m-svg name="think" :size="20"/></span>
      <span class="summary-text">{{ summaryText }}</span>
      <span class="summary-tags">
        <span class="tag reasoning-tag" v-if="reasoningCount > 0">思考 ×{{ reasoningCount }}</span>
        <span class="tag tool-tag" v-if="toolCount > 0">工具 ×{{ toolCount }}</span>
      </span>
      <span class="summary-arrow">
        <m-svg name="chevron-right" :size="18" />
      </span>
    </div>

    <!-- 内容区域：grid + 渐变遮罩 -->
    <div class="thinking-body-wrapper">
      <div class="thinking-body-container">
        <div class="thinking-body-inner">
          <div class="thinking-body-content">
            <template v-for="(node, idx) in steps" :key="idx">
              <ReasoningNode
                v-if="node.type === 'reasoning'"
                :node="{
                  type: 'reasoning',
                  content: node.content || '',
                  attrs: [['time', String(node.time || 0)]]
                }"
                :custom-id="customId"
                :is-dark="isDark"
              />
              <ToolCallsNode
                v-else-if="node.type === 'toolcalls'"
                :node="{
                  type: 'toolcalls',
                  content: JSON.stringify({ tools: node.tools, count: node.count, loading: node.loading }),
                  loading: node.loading
                }"
                :custom-id="customId"
                :is-dark="isDark"
              />
            </template>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import ReasoningNode from '@/components/CustomNodes/ReasoningNode.vue'
import ToolCallsNode from '@/components/CustomNodes/ToolCallsNode.vue'
import MSvg from '@/components/MSvg.vue'

const props = defineProps<{
  items: string
  customId?: string
  isDark?: boolean
}>()

const isExpanded = ref(false)

const steps = computed(() => {
  try {
    const json = decodeURIComponent(escape(atob(props.items)))
    return JSON.parse(json)
  } catch (e) {
    console.error('ThinkingGroup 解码失败', e)
    return []
  }
})

const reasoningCount = computed(() => {
  return steps.value.filter((s: any) => s.type === 'reasoning').length
})

const toolCount = computed(() => {
  let count = 0
  for (const step of steps.value) {
    if (step.type === 'toolcalls' && step.tools) {
      count += step.tools.length
    }
  }
  return count
})

const summaryText = computed(() => {
  const rCount = reasoningCount.value
  const tCount = toolCount.value
  if (rCount > 0 && tCount === 0) return '深度思考'
  if (rCount === 0 && tCount > 0) return `调用 ${tCount} 个工具`
  if (rCount > 0 && tCount > 0) return '思考与行动'
  return '思考过程'
})

function toggle() {
  isExpanded.value = !isExpanded.value
}
</script>

<style scoped>
.thinking-group {
  margin: 12px 0;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  overflow: hidden;
  transition: box-shadow 0.2s;
}
.thinking-group.expanded {
  box-shadow: 0 2px 8px rgba(99, 102, 241, 0.08);
}

/* ========== 头部摘要 ========== */
.thinking-summary {
  cursor: pointer;
  padding: 12px 16px;
  font-weight: 500;
  user-select: none;
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  gap: 8px;
  transition: background 0.2s;
  position: relative;
  z-index: 2;
}


.summary-icon {
  display: flex;
  align-items: center;
  color: var(--text-primary);
}
.summary-text {
  font-weight: 600;
  color: var(--text-primary);
  flex: 1;
  font-size: 16px;
}

/* 标签 */
.summary-tags {
  display: flex;
  gap: 6px;
  align-items: center;
}
.tag {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 500;
  white-space: nowrap;
}
.reasoning-tag {
  background: rgba(139, 92, 246, 0.12);
  color: #8b5cf6;
}
.tool-tag {
  background: rgba(59, 130, 246, 0.12);
  color: #3b82f6;
}

/* 箭头旋转动画 */
.summary-arrow {
  display: flex;
  align-items: center;
  color: var(--text-secondary);
  transition: transform 0.3s ease;
}
.thinking-group.expanded .summary-arrow {
  transform: rotate(90deg);
}

/* ========== 内容容器 ========== */
.thinking-body-wrapper {
  position: relative;
}

/* grid 折叠容器 */
.thinking-body-container {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows 0.35s ease;
  overflow: hidden;
  width: 100%;
}
.thinking-group.expanded .thinking-body-container {
  grid-template-rows: 1fr;
}

.thinking-body-inner {
  min-height: 0;
  min-width: 0;
  width: 100%;
  overflow: hidden;
}

.thinking-body-content {
  padding: 0 12px 12px;
}
</style>