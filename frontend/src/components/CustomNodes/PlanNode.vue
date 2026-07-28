<template>
  <div class="plan-blueprint">
    <!-- 头部 -->
    <div class="plan-header">
      <div class="plan-header-left">
        <span class="plan-icon">📋</span>
        <span class="plan-title">执行计划</span>
        <n-tag v-if="!editing && planData.length > 0" size="small" type="info">
          {{ getFilteredSteps(planData).length }} 个步骤
        </n-tag>
      </div>
      <div class="plan-header-right">
        <n-button v-if="!editing" size="small" quaternary @click="startEditing" title="编辑计划">
          <template #icon><n-icon><CreateOutline /></n-icon></template>
          编辑
        </n-button>
        <n-button v-else size="small" quaternary @click="cancelEditing" title="取消编辑">
          取消编辑
        </n-button>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-if="planData.length === 0" class="plan-empty">
      执行计划正在创建，请稍等...
    </div>

    <!-- 步骤列表（编辑模式 + 拖拽） 使用 v-show 确保 DOM 始终存在 -->
    <div v-show="editing && planData.length > 0" class="plan-list" ref="draggableRef">
      <div
        v-for="(step, index) in editablePlan"
        :key="step.uuid"
        class="plan-step"
        :class="{
          'step-disabled': step.disabled,
          'step-dragging': draggingIndex === index,
        }"
      >
        <!-- 拖拽手柄 -->
        <span class="drag-handle" title="拖拽调整顺序">
          <n-icon :size="14"><Move /></n-icon>
        </span>

        <!-- 步骤序号 -->
        <span class="step-index">{{ index + 1 }}</span>

        <!-- 描述（可编辑） -->
        <n-input
          v-if="editingIndex === index"
          v-model:value="editablePlan[index].description"
          size="small"
          class="step-desc-input"
          @blur="finishEdit"
          @keyup.enter="finishEdit"
          @keyup.esc="cancelEdit"
          autofocus
        />
        <span
          v-else
          class="step-desc"
          @dblclick="startEdit(index)"
          :title="'双击编辑'"
        >
          {{ step.description || step.desc || '无描述' }}
        </span>

        <!-- 工具标签（可编辑） -->
        <n-select
          v-if="editingIndex === index"
          v-model:value="editablePlan[index].tool"
          :options="toolOptions"
          size="small"
          class="step-tool-select"
          placeholder="选择工具"
          @blur="finishEdit"
        />
        <n-tag
          v-else
          :bordered="false"
          :type="getToolType(step.tool)"
          size="small"
          class="step-tool"
          @dblclick="startEdit(index)"
        >
          {{ getToolDisplayName(step.tool) }}
        </n-tag>

        <!-- 上移/下移（保留备选） -->
        <n-button-group size="tiny" class="step-move">
          <n-button quaternary :disabled="index === 0" @click="moveStep(index, -1)">
            <template #icon><n-icon><ChevronUpOutline /></n-icon></template>
          </n-button>
          <n-button
            quaternary
            :disabled="index === editablePlan.length - 1"
            @click="moveStep(index, 1)"
          >
            <template #icon><n-icon><ChevronDownOutline /></n-icon></template>
          </n-button>
        </n-button-group>

        <!-- 禁用开关 -->
        <n-switch
          v-model:value="editablePlan[index].disabled"
          size="small"
          class="step-disable-switch"
          :title="step.disabled ? '已禁用，执行时将跳过' : '已启用'"
        />

        <!-- 删除按钮 -->
        <n-button
          size="tiny"
          quaternary
          type="error"
          class="step-delete"
          @click="removeStep(index)"
        >
          <template #icon><n-icon><CloseOutline /></n-icon></template>
        </n-button>
      </div>
    </div>

    <!-- 步骤列表（只读模式） -->
    <n-timeline v-if="!editing && planData.length > 0" class="plan-timeline">
      <n-timeline-item
        v-for="(step, index) in getFilteredSteps(planData)"
        :key="step.uuid"
        type="info"
      >
        <template #header>
          <span class="step-title">步骤 {{ index + 1 }}</span>
          <n-tag v-if="step.disabled" size="tiny" type="warning" :bordered="false">
            已禁用
          </n-tag>
          <n-tag
            v-if="step.status"
            size="tiny"
            :type="step.status === 'success' ? 'success' : step.status === 'error' ? 'error' : 'info'"
            :bordered="false"
          >
            {{ step.status }}
          </n-tag>
        </template>
        <template #default>
          <div class="step-detail">
            <span v-if="step.tool && step.tool !== 'none' && step.tool !== ''">
              调用
              <n-tag :bordered="false" type="info" size="small" style="margin:0 6px;">
                {{ getToolDisplayName(step.tool) }}
              </n-tag>
            </span>
            <span class="step-desc-text">{{ step.description || step.desc || '' }}</span>
            <span v-if="step.disabled" class="step-disabled-hint">（已禁用，将跳过）</span>
          </div>
        </template>
      </n-timeline-item>
    </n-timeline>

    <!-- 编辑模式：添加步骤 -->
    <div v-if="editing" class="plan-add-step">
      <n-button size="small" quaternary @click="addStep">
        <template #icon><n-icon><AddOutline /></n-icon></template>
        添加步骤
      </n-button>
    </div>

    <!-- 底部操作按钮 -->
    <div class="plan-footer">
      <div v-if="editing" class="plan-footer-left">
        <n-checkbox v-model:checked="showDisabled" size="small">
          显示已禁用步骤
        </n-checkbox>
        <n-button size="small" quaternary @click="resetPlan">
          重置为原始计划
        </n-button>
      </div>
      <div class="plan-footer-right">
        <n-button
          v-if="editing"
          size="small"
          type="primary"
          :disabled="!hasValidSteps"
          @click="confirmEdit"
        >
          确认修改
        </n-button>
        <n-button
          size="small"
          type="success"
          :disabled="!hasExecutableSteps"
          @click="handleExecute"
        >
          <template #icon><n-icon><PlayOutline /></n-icon></template>
          {{ editing ? '确认并执行' : '执行计划' }}
        </n-button>
        <n-button v-if="editing" size="small" @click="cancelEditing">取消</n-button>
      </div>
    </div>

    <!-- 新增步骤弹窗 -->
    <n-modal v-model:show="showAddModal" :mask-closable="false" preset="dialog" title="添加步骤">
      <n-form :model="newStepForm" label-placement="left" label-width="80px">
        <n-form-item label="描述" required>
          <n-input v-model:value="newStepForm.description" placeholder="请输入步骤描述" />
        </n-form-item>
        <n-form-item label="工具">
          <n-select
            v-model:value="newStepForm.tool"
            :options="toolOptions"
            placeholder="选择工具（可选）"
            clearable
          />
        </n-form-item>
      </n-form>
      <template #action>
        <n-button @click="showAddModal = false">取消</n-button>
        <n-button type="primary" :disabled="!newStepForm.description.trim()" @click="confirmAddStep">
          添加
        </n-button>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, inject } from 'vue'
import { NTimeline, NTimelineItem, NTag, NButton, NInput, NSelect, NSwitch, 
  NIcon, NModal, NForm, NFormItem, NCheckbox, useMessage, NButtonGroup } from 'naive-ui'
import { CreateOutline, CloseOutline, AddOutline, PlayOutline, ChevronUpOutline, ChevronDownOutline, Move } from '@vicons/ionicons5'
import { useDraggable } from 'vue-draggable-plus'
import { useToolStore } from '@/stores/tools'
import { useProfileStore } from '@/stores/profiles'
import { useChat } from '@/composables/useChat'

const props = defineProps<{
  node: {
    type: 'plan'
    content?: string
    attrs?: Record<string, any>
  }
  customId?: string
  isDark?: boolean
}>()

const profileStore = useProfileStore()
const toolStore = useToolStore()
const message = useMessage()
const { sendTextMessage } = useChat()
const scrollToBottom = inject<() => void>('scrollToBottom', () => {})

// ---------- 状态 ----------
const editing = ref(false)
const editingIndex = ref<number | null>(null)
const showAddModal = ref(false)
const showDisabled = ref(true)
const originalPlan = ref<any[]>([])
const draggingIndex = ref<number | null>(null)

const newStepForm = ref({
  description: '',
  tool: '',
})

// ---------- 拖拽容器 ref ----------
const draggableRef = ref<HTMLElement>()

// ---------- 工具选项 ----------
const toolOptions = computed(() => {
  const tools = toolStore.defaultTools.concat(
    profileStore.activeProfile?.tools ?? []
  )
  return tools.map((name) => {
    return {
      label: toolStore.toolsInfo[name]?.title || name,
      value: name,
    }
  })
})

const generateId = () => `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`

// ---------- 计划数据 ----------
const rawPlan = computed(() => {
  const raw = props.node.content || '[]'
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
})

const planData = ref<any[]>([])
const editablePlan = ref<any[]>([])

watch(
  rawPlan,
  (newPlan) => {
    const normalized = newPlan.map((step: any, index: number) => {
      const uid = step.uuid || step._id || generateId()
        return {
        step_id: step.step_id || index + 1,
        description: step.description || step.desc || '',
        tool: step.tool || '',
        disabled: step.disabled || false,
        status: step.status || '',
        uuid: uid,
        ...step,
      }
    })
    planData.value = normalized
    originalPlan.value = JSON.parse(JSON.stringify(normalized))
    if (!editing.value) {
      editablePlan.value = JSON.parse(JSON.stringify(normalized))
    }
  },
  { immediate: true, deep: true }
)

// ---------- 初始化拖拽 ----------
useDraggable(draggableRef, editablePlan, {
  animation: 200,
  handle: '.drag-handle',
  ghostClass: 'step-ghost',
  chosenClass: 'step-chosen',
  dragClass: 'step-drag-class',
  group: 'plan-steps',
  // 只允许通过手柄拖拽，避免 input/select/switch 误触
  filter: '.step-desc-input, .step-tool-select, .n-input, .n-select, .n-switch, .n-button',
  preventOnFilter: false,
  onStart: () => {
    // 拖拽开始
  },
  onEnd: () => {
    draggingIndex.value = null
    // vue-draggable-plus 已自动同步数组顺序，这里只需重新编号
    renumberSteps()
  },
})

function renumberSteps() {
  editablePlan.value.forEach((step: any, i: number) => {
    step.step_id = i + 1
  })
}

// ---------- 计算属性 ----------
const hasValidSteps = computed(() => {
  return editablePlan.value.some((step: any) => step.description?.trim())
})

const hasExecutableSteps = computed(() => {
  return planData.value.some((step: any) => !step.disabled && step.description?.trim())
})

function getFilteredSteps(steps: any[]) {
  if (showDisabled.value) {
    return steps
  } else {
    return steps.filter(step => !step.disabled)
  }
}

// ---------- 工具函数 ----------
function getToolDisplayName(toolName: string): string {
  if (!toolName || toolName === 'none') return '无工具'
  return toolStore.toolsInfo[toolName]?.title || toolName
}

function getToolType(toolName: string): 'default' | 'info' {
  if (!toolName || toolName === 'none') return 'default'
  return 'info'
}

// ---------- 编辑操作 ----------
function startEditing() {
  editing.value = true
  editablePlan.value = JSON.parse(JSON.stringify(planData.value))
}

function cancelEditing() {
  editing.value = false
  editingIndex.value = null
  editablePlan.value = JSON.parse(JSON.stringify(planData.value))
}

function startEdit(index: number) {
  editingIndex.value = index
}

function finishEdit() {
  editingIndex.value = null
}

function cancelEdit() {
  editingIndex.value = null
}

function moveStep(index: number, direction: number) {
  const target = index + direction
  if (target < 0 || target >= editablePlan.value.length) return
  const [removed] = editablePlan.value.splice(index, 1)
  editablePlan.value.splice(target, 0, removed)
  renumberSteps()
}

function removeStep(index: number) {
  editablePlan.value.splice(index, 1)
  renumberSteps()
  message.success('步骤已删除')
}

function addStep() {
  newStepForm.value = { description: '', tool: '' }
  showAddModal.value = true
}

function confirmAddStep() {
  if (!newStepForm.value.description.trim()) {
    message.warning('请输入步骤描述')
    return
  }
  editablePlan.value.push({
    step_id: editablePlan.value.length + 1,
    description: newStepForm.value.description.trim(),
    tool: newStepForm.value.tool || '',
    disabled: false,
  })
  showAddModal.value = false
  message.success('步骤已添加')
}

function resetPlan() {
  editablePlan.value = JSON.parse(JSON.stringify(originalPlan.value))
  message.success('已重置为原始计划')
}

function confirmEdit() {
  console.log();
  
  planData.value = JSON.parse(JSON.stringify(editablePlan.value))
  editing.value = false
  editingIndex.value = null
  message.success('计划已更新')
}

// 添加格式化计划文本的函数
function formatPlan(steps: any[]): string {
  const lines = steps
    .filter(step => !step.disabled)
    .map((step, index) => {
      const desc = step.description || step.desc || '无描述'
      const tool = step.tool ? ` (工具: ${step.tool})` : ''
      return `${index + 1}. ${desc}${tool}`
    })
  return `按照以下计划执行：\n${lines.join('\n')}`
}

function handleExecute() {
  // 如果处于编辑模式，先应用编辑
  if (editing.value) {
    planData.value = JSON.parse(JSON.stringify(editablePlan.value))
    editing.value = false
    editingIndex.value = null
  }

  const executable = planData.value.filter((step: any) => !step.disabled)
  if (executable.length === 0) {
    message.warning('没有可执行的步骤')
    return
  }

  // 构造消息文本并发送
  const planText = formatPlan(planData.value)
  sendTextMessage(planText, [], scrollToBottom)
}

defineExpose({
  getPlan: () => planData.value,
  getRawPlan: rawPlan,
})
</script>

<style scoped>
.plan-blueprint {
  margin: 12px 0;
  padding: 16px 20px;
  background: var(--bg-secondary, #f5f7fa);
  border-radius: 10px;
  border: 1px solid var(--border-color, #e8ecf0);
}
.plan-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
}
.plan-header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}
.plan-header-right {
  display: flex;
  align-items: center;
  gap: 6px;
}
.plan-icon { font-size: 20px; }
.plan-title { font-weight: 600; font-size: 15px; }
.plan-empty { text-align: center; color: var(--text-secondary, #999); padding: 20px 0; }

.plan-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 12px;
}
.plan-step {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  background: var(--bg-primary, #fff);
  border-radius: 6px;
  border: 1px solid var(--border-color, #e8ecf0);
  transition: all 0.15s;
  user-select: none;
}
.plan-step:hover {
  border-color: var(--primary-color, #409eff);
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
.plan-step.step-disabled {
  opacity: 0.55;
  background: var(--bg-disabled, #f5f5f5);
}
/* 拖拽手柄 */
.drag-handle {
  cursor: grab;
  color: var(--text-secondary, #999);
  display: flex;
  align-items: center;
  padding: 2px;
  flex-shrink: 0;
  transition: color 0.15s;
}
.drag-handle:hover {
  color: var(--primary-color, #409eff);
}
.drag-handle:active {
  cursor: grabbing;
}

/* vue-draggable-plus 加在 DOM 上的 class（scoped 中需要 :deep 才能命中） */
:deep(.step-ghost) {
  opacity: 0.4;
  background: var(--bg-hover, #f0f2f5);
}
:deep(.step-chosen) {
  box-shadow: 0 4px 14px rgba(64, 158, 255, 0.25);
  border-color: var(--primary-color, #409eff);
}

.step-index {
  font-weight: 600;
  font-size: 13px;
  color: var(--text-secondary, #666);
  min-width: 24px;
  text-align: center;
}
.step-desc {
  flex: 1;
  font-size: 14px;
  color: var(--text-primary, #333);
  padding: 2px 6px;
  border-radius: 4px;
  cursor: text;
  min-height: 28px;
  display: flex;
  align-items: center;
}
.step-desc:hover {
  background: var(--bg-hover, #f0f2f5);
}
.step-desc-input {
  flex: 1;
  min-width: 120px;
}
.step-tool {
  flex-shrink: 0;
  cursor: pointer;
}
.step-tool:hover { opacity: 0.8; }
.step-tool-select {
  width: 140px;
  flex-shrink: 0;
}
.step-move {
  flex-shrink: 0;
}
.step-disable-switch {
  flex-shrink: 0;
}
.step-delete {
  flex-shrink: 0;
  opacity: 0.4;
  transition: opacity 0.15s;
}
.step-delete:hover { opacity: 1; }

.plan-timeline {
  margin-bottom: 12px;
}
.step-detail {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 2px;
}
.step-desc-text {
  color: var(--text-secondary, #666);
  font-size: 0.95em;
}
.step-disabled-hint {
  color: var(--warning-color, #e6a23c);
  font-size: 0.85em;
  margin-left: 6px;
}

.plan-add-step {
  padding: 8px 0 4px 0;
  border-top: 1px dashed var(--border-color, #e8ecf0);
}
.plan-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid var(--border-color, #e8ecf0);
}
.plan-footer-left {
  display: flex;
  align-items: center;
  gap: 16px;
}
.plan-footer-right {
  display: flex;
  align-items: center;
  gap: 8px;
}
</style>
