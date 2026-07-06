<template>
  <!-- 主弹窗：习得技能 -->
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
    <div class="modal-content">
      <!-- 角色信息 -->
      <div class="profile-section">
        <n-form label-placement="left" label-width="70" size="large" :show-feedback="false">
          <n-form-item label="角色">
            <n-input v-model:value="localProfile.name" disabled />
          </n-form-item>
          <n-form-item label="能力">
            <n-flex :size="4" style="margin-top:4px">
              <n-tag v-for="name in localProfile.tools" :key="name" :bordered="false" type="info">
                {{ toolStore.toolsInfo[name]?.title ?? name }}
              </n-tag>
            </n-flex>
          </n-form-item>
          <n-form-item label="技能">
            <n-flex :size="8" v-if="selectedSkills.length">
              <n-tag v-for="skill in selectedSkills" :key="skill" :bordered="false" type="warning">
                {{ skill }}
              </n-tag>
            </n-flex>
            <span v-else style="color: var(--text-secondary)">未习得任何技能</span>
          </n-form-item>
        </n-form>
      </div>

      <n-divider dashed>技能修炼</n-divider>

      <!-- 技能修炼区 -->
      <div class="skill-section">
        <!-- 添加技能按钮 -->
        <n-button
          type="primary"
          dashed
          block
          style="margin-top: 12px"
          @click="openAddSkillModal"
        >
          <template #icon>
            <span style="font-size: 16px">+</span>
          </template>
          添加技能
        </n-button>
        <br>
        <!-- 已有技能多选列表 -->
        <div class="skill-checkbox-list" v-if="allSkills.length">
          <n-checkbox-group v-model:value="selectedSkills">
            <n-flex>
              <n-checkbox v-for="skill in allSkills" :key="skill" :value="skill">
                {{ skill }}
              </n-checkbox>
            </n-flex>
          </n-checkbox-group>
        </div>
        <span v-else style="color: #999; font-size: 14px">暂无技能，请添加</span>
      </div>
    </div>
  </n-modal>

  <!-- 子弹窗：添加新技能 -->
  <n-modal
    v-model:show="addSkillModalShow"
    preset="dialog"
    style="max-width: 520px; width: 96%"
    title="修炼新技能"
    :mask-closable="false"
    :loading="adding"
    @positive-click="addSkill"
    @negative-click="cancelAdd"
  >
    <n-form label-placement="left" label-width="0" size="large" style="margin-top:20px">
      <n-form-item>
        <n-input
          v-model:value.trim="newSkillName"
          placeholder="请输入技能名称"
          :disabled="adding"
        />
      </n-form-item>
      <n-form-item>
        <!-- 原拖拽上传组件（保持原有样式和行为） -->
        <div class="skill-upload" @drop.prevent="onDrop" @dragover.prevent.stop>
          <n-upload
            directory
            :show-file-list="false"
            :disabled="['progress', 'finish'].includes(uploadPhase) || !newSkillName.trim()"
            :custom-request="customRequest"
          >
            <div class="upload-area">
              <div style="margin-bottom: 12px">
                <m-svg
                  :name="
                    uploadPhase === 'progress'
                      ? 'skill-cultivation-progress'
                      : uploadPhase === 'finish'
                        ? 'skill-cultivation-finish'
                        : 'skill-cultivation'
                  "
                  :size="240"
                />
              </div>
              <n-text v-if="newSkillName.trim()" style="font-size: 16px; opacity: 0.45">
                <span v-if="uploadPhase === 'idle'">点击或拖动技能文件夹到该区域</span>
                <span v-else-if="uploadPhase === 'progress'">修炼中...</span>
                <span v-else-if="uploadPhase === 'finish'">习得成功！</span>
              </n-text>
              <n-text v-else>请先输入技能名称，才能继续修炼</n-text>
            </div>
          </n-upload>
        </div>
      </n-form-item>
    </n-form>
  </n-modal>
</template>

<script setup lang="ts">
import { NForm, NFormItem, NInput, NModal, NDivider, NTag, NFlex, NCheckboxGroup, 
  NCheckbox, NText, NButton, NUpload, useMessage, type UploadCustomRequestOptions } from 'naive-ui'
import { ref, reactive, watch, onUnmounted } from 'vue'
import mSvg from '@/components/MSvg.vue'
import { useProfileStore } from '@/stores/profiles'
import { useToolStore } from '@/stores/tools'

const props = defineProps({
  show: Boolean,
  profileId: Number,
})

const emit = defineEmits(['update:show'])
const message = useMessage()
const profileStore = useProfileStore()
const toolStore = useToolStore()

// ---------- 主弹窗数据 ----------
const localProfile = reactive({
  name: '',
  tools: [] as string[],
  skills: [] as string[],
})

// 所有可选技能（初始来自角色已有技能，新增技能也会加入）
const allSkills = ref<string[]>([])
// 勾选的技能（将保存为最终技能）
const selectedSkills = ref<string[]>([])

// 监听主弹窗打开，加载角色数据
watch(
  () => props.show,
  (val) => {
    if (val && props.profileId != null) {
      const p = profileStore.getProfile(props.profileId)
      if (p) {
        localProfile.name = p.name || ''
        localProfile.tools = p.tools || []
        localProfile.skills = p.skills ? [...p.skills] : []
      }
      // 初始化可选和已选技能
      allSkills.value = [...localProfile.skills]
      selectedSkills.value = [...localProfile.skills]
    }
  },
  { immediate: true }
)

// 保存：将勾选的技能写入角色
const saveSkill = () => {
  if (props.profileId != null) {
    const target = profileStore.getProfile(props.profileId)
    if (target) {
      target.skills = [...selectedSkills.value]
    }
  }
  emit('update:show', false)
}

const negativeClick = () => {
  emit('update:show', false)
}

// ---------- 子弹窗（添加技能）相关 ----------
const addSkillModalShow = ref(false)
const newSkillName = ref('')
const adding = ref(false)

// 将原上传组件的状态移植到此处
const uploadPhase = ref<'idle' | 'progress' | 'finish'>('idle')
let finishTimer: number | null = null

interface UploadTask {
  file: File
  relativePath: string
  onFinish: () => void
  onError: () => void
}
const uploadQueue = ref<UploadTask[]>([])
let uploadTimer: number | null = null
const activeUploads = ref(0)

// 原拖拽/上传相关逻辑（完全保留）
function startUpload() {
  if (finishTimer) {
    clearTimeout(finishTimer)
    finishTimer = null
  }
  uploadPhase.value = 'progress'
}

function finishUpload() {
  uploadPhase.value = 'finish'
  if (finishTimer) clearTimeout(finishTimer)
  finishTimer = window.setTimeout(() => {
    uploadPhase.value = 'idle'
    finishTimer = null
  }, 3000)
}

function addFileToQueue(
  file: File,
  relativePath: string,
  origOnFinish?: () => void,
  origOnError?: () => void
) {
  activeUploads.value++

  const onFinish = () => {
    origOnFinish?.()
    activeUploads.value--
    if (activeUploads.value === 0) finishUpload()
  }

  const onError = () => {
    origOnError?.()
    activeUploads.value--
    if (activeUploads.value === 0) finishUpload()
  }

  uploadQueue.value.push({ file, relativePath, onFinish, onError })

  if (uploadTimer) clearTimeout(uploadTimer)
  uploadTimer = window.setTimeout(() => {
    flushQueue()
  }, 200)
}

const customRequest = async ({ file, onFinish, onError }: UploadCustomRequestOptions) => {
  const rawFile = file.file
  if (!rawFile) {
    onError()
    return
  }

  const naivePath = file.name
  // @ts-ignore
  const webkitPath = rawFile.webkitRelativePath

  let relativePath = ''
  if (naivePath && naivePath.includes('/')) {
    relativePath = naivePath
  } else if (webkitPath && webkitPath.includes('/')) {
    relativePath = webkitPath
  } else {
    message.error('上传失败：请选择文件夹，而非单个文件')
    onError()
    return
  }

  startUpload()
  addFileToQueue(rawFile, relativePath, onFinish, onError)
}

const flushQueue = async () => {
  const tasks = [...uploadQueue.value]
  uploadQueue.value = []

  if (tasks.length === 0) return

  const formData = new FormData()
  // 使用用户输入的技能名称，而非从路径提取
  const skillName = newSkillName.value.trim()
  formData.append('skillName', skillName)

  tasks.forEach((task) => {
    formData.append('files', task.file, task.relativePath)
  })

  try {
    const response = await fetch('/api/skills/upload', {
      method: 'POST',
      body: formData,
    })

    if (response.ok) {
      const result = await response.json()
      if (result.success) {
        tasks.forEach((t) => t.onFinish())
        // 上传成功后，将技能加入主弹窗列表并自动勾选
        if (skillName && !allSkills.value.includes(skillName)) {
          allSkills.value.push(skillName)
          selectedSkills.value.push(skillName)
        }
        message.success(`技能 [${skillName}] 修炼成功！`)
        // 关闭子弹窗
        addSkillModalShow.value = false
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

// 拖拽文件夹处理（保留原逻辑）
async function traverseEntry(entry: FileSystemEntry, basePath: string): Promise<File[]> {
  if (entry.isFile) {
    const file = await new Promise<File>((resolve, reject) => {
      (entry as FileSystemFileEntry).file(resolve, reject)
    })
    Object.defineProperty(file, 'webkitRelativePath', {
      value: basePath + file.name,
      writable: false,
    })
    return [file]
  }

  if (entry.isDirectory) {
    const reader = (entry as FileSystemDirectoryEntry).createReader()
    const entries = await new Promise<FileSystemEntry[]>((resolve, reject) => {
      reader.readEntries(resolve, reject)
    })

    const files: File[] = []
    for (const child of entries) {
      const childFiles = await traverseEntry(child, basePath + entry.name + '/')
      files.push(...childFiles)
    }
    return files
  }

  return []
}

async function onDrop(e: DragEvent) {
  
  if(!newSkillName.value.trim()) {
    message.error("技能名称还没有填写呢！")
    return
  }
  if (uploadPhase.value === 'progress') return

  const items = e.dataTransfer?.items
  if (!items || items.length === 0) return

  startUpload()

  const allFiles: { file: File; relativePath: string }[] = []
  let topFolder: string | null = null

  for (let i = 0; i < items.length; i++) {
    const item = items[i]
    if (item.kind !== 'file') continue
    const entry = item.webkitGetAsEntry?.()
    if (!entry) continue

    const filesFromEntry = await traverseEntry(entry, '')
    for (const file of filesFromEntry) {
      // @ts-ignore
      const path: string = file.webkitRelativePath || file.name
      const folder = path.split('/')[0]

      if (!topFolder) {
        topFolder = folder
      } else if (topFolder !== folder) {
        message.error('一次只允许拖拽一个技能文件夹')
        uploadPhase.value = 'idle'
        return
      }

      allFiles.push({ file, relativePath: path })
    }
  }

  if (allFiles.length === 0) {
    message.error('拖拽区域未检测到有效文件')
    uploadPhase.value = 'idle'
    return
  }

  allFiles.forEach(({ file, relativePath }) => {
    addFileToQueue(file, relativePath)
  })
}

// 打开添加技能弹窗
const openAddSkillModal = () => {
  newSkillName.value = ''
  uploadPhase.value = 'idle'
  addSkillModalShow.value = true
}

// 取消添加
const cancelAdd = () => {
  addSkillModalShow.value = false
}

// 确认添加（需等待上传完成，这里通过按钮 loading 控制）
const addSkill = async () => {
  const name = newSkillName.value.trim()
  if (!name) {
    message.warning('请输入技能名称')
    return false
  }
  if (allSkills.value.includes(name)) {
    message.warning('技能名称已存在')
    return false
  }
  // 若用户没有拖拽/选择文件，则不允许添加
  if (uploadQueue.value.length === 0 && activeUploads.value === 0) {
    message.warning('请通过拖拽或点击选择技能文件夹')
    return false
  }
  if (uploadPhase.value === 'progress') {
    message.info('正在上传，请稍后...')
    return false
  }
  // 如果已经处于 finish 状态，说明刚刚上传完成，可以直接关闭（已经在 flushQueue 中处理了关闭）
  if (uploadPhase.value === 'finish') {
    // 此时技能已添加，直接关闭
    addSkillModalShow.value = false
    return true
  }
  // 其他情况（idle 状态且没有文件）：提示
  message.warning('请先选择文件夹上传')
  return false
}

onUnmounted(() => {
  if (finishTimer) clearTimeout(finishTimer)
  if (uploadTimer) clearTimeout(uploadTimer)
})
</script>

<style scoped>
.modal-content {
  padding: 4px 0;
}
.profile-section {
  margin-bottom: 8px;
}
.skill-section {
  margin-top: 4px;
}
.skill-checkbox-list {
  max-height: 200px;
  overflow-y: auto;
  margin-bottom: 12px;
}
.skill-list {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 0;
  margin-bottom: 16px;
}
.skill-upload{width:100%;}
:deep(.n-upload-trigger) {
  display: block !important;
}
.upload-area {
  padding: 24px;
  border: var(--n-dragger-border);
  border-radius: 4px;
  text-align: center;
  cursor: pointer;
  transition: border-color 0.3s;
}
.upload-area:hover {
  border-color: #1890ff;
}
</style>