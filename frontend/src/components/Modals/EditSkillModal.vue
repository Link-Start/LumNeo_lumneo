<template>
  <n-modal
    :show="show"
    :auto-focus="false"
    preset="dialog"
    draggable
    :mask-closable="false"
    style="max-width: 520px; width: 96%"
    title="习得技能"
    positive-text="确认"
    negative-text="关闭"
    @update:show="negativeClick"
    @positive-click="saveSkill"
    @negative-click="negativeClick"
  >
    <!-- 弹框内容 -->
    <div class="modal-content">
      <!-- 1. 角色信息 -->
      <div class="profile-section">
        <n-form label-placement="left" label-width="70" size="large" :show-feedback="false">
          <n-form-item label="角色">
            <n-input v-model:value="localProfile.name" disabled />
          </n-form-item>
          <n-form-item label="能力">
            <n-flex :size="8">
              <n-tag v-for="name in localProfile.tools" :key="name" :bordered="false" type="info">
                {{ toolStore.toolsInfo[name].title }}
              </n-tag>
            </n-flex>
          </n-form-item>
          <n-form-item label="技能">
            <n-flex :size="8" v-if="localProfile.skills.length">
              <n-tag v-for="skill in localProfile.skills" :key="skill" :bordered="false" type="info">
                {{ skill }}
              </n-tag>
            </n-flex>
            <span v-else style="color: var(--text-secondary)">未习得任何技能</span>
          </n-form-item>
        </n-form>
      </div>

      <n-divider dashed>技能修炼</n-divider>

      <!-- 2. 技能管理 -->
      <div class="skill-section">
        <div class="skill-upload">
          <n-upload
            directory
            :show-file-list="false"
            :disabled="uploadPhase === 'progress'"
            :custom-request="customRequest"
            @change="handleUploadChange"
          >
            <n-upload-dragger>
              <div style="margin-bottom: 12px">
                <m-svg
                  :name="
                    uploadPhase === 'progress'
                      ? 'skill-cultivation-progress'
                      : uploadPhase === 'finish'
                        ? 'skill-cultivation-finish'
                        : 'skill-cultivation'
                  "
                  :size="120"
                />
              </div>
              <n-text style="font-size: 16px; opacity: 0.45">
                <span v-if="uploadPhase === 'idle'">点击选择技能文件夹</span>
                <span v-else-if="uploadPhase === 'progress'">修炼中...</span>
                <span v-else-if="uploadPhase === 'finish'">习得成功！</span>
              </n-text>
            </n-upload-dragger>
          </n-upload>
        </div>

        <div class="skill-list">
          <n-space size="small" wrap>
            <n-tag v-for="skill in localProfile.skills" :key="skill" closable @close="removeSkill(skill)">
              {{ skill }}
            </n-tag>
            <span v-if="!localProfile.skills.length" style="color: #999; font-size: 14px"> 暂无技能 </span>
          </n-space>
        </div>
      </div>
    </div>
  </n-modal>
</template>

<script setup lang="ts">
import {
  NForm,
  NFormItem,
  NInput,
  NButton,
  NSpace,
  NModal,
  NDivider,
  NTag,
  NFlex,
  NUpload,
  NUploadDragger,
  NText,
  useMessage,
  type UploadFileInfo,
  type UploadCustomRequestOptions
} from 'naive-ui'
import { ref, reactive, watch, onUnmounted } from 'vue'
import mSvg from '@/components/MSvg.vue'
import { useProfileStore } from '@/stores/profiles'
import { useToolStore } from '@/stores/tools'

const props = defineProps({
  show: Boolean,
  isEditing: Boolean,
  profileId: Number
})

const emit = defineEmits(['update:show'])
const message = useMessage()
const profileStore = useProfileStore()
const toolStore = useToolStore()

// 本地副本，用于编辑
const localProfile = reactive({
  name: '',
  tools: [] as string[],
  skills: [] as string[]
})

const newSkill = ref('')

// 上传状态
const uploadPhase = ref<'idle' | 'progress' | 'finish'>('idle')
let finishTimer: number | null = null

// --- 批量上传队列逻辑 ---
interface UploadTask {
  file: File
  relativePath: string
  onFinish: () => void
  onError: () => void
}

const uploadQueue = ref<UploadTask[]>([])
let uploadTimer: number | null = null

watch(
  () => props.show,
  (val) => {
    uploadPhase.value = 'idle'
    if (val && props.profileId) {
      const p = profileStore.getProfile(props.profileId)
      if (p) {
        localProfile.name = p.name || ''
        localProfile.tools = p.tools
        localProfile.skills = [...(p.skills || [])]
      }
    }
  },
  { immediate: true }
)

// 核心上传逻辑
const customRequest = async ({ file, onFinish, onError }: UploadCustomRequestOptions) => {
  const rawFile = file.file
  if (!rawFile) {
    onError()
    return
  }

  // 1. 稳健获取路径：优先使用 Naive UI 处理过的 file.name (通常包含目录结构)
  // @ts-ignore
  const naivePath = file.name 
  // @ts-ignore
  const webkitPath = rawFile.webkitRelativePath
  
  let relativePath = ''

  // 判断哪个路径有效 (包含 '/' 说明包含文件夹信息)
  if (naivePath && naivePath.includes('/')) {
    relativePath = naivePath
  } else if (webkitPath && webkitPath.includes('/')) {
    relativePath = webkitPath
  } else {
    // 如果都不包含路径分隔符，说明获取失败
    // 可能原因：用户拖拽了单个文件而非文件夹，或者浏览器环境不支持
    message.error('上传失败：请确保上传的是文件夹，且点击选择文件夹而非拖拽')
    uploadPhase.value = 'idle'
    onError()
    return
  }

  uploadQueue.value.push({
    file: rawFile,
    relativePath,
    onFinish,
    onError
  })

  if (uploadTimer) clearTimeout(uploadTimer)
  
  uploadTimer = window.setTimeout(() => {
    flushQueue()
  }, 200)
}

const flushQueue = async () => {
  const tasks = [...uploadQueue.value]
  uploadQueue.value = [] 

  if (tasks.length === 0) return

  const formData = new FormData()
  const skillName = tasks[0].relativePath.split('/')[0]
  
  tasks.forEach((task) => {
    formData.append('files', task.file, task.relativePath)
  })

  try {
    const response = await fetch('/api/skills/upload', {
      method: 'POST',
      body: formData
    })

    if (response.ok) {
      const result = await response.json()
      if (result.success) {
        tasks.forEach((t) => t.onFinish())
        if (skillName && !localProfile.skills.includes(skillName)) {
          localProfile.skills.push(skillName)
        }
        message.success(`技能 [${skillName}] 修炼成功！`)
      } else {
        message.error(result.message || '上传失败')
        tasks.forEach((t) => t.onError())
      }
    } else {
      message.error(`服务器错误: ${response.statusText}`)
      tasks.forEach((t) => t.onError())
    }
  } catch (error) {
    console.error('批量上传异常:', error)
    message.error('网络请求失败')
    tasks.forEach((t) => t.onError())
  }
}

const handleUploadChange = (options: { fileList: UploadFileInfo[] }) => {
  const { fileList } = options
  const hasUploadingFile = fileList.some((file) => file.status === 'uploading' || file.status === 'pending')

  if (hasUploadingFile) {
    uploadPhase.value = 'progress'
    if (finishTimer) clearTimeout(finishTimer)
  } else {
    if (uploadPhase.value === 'progress') {
      uploadPhase.value = 'finish'
      if (finishTimer) clearTimeout(finishTimer)
      finishTimer = window.setTimeout(() => {
        uploadPhase.value = 'idle'
        finishTimer = null
      }, 3000)
    }
  }
}

onUnmounted(() => {
  if (finishTimer) clearTimeout(finishTimer)
  if (uploadTimer) clearTimeout(uploadTimer)
})


const removeSkill = (skill: string) => {
  const index = localProfile.skills.indexOf(skill)
  if (index !== -1) {
    localProfile.skills.splice(index, 1)
  }
}

const saveSkill = () => {
  if (props.profileId) {
    const target = profileStore.getProfile(props.profileId)
    if (target) {
      target.skills = [...localProfile.skills]
    }
  }
  emit('update:show', false)
}

const negativeClick = () => {
  emit('update:show', false)
}
</script>

<style scoped>
/* 样式保持不变 */
.modal-content {
  padding: 4px 0;
}
.profile-section {
  margin-bottom: 8px;
}
.skill-section {
  margin-top: 4px;
}
.skill-list {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 0;
  margin-bottom: 16px;
}
.section-label {
  font-weight: 500;
  margin-right: 8px;
  color: #333;
}
.add-skill {
  display: flex;
  gap: 12px;
  align-items: center;
}
</style>
