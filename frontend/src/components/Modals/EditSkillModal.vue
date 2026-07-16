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
    negative-text="取消"
    @update:show="negativeClick"
    @positive-click="saveSkill"
    @negative-click="negativeClick"
  >
    <div class="modal-content">
      <!-- 角色信息 (只读展示) -->
      <div class="profile-section">
        <n-form label-placement="left" label-width="70" size="large" :show-feedback="false">
          <n-form-item>
            <n-avatar v-if="profileStore.activeProfile" class="avatar" round :size="60" :src="`/images/avatars/${profileStore.activeProfile.avatar}`"/>
          </n-form-item>
          <n-form-item label="角色">
            <n-input v-model:value="localProfile.name" disabled />
          </n-form-item>
          <n-form-item label="能力">
            <n-flex :size="4" style="margin-top:6px">
              <n-tag v-for="name in localProfile.tools" :key="name" :bordered="false" type="info">
                {{ toolStore.toolsInfo[name]?.title ?? name }}
              </n-tag>
            </n-flex>
          </n-form-item>
          <n-form-item label="技能">
            <n-flex :size="4" v-if="selectedSkills.length">
              <!-- 只展示已勾选的技能，并转换为名称 -->
              <n-tag v-for="skillId in selectedSkills" :key="skillId" :bordered="false" type="warning">
                {{ getSkillNameById(skillId) }}
              </n-tag>
            </n-flex>
            <span v-else style="color: var(--text-secondary)">未装备任何技能</span>
          </n-form-item>
        </n-form>
      </div>

      <n-divider dashed>技能修炼</n-divider>

      <!-- 技能修炼区 -->
      <div class="skill-section">
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
        <!-- 技能列表 -->
        <div class="skill-checkbox-list" v-if="allSkills.length">
          <n-checkbox-group v-model:value="selectedSkills">
            <n-flex :size="12">
              <n-checkbox 
                v-for="skill in allSkills" 
                :key="skill.id" 
                :value="skill.id"
              >
                <div class="skill-item-wrapper">
                  <div class="skill-header">
                    <!-- 悬停展示描述 -->
                    <n-tooltip trigger="hover" v-if="skill.description">
                      <template #trigger>
                        <span class="skill-name skill-name--has-desc">{{ skill.name }}</span>
                      </template>
                      <div class="skill-tooltip-desc">{{ skill.description }}</div>
                    </n-tooltip>
                    <span v-else class="skill-name">{{ skill.name }}</span>
                    
                    <!-- 全局标签：只要技能是全局的就显示 -->
                    <n-tag 
                      v-if="skill.isGlobal" 
                      size="small" 
                      type="success" 
                      :bordered="false" 
                      style="margin-left: 8px; transform: scale(0.9);"
                    >
                      全局
                    </n-tag>
                  </div>
                </div>
              </n-checkbox>
            </n-flex>
          </n-checkbox-group>
        </div>
        <span v-else style="color: #999; font-size: 14px">无可用技能，请添加</span>
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
    positive-text="开始修炼"
    negative-text="关闭"
    @positive-click="addSkill"
    @negative-click="cancelAdd"
  >
    <n-form label-placement="left" label-width="0" size="large" style="margin-top:20px">
      <n-form-item label="" label-placement="left" label-width="0">
        <n-input
          v-model:value.trim="newSkillName"
          placeholder="请输入技能名称"
          :disabled="adding"
        />
      </n-form-item>
      
      <n-form-item label="" label-placement="left" label-width="0">
        <n-checkbox v-model:checked="newSkillGlobal">
          设为全局技能 (所有角色可用)
        </n-checkbox>
      </n-form-item>

      <n-form-item>
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
                <span v-if="pendingFiles.length > 0 && uploadPhase === 'idle'">技能已准备就绪，点击“开始修炼”</span>
                <span v-else-if="uploadPhase === 'idle'">点击或拖动技能文件夹到该区域</span>
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
  NCheckbox, NText, NAvatar, NButton, NUpload, NTooltip, useMessage, type UploadCustomRequestOptions } from 'naive-ui'
import { ref, reactive, watch, onUnmounted } from 'vue'
import mSvg from '@/components/MSvg.vue'
import { useProfileStore } from '@/stores/profiles'
import { useToolStore } from '@/stores/tools'

interface SkillItem {
  id: string
  name: string
  isGlobal: boolean
  description?: string
}

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

const allSkills = ref<SkillItem[]>([])
const selectedSkills = ref<string[]>([])
const originalSelectedSkills = ref<string[]>([])

// 根据技能 id 获取技能名称
function getSkillNameById(id: string): string {
  const skill = allSkills.value.find(s => s.id === id)
  return skill?.name ?? '未知技能'
}

// 加载所有可用技能
async function loadAllSkills() {
  try {
     const url = props.profileId ? `/api/skills/list?profile_id=${props.profileId}` : '/api/skills/list'
    const res = await fetch(url)
    const data = await res.json()
    allSkills.value = (data || []).map((item: any) => ({
      id: item.id,
      name: item.name || item.id,
      isGlobal: !!item.is_global,
      description: item.description
    }))
  } catch (e) {
    message.error("加载技能列表失败")
  }
}
// 加载已习得技能
async function loadLearnedSkills() {
    try {
    const res = await fetch(`/api/profiles/${props.profileId}/skills`)
    const data = await res.json()
    localProfile.skills = data || []
  } catch (e) {
    message.error("查询已习得技能失败")
  }
}

// 监听弹窗打开
watch(
  () => props.show,
  async (val) => {
    if (val && props.profileId != null) {
      selectedSkills.value = []
      // 加载所有可用技能
      await loadAllSkills()
      const p = profileStore.getProfile(props.profileId)
      if (p) {
        localProfile.name = p.name || ''
        localProfile.tools = p.tools || []
        await loadLearnedSkills()
      }
      
      // 设置当前角色已选中的技能（用 ID 匹配）
      selectedSkills.value = [...localProfile.skills]

      // 记录初始状态，用于后续对比
      originalSelectedSkills.value = [...localProfile.skills]
    }
  },
  { immediate: true }
)

// 保存配置
const saveSkill = async () => {
  if (props.profileId == null) {
    emit('update:show', false)
    return
  }

  const response = await fetch('/api/skills/batch-select', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      profile_id: props.profileId,
      selected_skill_ids: selectedSkills.value,   // 当前所有勾选的 ID
    }),
  })

  if (response.ok) {
    message.success('技能配置已保存')
  } else {
    message.error('保存失败')
  }

  emit('update:show', false)
}

const negativeClick = () => {
  emit('update:show', false)
}

// ---------- 子弹窗（添加技能）相关 ----------
const addSkillModalShow = ref(false)
const newSkillName = ref('')
const newSkillGlobal = ref(false)
const adding = ref(false)

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
const pendingFiles = ref<{ file: File; relativePath: string }[]>([])

function startUpload() {
  if (finishTimer) {
    clearTimeout(finishTimer)
    finishTimer = null
  }
  uploadPhase.value = 'progress'
}

function finishUpload() {
  uploadPhase.value = 'finish'
  adding.value = false
  if (finishTimer) clearTimeout(finishTimer)
  finishTimer = window.setTimeout(() => {
    uploadPhase.value = 'idle'
    finishTimer = null
  }, 1000)
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

  pendingFiles.value.push({ file: rawFile, relativePath })
  onFinish()
}

const flushQueue = async () => {
  const tasks = [...uploadQueue.value]
  uploadQueue.value = []

  if (tasks.length === 0) return

  const formData = new FormData()
  const skillName = newSkillName.value.trim()
  
  formData.append('skillName', skillName)
  formData.append('is_global', String(newSkillGlobal.value))
  
  if (props.profileId) {
    formData.append('profile_id', String(props.profileId))
  }

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
        
        const newSkill: SkillItem = {
          id: result.id,
          name: newSkillName.value,
          isGlobal: result.is_global !== undefined ? result.is_global : newSkillGlobal.value,
          description: result.description || ''
        }

        // 检查是否已在列表中
        const existIndex = allSkills.value.findIndex(s => s.id === newSkill.id)
        
        if (existIndex === -1) {
          allSkills.value.push(newSkill)
        } else {
          allSkills.value[existIndex] = newSkill
        }
        
        // 自动勾选新添加的技能（使用 id）
        if (!selectedSkills.value.includes(newSkill.id)) {
            selectedSkills.value.push(newSkill.id)
        }
        setTimeout(() => {
            message.success(`技能 [${newSkill.name}] 修炼成功！`)
            addSkillModalShow.value = false
        }, 1000)
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
    message.error("技能名称还没有填写哦~")
    return
  }
  if (uploadPhase.value === 'progress') return

  const items = e.dataTransfer?.items
  if (!items || items.length === 0) return

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
  pendingFiles.value = allFiles
}

const openAddSkillModal = () => {
  newSkillName.value = ''
  newSkillGlobal.value = false
  uploadPhase.value = 'idle'
  pendingFiles.value = []
  addSkillModalShow.value = true
}

const cancelAdd = () => {
  addSkillModalShow.value = false
}

const addSkill = async () => {
  const name = newSkillName.value.trim()
  if (!name) {
    message.warning('请输入技能名称')
    return false
  }
  if (allSkills.value.find(s => s.name === name)) {
    message.warning('技能名称已存在')
    return false
  }
  if (pendingFiles.value.length === 0) {
    message.warning('请通过拖拽或点击选择技能文件夹')
    return false
  }
  if (uploadPhase.value === 'progress') {
    message.info('正在修炼中...')
    return false
  }
  // 开始上传
  startUpload()
  adding.value = true

  // 将暂存的文件全部加入上传队列
  pendingFiles.value.forEach(({ file, relativePath }) => {
    addFileToQueue(file, relativePath, undefined, undefined)
  })
  pendingFiles.value = []

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
  max-height: 300px;
  overflow-y: auto;
  margin-bottom: 12px;
  padding-right: 4px;
}

.skill-item-wrapper {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-left: 4px;
}
.skill-header {
  display: flex;
  align-items: center;
}
.skill-name {
  font-weight: 500;
  font-size: 14px;
}
.skill-name--has-desc {
  border-bottom: 1px dashed #999;
  cursor: help;
}
.skill-tooltip-desc {
  max-width: 320px;
  white-space: normal;
  word-break: break-word;
  line-height: 1.5;
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
.avatar {box-shadow: 0 0 2px rgba(128,128,.3);border:2px solid #fff;margin-left:220px;margin-bottom:10px;}
</style>