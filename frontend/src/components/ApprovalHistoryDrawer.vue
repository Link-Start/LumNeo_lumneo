<template>
  <n-drawer
    v-model:show="show"
    placement="bottom"
    :height="height"
    closable
    :style="{ maxHeight: '90vh' }"
  >
    <n-drawer-content title="审批操作记录">
      <n-spin :show="loading">
        <div v-if="records.length === 0" class="empty-state">
          暂无审批记录
        </div>
        <n-list v-else>
          <n-list-item v-for="item in records" :key="item.id">
            <template #prefix>
              <n-tag :type="getStatusType(item.status)" size="small">
                {{ getStatusLabel(item.status) }}
              </n-tag>
            </template>
            <div class="record-item">
              <div class="record-meta">
                <span class="record-time">{{ formatTime(item.created_at) }}</span>
                <span class="record-turn">轮次 {{ item.turn_index }}</span>
              </div>
              <div class="record-message" v-html="formatMessage(item.message)"></div>
            </div>
          </n-list-item>
        </n-list>
      </n-spin>
    </n-drawer-content>
  </n-drawer>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { NDrawer, NDrawerContent, NList, NListItem, NTag, NSpin } from 'naive-ui'

const props = defineProps<{
  show: boolean
  chatId: string
  height?: string
}>()

const emit = defineEmits(['update:show'])

const loading = ref(false)
const records = ref<any[]>([])

const show = computed({
  get: () => props.show,
  set: (val) => emit('update:show', val),
})

const height = computed(() => props.height || '70vh')

watch(() => props.show, (val) => {
  if (val && props.chatId) {
    fetchRecords()
  }
})

async function fetchRecords() {
  if (!props.chatId) return
  loading.value = true
  try {
    const res = await fetch(`/api/decisions?chat_id=${props.chatId}`)
    if (!res.ok) throw new Error('加载失败')
    const data = await res.json()
    records.value = data
  } catch (e) {
    console.error('获取审批记录失败', e)
  } finally {
    loading.value = false
  }
}

function getStatusType(status: string): any {
  const map: Record<string, string> = {
    pending: 'warning',
    continue: 'success',
    stop: 'error',
  }
  return map[status] || 'default'
}

function getStatusLabel(status: string) {
  const map: Record<string, string> = {
    pending: '待处理',
    continue: '已通过',
    stop: '已拒绝',
  }
  return map[status] || status
}

function formatTime(timestamp: string) {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  return date.toLocaleString('zh-CN', { hour12: false })
}

function formatMessage(message: string) {
  if (!message) return '无详情'
  try {
    const obj = JSON.parse(message)
    let parts = []
    if (obj.tool_name) parts.push(`工具: ${obj.tool_name}`)
    if (obj.reason) parts.push(`原因: ${obj.reason}`)
    if (obj.suggestion) parts.push(`建议: ${obj.suggestion}`)
    if (obj.total_attempts) parts.push(`尝试: ${obj.total_attempts} 次`)
    if (parts.length) return parts.join('<br>')
    return JSON.stringify(obj, null, 2)
  } catch {
    return message
  }
}
</script>

<style scoped>
.empty-state {
  text-align: center;
  color: var(--text-secondary);
  padding: 40px 0;
}
.record-item {
  width: 100%;
}
.record-meta {
  display: flex;
  gap: 12px;
  font-size: 0.85rem;
  color: var(--text-secondary);
  margin-bottom: 4px;
}
.record-message {
  font-size: 0.95rem;
  line-height: 1.5;
}
</style>