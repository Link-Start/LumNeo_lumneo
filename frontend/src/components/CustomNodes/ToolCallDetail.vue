<template>
  <n-modal
    v-model:show="show"
    preset="card"
    :title="title"
    style="width: 800px; max-width: 90vw"
    :segmented="{ content: 'soft' }"
  >
    <n-spin :show="loading">
      <div v-if="data" class="tool-detail-content">
        <!-- 工具名称 -->
        <div class="detail-section">
          <div class="section-label">工具名称</div>
          <div class="tool-name-display">{{ data.tool_name }}</div>
        </div>

        <!-- 工具描述 -->
        <div class="detail-section">
          <div class="section-label">工具描述</div>
          <div class="tool-description">
            {{ toolStore.toolsInfo[data.tool_name]?.description || '无' }}
          </div>
        </div>
        <!-- 状态 -->
        <div class="detail-section">
          <div class="section-label">执行状态</div>
          <n-tag :type="statusType" :bordered="false">
            {{ statusText }}
          </n-tag>
          <span v-if="data.execution_time" class="exec-time">
            耗时 {{ formatDuration(data.execution_time) }}
          </span>
        </div>

        <!-- 参数 -->
        <div class="detail-section">
          <div class="section-label">调用参数</div>
          <div class="code-block-wrapper">
            <n-button class="copy-btn" size="small" @click="handleCopy(argsJson)">
              <template #icon>
                <m-svg :name="copied ? 'succ' : 'copy'" />
              </template>
              复制
            </n-button>
            <pre class="code-block"><code>{{ argsJson }}</code></pre>
          </div>
        </div>

        <!-- 结果 -->
        <div v-if="data.result" class="detail-section">
          <div class="section-label">执行结果</div>
          <div class="code-block-wrapper">
            <n-button class="copy-btn" size="small" @click="handleCopy(resultJson)">
              <template #icon>
                <m-svg :name="copied ? 'succ' : 'copy'" />
              </template>
              复制
            </n-button>
            <pre class="code-block result"><code>{{ resultJson }}</code></pre>
          </div>
        </div>

        <!-- 错误信息 -->
        <div v-if="data.error_message" class="detail-section">
          <div class="section-label">错误信息</div>
          <div class="error-message">{{ data.error_message }}</div>
        </div>
      </div>
      
      <div v-else-if="!loading" class="empty-state">
        未找到工具调用记录
      </div>
    </n-spin>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { NModal, NTag, NButton, NSpin } from 'naive-ui'
import MSvg from '@/components/MSvg.vue'
import { formatDuration, copyToClipboard } from '@/utils/common'
import { useToolStore } from '@/stores/tools'

const props = defineProps<{
  callId: string
  visible: boolean
}>()

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void
}>()

const toolStore = useToolStore()

const show = computed({
  get: () => props.visible,
  set: (val) => emit('update:visible', val)
})

const data = ref<any>(null)
const loading = ref(false)
const copied = ref(false)

const title = computed(() => {
  return data.value ? `${toolStore.toolsInfo[data.value.tool_name]?.title || data.value.tool_name} - 详情` : '工具调用详情'
})

const statusType = computed(() => {
  if (!data.value) return 'default'
  switch (data.value.status) {
    case 'success': return 'success'
    case 'error': return 'error'
    case 'calling': return 'warning'
    default: return 'default'
  }
})

const statusText = computed(() => {
  if (!data.value) return '未知'
  const map: Record<string, string> = {
    success: '执行成功',
    error: '执行失败',
    calling: '执行中...'
  }
  return map[data.value.status] || data.value.status
})

const argsJson = computed(() => {
  if (!data.value?.arguments) return '{}'
  try {
    if (typeof data.value.arguments === 'string') {
      return JSON.stringify(JSON.parse(data.value.arguments), null, 2)
    }
    return JSON.stringify(data.value.arguments, null, 2)
  } catch {
    return String(data.value.arguments)
  }
})

const resultJson = computed(() => {
  if (!data.value?.result) return ''
  try {
    const parsed = JSON.parse(data.value.result)
    return JSON.stringify(parsed, null, 2)
  } catch {
    return data.value.result
  }
})

async function loadDetail() {
  if (!props.callId) return
  loading.value = true
  data.value = null
  try {
    const res = await fetch(`/api/tool-calls/${props.callId}`)
    if (res.ok) {
      data.value = await res.json()
    }
  } catch (e) {
    console.error('Failed to load tool call detail:', e)
  } finally {
    loading.value = false
  }
}

watch(() => props.visible, (visible) => {
  if (visible && props.callId) {
    loadDetail()
  }
})

watch(() => props.callId, () => {
  if (show.value && props.callId) {
    loadDetail()
  }
})

function handleCopy(content: string) {
  copyToClipboard(content)
  copied.value = true
  setTimeout(() => copied.value = false, 800)
}
</script>

<style scoped>
.tool-detail-content {
  padding: 8px 0;
}

.detail-section {
  margin-bottom: 20px;
}
.tool-description {
    max-height: 80px;
    overflow: auto;
}

.section-label {
  font-weight: 600;
  font-size: 14px;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

.tool-name-display {
  font-size: 16px;
  font-weight: 600;
  color: var(--primary-color, #3b82f6);
}

.exec-time {
  margin-left: 12px;
  color: var(--text-secondary);
  font-size: 13px;
}

.code-block-wrapper {
  position: relative;
}

.code-block {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 12px;
  max-height: 280px;
  overflow: auto;
  font-family: 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
}

.code-block.result {
  color: var(--text-info, #26cf6d);
}

.code-block code {
  font-family: inherit;
}

.copy-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  opacity: 0;
  transition: opacity 0.2s;
}

.code-block-wrapper:hover .copy-btn {
  opacity: 1;
}

.error-message {
  background: rgba(255, 77, 79, 0.08);
  border: 1px solid rgba(255, 77, 79, 0.3);
  border-radius: 6px;
  padding: 12px;
  color: #ff4d4f;
  font-size: 13px;
  white-space: pre-wrap;
  word-break: break-all;
}

.empty-state {
  text-align: center;
  padding: 40px;
  color: var(--text-secondary);
}
</style>