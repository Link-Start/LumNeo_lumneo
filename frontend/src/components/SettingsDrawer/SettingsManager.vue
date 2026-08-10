<template>
    <div>
        <n-form label-placement="left" label-width="80">
            <n-form-item label="启用角色">
              <n-switch v-model:value="chatStore.enableProfile" @update-value="handleProfile"/>
            </n-form-item>
            <n-form-item label="主题">
              <n-button @click="configStore.toggleTheme">
                <template #icon>
                  <n-icon><m-svg :name="configStore.themeMode === 'dark' ? 'moon' : 'son'"/></n-icon>
                </template>
                {{ configStore.themeMode === 'dark' ? '暗色' : '浅色' }}
              </n-button>
            </n-form-item>
            <n-form-item label="工作目录">
              <n-input-group>
                <n-input v-model:value="workspacePath" size="large" placeholder="选择或输入目录路径" @change="saveWorkspace(workspacePath)"/>
                <n-button secondary @click="selectFolder" size="large">选择</n-button>
              </n-input-group>
            </n-form-item>
            <n-form-item label="归档模型">
          <template #label>
            <n-tooltip placement="top" :keep-alive-on-hover="false">
              <template #trigger>
                <span style="cursor: help; border-bottom: 1px dashed #999">归档模型</span>
              </template>
              用于后台记忆归档的专用模型。建议选择成本低、速度快的模型。<br/>
              如果未配置，后台自动归档将跳过
            </n-tooltip>
          </template>
          <n-select
            v-model:value="archiveModelId"
            :options="archiveModelOptions"
            placeholder="选择归档专用模型"
            clearable
            style="width: 280px"
            @update:value="saveArchiveModel"
            @clear="clearArchiveModel"
          />
        </n-form-item>
        </n-form>

        <!-- ========== 角色管理 ========== -->
        <div v-if="chatStore.enableProfile">
            <div>
                <n-divider />
                <h3 style="margin-bottom: 12px;">角色管理</h3>
                <n-select size="large"
                v-model:value="profileId"
                :options="profileOptions"
                placeholder="选择角色"
                style="margin-bottom: 12px;"
                />
                <n-space justify="center">
                <n-button @click="openCreateProfile" secondary type="primary">
                    <template #icon><n-icon><add /></n-icon></template>
                    新建角色
                </n-button>
                <n-button @click="openEditProfile" secondary :disabled="!profileId">
                    <template #icon><n-icon><create-outline /></n-icon></template>
                    编辑
                </n-button>
                <n-button @click="openProfileSkills" secondary :disabled="!profileId">
                    <template #icon><n-icon><book-outline /></n-icon></template>
                    习得技能
                </n-button>
                <n-popconfirm
                    @positive-click="deleteCurrentProfile"
                >
                    <template #trigger>
                    <n-button secondary type="error" :disabled="!profileId">
                        <template #icon><n-icon><trash-outline /></n-icon></template>
                        删除
                    </n-button>
                    </template>
                    确定删除当前角色吗？
                </n-popconfirm>
                
                </n-space>
            </div>
        </div>

        <!-- 新建/编辑角色模态框 -->
        <edit-profile-modal v-model:show="profileModalVisible" :is-editing="isEditing" :profile-id="profileId"/>

        <!-- 习得技能 -->
        <edit-skill-modal v-model:show="skillModalVisible" :profile-id="profileId"/>
    </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, computed } from 'vue'
import { NForm, NFormItem, NInputGroup, NInput, NSwitch, NButton, NText, NTooltip, NSpace, NDivider, NIcon, NPopconfirm, NSelect, useMessage } from 'naive-ui'
import { Add, CreateOutline, TrashOutline, BookOutline } from '@vicons/ionicons5'
import { useConfigStore } from '@/stores/config'
import EditProfileModal from '@/components/Modals/EditProfileModal.vue'
import EditSkillModal from '@/components/Modals/EditSkillModal.vue'
import MSvg from '@/components/MSvg.vue'
import { useChatStore } from '@/stores/chat'
import { useProfileStore } from '@/stores/profiles'


const chatStore = useChatStore()
const profileStore = useProfileStore()
const configStore = useConfigStore()
const message = useMessage()

const profileId = ref()
const archiveModelId = ref(localStorage.getItem('archiveModelId') || null)

watch(() => profileStore.activeProfileId, (val) => {
  profileId.value = val
})

watch(() => configStore.modelList.length, (len) => {
  if (len > 0 && !archiveModelId.value) {
    archiveModelId.value = localStorage.getItem('archiveModelId') || null
  }
})

const archiveModelOptions = computed(() =>
  configStore.modelList.map(m => ({
    label: `${m.name} (${m.type === 'local' ? '本地' : '云端'})`,
    value: m.id
  }))
)

const workspacePath = ref(localStorage.getItem('workspacePath') || '')
async function selectFolder() {
  try {
    const folder = await window.pywebview.api.select_folder()
    if (folder) {
      workspacePath.value = folder
      localStorage.setItem('workspacePath', folder)
      await saveWorkspace(folder)
    }
  } catch {
   message.warning('文件夹选择仅支持桌面环境')
  }
}

const getWorkspace = async () => {
  try {
    const res = await fetch('/api/workspace')
    const data = await res.json()
    if (data.path) {
      workspacePath.value = data.path
      localStorage.setItem('workspacePath', data.path)
    }
  } catch (e) {
    console.warn('获取工作目录失败', e)
  }
}

const saveWorkspace = async (path: string, isMsg: boolean = true) => {
  await fetch('/api/workspace/set', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path })
  }).then(async (res: any) => {
    if (res.ok) {
      if (isMsg)
        message.success('工作目录设置成功')
        localStorage.setItem('workspacePath', path)
    } else {
      const errorData = await res.json()
      message.error(errorData.detail || '工作目录设置失败')
    }
  })
}

// 角色相关状态
const profileModalVisible = ref(false)
const isEditing = ref(false)
const skillModalVisible = ref(false)

const profileOptions = computed(() =>
  profileStore.profiles.map(p => ({ label: p.name, value: p.id }))
)

const openCreateProfile = () => {
  isEditing.value = false
  profileModalVisible.value = true
}

const openEditProfile = () => {
  isEditing.value = true
  profileModalVisible.value = true
}

const openProfileSkills = () => {
  skillModalVisible.value = true
}

const deleteCurrentProfile = async () => {
  if (profileStore.activeProfile) {
    await profileStore.deleteProfile(profileStore.activeProfile.id)
  }
}

const handleProfile = (val: boolean) => {
  localStorage.setItem('enableProfile', val.toString())
}

const saveArchiveModel = async (value: string) => {
  const res = await fetch('/api/memory/archive-model', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      model_id: value
    })
  })
  if (res.ok) {
    message.success('归档模型已设置，后台归档将在下次定时任务时生效')
    localStorage.setItem('archiveModelId', value)
  }
}

const clearArchiveModel = async () => {
  await fetch('/api/memory/archive-model', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({model_id: null})  // 空配置
  })
  message.info('归档模型已清除，后台归档将跳过')
  localStorage.removeItem('archiveModelId') 
}

onMounted(() => {
    profileId.value = profileStore.activeProfileId
    if (!workspacePath.value) {
        getWorkspace()
    }
})
</script>