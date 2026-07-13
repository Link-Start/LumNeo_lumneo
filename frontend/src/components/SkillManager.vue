<template>
  <n-space vertical>
    <!-- 说明 -->
    <n-alert v-if="showTip" type="info" :bordered="false" closable @close="dismissTip">
      <template #header>
        技能源于角色历练的沉淀
      </template>
      <div style="font-size: 13px; line-height: 1.6">
        技能无法凭空创造，需通过角色的<b>“习得技能”</b>让角色领悟新能力。<br/>
        此处仅用于查看、编辑或遗忘已习得的技能。
      </div>
    </n-alert>

    <!-- 技能列表 -->
    <n-list hoverable clickable :show-divider="false" v-if="allSkillItems.length">
      <n-list-item v-for="skill in allSkillItems" :key="skill.id" style="background-color: rgba(125,125,125,.2);margin-bottom:4px;">
        <template #suffix>
          <n-space>
            <n-button text size="small" @click="openEditDialog(skill)">
              <template #icon><n-icon><create-outline /></n-icon></template>
              编辑
            </n-button>
            <n-popconfirm
              @positive-click="() => deleteSkill(skill.id)"
              negative-text="取消"
              positive-text="确定遗忘"
              :negative-button-props="{ size: 'tiny' }"
              :positive-button-props="{ size: 'tiny', type: 'error' }"
            >
              <template #trigger>
                <n-button text size="small" type="error">
                  <template #icon><n-icon><trash-outline /></n-icon></template>
                  遗忘
                </n-button>
              </template>
              <div style="max-width: 300px">
                <p style="margin-bottom: 8px">确定让所有角色遗忘技能「{{ skill.name }}」吗？</p>
                <p style="color: #999; font-size: 12px; margin: 0">
                  此操作将永久移除此技能，相关角色将失去该能力。
                </p>
              </div>
            </n-popconfirm>
          </n-space>
        </template>
        <div class="skill-item-content">
          <div class="skill-header">
            <n-text strong style="font-size:16px">{{ skill.name }}</n-text>
            <n-tag v-if="skill.isGlobal" size="small" type="success" :bordered="false" style="margin-left: 8px;">
              全角色可见
            </n-tag>
          </div>
          <n-text depth="3" style="font-size: 0.8rem">
            <n-ellipsis :line-clamp="2" :tooltip="{delay: 500}">
                {{ skill.description || '暂无描述' }}
            </n-ellipsis>
          </n-text>
          <div v-if="skill.usedByProfiles?.length" style="margin-top: 4px">
            <n-space :size="4" style="margin-top: 2px">
              <n-tag
                v-for="p in skill.usedByProfiles"
                :key="p.id"
                size="small"
                :bordered="false"
                type="info"
              >
                {{ p.name }}
              </n-tag>
            </n-space>
          </div>
        </div>
      </n-list-item>
    </n-list>

    <n-empty v-else description="尚无角色习得任何技能" style="padding: 24px 0">
      <template #extra>
        <n-text depth="3">前往功能设置 → 角色管理 → 习得技能，踏上修行之路</n-text>
      </template>
    </n-empty>
  </n-space>

  <!-- 编辑技能对话框 -->
  <n-modal
    v-model:show="showEditModal"
    preset="dialog"
    style="max-width: 520px; width: 96%"
    title="编辑技能"
    :mask-closable="false"
    positive-text="保存"
    negative-text="取消"
    @positive-click="saveEdit"
    @negative-click="showEditModal = false"
  >
    <n-form ref="formRef" :model="editForm" :rules="editRules" label-placement="left" label-width="90" size="large" style="margin-top: 20px">
      <n-form-item label="技能名称" path="name" required>
        <n-input v-model:value="editForm.name" placeholder="请输入技能名称" :maxlength="64" show-count />
      </n-form-item>
      <n-form-item label="技能描述" path="description">
        <n-input
          v-model:value="editForm.description"
          type="textarea"
          placeholder="以动词开头，写明做什么、何时触发。例如“提取PDF文本… 当用户提到PDF时使用”"
          :autosize="{ minRows: 3, maxRows: 6 }"
          :maxlength="320"
          show-count
        />
      </n-form-item>
      <n-form-item label="可见范围" path="isGlobal">
        <n-radio-group v-model:value="editForm.isGlobal">
          <n-space vertical>
            <n-radio :value="true">全角色可见</n-radio>
            <n-radio :value="false">仅已习得角色可见</n-radio>
          </n-space>
        </n-radio-group>
      </n-form-item>

      <n-divider v-if="editingSkill?.usedByProfiles?.length" style="margin: 12px 0">当前习得此技能的角色</n-divider>
      <n-space v-if="editingSkill?.usedByProfiles?.length" :size="4" style="margin-bottom: 12px">
        <n-tag v-for="p in editingSkill.usedByProfiles" :key="p.id" :bordered="false" type="info">
          {{ p.name }}
        </n-tag>
      </n-space>
    </n-form>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import {
  NList, NListItem, NButton, NSpace, NText, NTag, NPopconfirm, NEmpty, NModal,
  NForm, NFormItem, NInput, NRadioGroup, NRadio, NIcon, NDivider, NAlert, NEllipsis,
  useMessage
} from 'naive-ui'
import { CreateOutline, TrashOutline } from '@vicons/ionicons5'

interface ProfileInfo {
  id: number
  name: string
}

interface SkillItem {
  id: string
  name: string
  description: string
  isGlobal: boolean
  usedByProfiles?: ProfileInfo[]
}

const message = useMessage()
const formRef = ref()
const showTip = ref(true)

const editRules = {
  name: { required: true, message: '请输入技能名称', trigger: ['blur', 'input'] }
}

const allSkillItems = ref<SkillItem[]>([])
const showEditModal = ref(false)
const editingSkill = ref<SkillItem | null>(null)
const editForm = reactive({
  name: '',
  description: '',
  isGlobal: false
})

async function loadSkills() {
  try {
    const res = await fetch('/api/skills/list?include_profiles=true')
    const data = await res.json()
    allSkillItems.value = data.map((item: any) => ({
      id: item.id,
      name: item.name,
      description: item.description || '',   // 已经优先数据库字段
      isGlobal: item.is_global,
      usedByProfiles: item.used_by_profiles || []
    }))
  } catch (e) {
    message.error('加载技能列表失败')
  }
}

function openEditDialog(skill: SkillItem) {
  editingSkill.value = skill
  editForm.name = skill.name
  editForm.description = skill.description || ''
  editForm.isGlobal = skill.isGlobal
  showEditModal.value = true
}

async function saveEdit() {
  const valid = await formRef.value?.validate()
  if (!valid) return false

  const name = editForm.name.trim()
  if (!name) return false

  // 名称重复检查
  const dup = allSkillItems.value.some(s => s.id !== editingSkill.value?.id && s.name === name)
  if (dup) {
    message.warning('技能名称已存在')
    return false
  }

  try {
    const res = await fetch(`/api/skills/${editingSkill.value!.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: name,
        description: editForm.description,
        is_global: editForm.isGlobal
      })
    })
    if (res.ok) {
      message.success('技能更新成功')
      showEditModal.value = false
      await loadSkills()
      return true
    } else {
      const err = await res.json()
      message.error(err.detail || '更新失败')
      return false
    }
  } catch {
    message.error('网络错误')
    return false
  }
}

async function deleteSkill(skillId: string) {
  try {
    const res = await fetch(`/api/skills/${skillId}`, { method: 'DELETE' })
    if (res.ok) {
      message.success('技能已被遗忘')
      await loadSkills()
    } else {
      const err = await res.json()
      message.error(err.detail || '删除失败')
    }
  } catch {
    message.error('网络错误')
  }
}

onMounted(() => {
  // 检查是否已经关闭过提示
  const dismissed = localStorage.getItem('skill_tip_dismissed')
  if (dismissed === 'true') {
    showTip.value = false
  }
  loadSkills()
})

function dismissTip() {
  showTip.value = false
  localStorage.setItem('skill_tip_dismissed', 'true')
}
</script>

<style scoped>
.skill-item-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
  width: 100%;
}
.skill-header {
  display: flex;
  align-items: center;
}
:deep(.n-alert__content) {
  width: 100%;
}
</style>