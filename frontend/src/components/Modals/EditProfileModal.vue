<template>
<n-modal 
  :show="show"
  :auto-focus="false"
  preset="dialog" 
  draggable
  :mask-closable="false"
  style="max-width:520px;width:96%;" 
  :title="isEditing ? '编辑角色' : '新建角色'"
  positive-text="确认"
  negative-text="关闭"
  @update:show="negativeClick"
  @positive-click="saveProfile"
  @negative-click="negativeClick">
    <n-form :model="profileForm" label-placement="left" label-width="70">
      <n-form-item label="">
        <n-avatar
        style="margin-left:200px"
          round
          :size="60"
          src="https://07akioni.oss-cn-beijing.aliyuncs.com/07akioni.jpeg"
        />
      </n-form-item>
      <n-form-item label="角色名称">
        <n-input v-model:value="profileForm.name" placeholder="例如：程序员、生活助手" :maxlength="12" show-count/>
      </n-form-item>
      <n-form-item label="角色描述">
        <n-input
          v-model:value="profileForm.profile_prompt"
          type="textarea"
          placeholder="例如：你是一个专业的 Python 开发者，回答要简洁..."
          show-count
          :maxlength="300"
          :autosize="{ minRows: 3, maxRows: 8 }"
        />
      </n-form-item>
      <n-form-item label="赋予能力">
        <n-button size="small" style="position:absolute;left:-64px;top:40px;" @click="loadTools">刷新</n-button>
        <div style="width: 420px; max-height: 200px; overflow-y: auto;">
          <n-checkbox-group v-model:value="profileForm.tools">
            <n-space vertical>
              <n-checkbox v-for="tool in allTools" :key="tool.function.name" :value="tool.function.name">
                <n-popover trigger="hover" placement="right" :width="400">
                  <template #trigger>
                    <span style="cursor: pointer;">{{tool.function.title}} - {{ tool.function.name }}</span>
                  </template>
                  <div style="word-break: break-word; white-space: pre-wrap;">
                    {{ tool.function.description }}
                  </div>
                </n-popover>
              </n-checkbox>
            </n-space>
          </n-checkbox-group>
        </div>
        <p v-if="allTools.length === 0" style="color: gray;">暂无可用工具，请检查 MCP 服务或工具配置。</p>
      </n-form-item>
    </n-form>
    <n-collapse :default-expanded-names="[]">
      <n-collapse-item title="高级设置" name="params">
        <!-- Temperature -->
        <n-form-item label="温度" label-placement="left" label-width="100">
          <n-space align="center">
            <n-slider
              v-model:value="profileForm.temperature"
              :min="0"
              :max="2"
              :step="0.1"
              style="width: 200px"
            />
            <n-input-number
              v-model:value="profileForm.temperature"
              size="small"
              :min="0"
              :max="2"
              :step="0.1"
              style="width: 100px"
            />
          </n-space>
        </n-form-item>

        <!-- Top P -->
        <n-form-item label="Top P采样" label-placement="left" label-width="100">
          <n-space align="center" style="width:100%">
            <n-slider
              v-model:value="profileForm.top_p"
              :min="0"
              :max="1"
              :step="0.05"
              style="width: 200px"
            />
            <n-input-number
              v-model:value="profileForm.top_p"
              size="small"
              :min="0"
              :max="1"
              :step="0.05"
              style="width: 100px"
            />
          </n-space>
        </n-form-item>

        <!-- Top K -->
        <n-form-item label="Top K采样" label-placement="left" label-width="100">
          <n-space align="center">
            <n-slider
              v-model:value="profileForm.top_k"
              :min="1"
              :max="100"
              :step="1"
              style="width: 200px"
            />
            <n-input-number
              v-model:value="profileForm.top_k"
              size="small"
              :min="1"
              :max="100"
              :step="1"
              style="width: 100px"
            />
          </n-space>
        </n-form-item>
        <!-- Frequency Penalty -->
        <n-form-item label="频率惩罚" label-placement="left" label-width="100">
          <n-space align="center">
            <n-slider
              v-model:value="profileForm.frequency_penalty"
              :min="-2"
              :max="2"
              :step="0.1"
              style="width: 200px"
            />
            <n-input-number
              v-model:value="profileForm.frequency_penalty"
              size="small"
              :min="-2"
              :max="2"
              :step="0.1"
              style="width: 100px"
            />
          </n-space>
        </n-form-item>

        <!-- Presence Penalty -->
        <n-form-item label="存在惩罚" label-placement="left" label-width="100">
          <n-space align="center">
            <n-slider
              v-model:value="profileForm.presence_penalty"
              :min="-2"
              :max="2"
              :step="0.1"
              style="width: 200px"
            />
            <n-input-number
              v-model:value="profileForm.presence_penalty"
              size="small"
              :min="-2"
              :max="2"
              :step="0.1"
              style="width: 100px"
            />
          </n-space>
        </n-form-item>
      </n-collapse-item>
    </n-collapse>
  </n-modal>
</template>

<script setup lang="ts">
import {
  NForm, NFormItem, NInput, NPopover, NButton, NSpace,
  NModal, NCheckboxGroup, NCheckbox, NSlider,
  NInputNumber, NCollapseItem, NCollapse, NAvatar
} from 'naive-ui'
import { ref, reactive, watch  } from 'vue'
import { useProfileStore, type Profile } from '@/stores/profiles'

const props = defineProps({
    show: {
        type: Boolean,
        default: false
    },
    isEditing: {
        type: Boolean,
        default: false
    },
    profileId: {
        type: Number,
        default: 0
    }
})

const emit = defineEmits(['update:show'])

const profileStore = useProfileStore()

const allTools = ref<{ function: { name: string; title: string; description: string } }[]>([])
const editingProfile = ref<Profile | null>(null)
const profileForm = reactive({
  name: '',
  tools: [] as string[],
  profile_prompt: '',
  temperature: 1,
  top_p: 0.95,
  top_k: 40,
  frequency_penalty: 0,
  presence_penalty: 0
})

watch(() => props.show, (val) => {
  if (val) {
    if (props.isEditing) {
      openEditProfile()
    } else {
      openCreateProfile()
    }
  }
})

// 加载全局工具列表
async function loadTools() {
  try {
    const res = await fetch('/api/tools')
    const data = await res.json()
    allTools.value = data.tools || []
  } catch (e) {
    console.warn('获取工具列表失败', e)
  }
}

// 创建角色
const openCreateProfile = () => {
    if(allTools.value.length === 0) {
        loadTools()
    }
    editingProfile.value = null
    profileForm.name = ''
    profileForm.tools = []
    profileForm.profile_prompt = ''
    profileForm.temperature = 1
    profileForm.top_p = 0.95
    profileForm.top_k = 40
    profileForm.frequency_penalty = 0
    profileForm.presence_penalty = 0
}

// 编辑角色
const openEditProfile = () => {
  if (!profileStore.activeProfile) return
  if(allTools.value.length === 0) {
    loadTools()
  }
  const p = profileStore.getProfile(props.profileId)
  if (!p) return
  editingProfile.value = { ...p }
  profileForm.name = p.name
  profileForm.tools = [...p.tools]
  profileForm.profile_prompt = p.profile_prompt || ''
  // 读取角色保存的参数，若旧角色没有则使用默认值
  profileForm.temperature = p.temperature ?? 1
  profileForm.top_p = p.top_p ?? 0.95
  profileForm.top_k = p.top_k ?? 40
  profileForm.frequency_penalty = p.frequency_penalty ?? 0
  profileForm.presence_penalty = p.presence_penalty ?? 0
}

const negativeClick = () => {
    emit('update:show', false)
}

// 保存配置
async function saveProfile() {
    if (props.isEditing && editingProfile.value) {
        await profileStore.updateProfile(
        editingProfile.value.id,
        profileForm.name,
        profileForm.tools,
        profileForm.profile_prompt,
        profileForm.temperature,
        profileForm.top_p,
        profileForm.top_k,
        profileForm.frequency_penalty,
        profileForm.presence_penalty
        )
    } else {
        await profileStore.createProfile(
        profileForm.name,
        profileForm.tools,
        profileForm.profile_prompt,
        profileForm.temperature,
        profileForm.top_p,
        profileForm.top_k,
        profileForm.frequency_penalty,
        profileForm.presence_penalty
        )
    }
    emit('update:show', false)
}
</script>