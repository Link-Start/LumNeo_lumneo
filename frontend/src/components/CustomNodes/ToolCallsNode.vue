<template>
  <div class="toolcalls-block" :class="{ 'streaming': isLoading, 'expanded': expanded }">
    <div class="toolcalls-summary no-select" @click="toggleExpand">
      <span v-if="!isLoading" class="summary-icon">
        <m-svg name="tools" :size="20"/>
      </span>
      <span v-else class="item-status status-calling">
        <m-svg name="spinner"/>
      </span>
      <span class="summary-text">{{ title }}</span>
      <span class="summary-count" v-if="toolsList.length > 0">
        {{ toolsList.length }}个
      </span>
    </div>
    
    <div class="toolcalls-container">
      <div class="toolcalls-inner">
        <div class="toolcalls-list">
          <div 
            v-for="(tool, index) in toolsList" 
            :key="tool.call_id"
            class="toolcall-item"
            @click.stop="openDetail(tool.call_id)"
          >
            <span class="item-status" :class="getStatusClass(tool)">
              <m-svg :name="getStatusIcon(tool)" :size="tool.status === 'error' ? 20 : 16"/>
            </span>
            <span class="item-name">{{ tool.name }} #{{ (index as number)+1 }}</span>
            <span class="item-arrow">
              <m-svg name="chevron-right" />
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>

  <ToolCallDetail
    v-model:visible="detailVisible"
    :call-id="selectedCallId"
  />
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import MSvg from '@/components/MSvg.vue'
import ToolCallDetail from './ToolCallDetail.vue'

defineOptions({
  inheritAttrs: false
})
const props = defineProps<{
  node: {
    type: 'toolcalls'
    content?: string
    loading?: boolean
    attrs?: Record<string, any>
  }
  customId?: string
  isDark?: boolean
}>()

const expanded = ref(false)
const detailVisible = ref(false)
const selectedCallId = ref('')

// 解析 props.node.content 获取 tool 列表
const parsedData = computed(() => {
  try {
    const content = props.node.content || '{}'
    return JSON.parse(content)
  } catch {
    return { tools: [], count: 0, loading: false }
  }
})

// 解析出的工具列表数据
const toolsList = computed(() => parsedData.value.tools || [])

const activeTools = computed(() => toolsList.value.filter((t: any) => t.streaming))

// 是否处于加载状态
const isLoading = computed(() => {
  // 只要列表中有工具状态为 streaming，就视为正在加载
  if (activeTools.value.length > 0) {
    return true
  }
  // 否则回退到外部传入或者解析出的 loading 状态
  return props.node.loading || parsedData.value.loading || false
})

// 标题动态显示
const title = computed(() => {
  // ✅ 新增兜底：如果正在 loading，但列表为空，说明参数还在生成中
  if (isLoading.value && toolsList.value.length === 0) {
    return '正在准备调用工具...'
  }

  if (isLoading.value) {
    // 1. 如果正在准备（还没有获取到工具名称）
    if (activeTools.value.length === 0) {
      return '正在准备调用工具...'
    }
    // 2. 如果只有一个工具正在调用，显示【工具名称】
    if (activeTools.value.length === 1) {
      return `正在调用【${activeTools.value[0].name}】...`
    }
    // 3. 如果有多个同时调用
    return `正在调用 ${activeTools.value.length} 个工具...`
  }
  
  // 4. 工具全部执行完毕后的状态
  return `已调用工具`
})


function toggleExpand() {
  expanded.value = !expanded.value
}

function openDetail(callId: string) {
  selectedCallId.value = callId
  detailVisible.value = true
}

// 根据工具状态渲染类名
function getStatusClass(tool: { call_id: string; name: string; streaming: boolean; status?: string }) {
  if (tool.streaming) return 'status-calling'
  if (tool.status === 'error') return 'status-error'
  return 'status-success'
}

// 根据工具状态渲染图标
function getStatusIcon(tool: { call_id: string; name: string; streaming: boolean, status?: string }) {
  if (tool.streaming) return 'spinner'
  if (tool.status === 'error') return 'error'
  return 'check'
}
</script>

<style scoped>
.toolcalls-block {
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-secondary);
  overflow: hidden;
  margin: 8px 0;
}

.toolcalls-block.streaming {
  border-left: 3px solid var(--primary-color, #1890ff);
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}

.toolcalls-block.expanded .toolcalls-summary {
  background: rgba(99, 102, 241, 0.1);
}

.toolcalls-summary {
  display: flex;
  align-items: center;
  padding: 12px 16px;
  cursor: pointer;
  user-select: none;
  gap: 10px;
  transition: background 0.2s;
}

.toolcalls-summary:hover {
  background: rgba(99, 102, 241, 0.05);
}

.toolcalls-summary::before {
  content: '';
  display: inline-block;
  width: 0;
  height: 0;
  /* 三角形大小 */
  border-top: 0.6em solid transparent;
  border-bottom: 0.6em solid transparent;
  border-left: 0.9em solid currentColor;   /* 使用当前文字颜色 */
  margin-right: 0.4em;
  transition: transform 0.3s ease;
  vertical-align: middle;
  position: relative;
}

.toolcalls-block.expanded .toolcalls-summary::before {
  transform: rotate(90deg);
}
.summary-icon {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  color: var(--text-primary);
}
.summary-text {
  font-weight: 600;
  color: var(--text-primary);
  flex: 1;
}

.summary-count {
  font-size: 13px;
  color: var(--text-secondary);
  background: var(--bg-tertiary);
  padding: 2px 8px;
  border-radius: 12px;
}

/* ---- 折叠容器 ---- */
.toolcalls-container {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows 0.3s ease;
  overflow: hidden;
}

.toolcalls-container > .toolcalls-inner {
  min-height: 0;
}

.toolcalls-block.expanded .toolcalls-container {
  grid-template-rows: 1fr;
}

/* ---- 列表样式（与原来一致） ---- */
.toolcalls-list {
  border-top: 1px solid var(--border-color);
  padding: 8px;
  display: flex;
  flex-wrap: wrap;      /* 换行 */
  gap: 8px;            /* 项间距 */
  align-items: center; /* 垂直居中 */
}

.toolcall-item {
  display: inline-flex;  /* 水平排列且宽度收缩 */
  align-items: center;
  padding: 8px 12px;     /* 适当内边距 */
  border-radius: 6px;
  cursor: pointer;
  gap: 8px;
  background: var(--bg-tool);
  transition: background 0.2s;
  white-space: nowrap; 
}

.toolcall-item:hover {
  background: rgba(99, 102, 241, 0.08);
}

.item-status {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
}

.item-status.status-success { color: #52c41a; }
.item-status.status-error { color: #ff4d4f; }
.item-status.status-calling { 
  color: var(--primary-color, #1890ff);
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.item-name {
  flex: 1;
  font-size: 14px;
  color: var(--text-primary);
}

.item-arrow {
  width: 16px;
  height: 16px;
  color: var(--text-secondary);
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  transition: transform 0.25s ease;
}

.toolcall-item:hover .item-arrow {
transform: translateX(4px);
}
</style>