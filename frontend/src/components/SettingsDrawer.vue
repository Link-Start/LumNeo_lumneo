<template>
  <n-drawer :show="show" :auto-focus="false" @update:show="(val: boolean) => emit('update:show', val)" width="400">
    <n-drawer-content title="设置" closable>
      <n-tabs default-value="model">
        <n-tab-pane name="model" tab="模型管理">
          <n-space vertical>
            <!-- 当前活跃模型指示 -->
            <n-alert v-if="!configStore.activeModel" type="warning" title="尚未选择模型" />
            <div v-else>
              <n-tag type="info" size="small">当前使用：{{ configStore.activeModel.name }}</n-tag>
            </div>

            <n-divider />

            <!-- 模型列表 -->
            <n-list hoverable clickable>
              <n-list-item v-for="model in configStore.savedModels" :key="model.id">
                <template #suffix>
                  <n-space>
                    <n-button text size="small" @click="editModel(model)">编辑</n-button>
                    <n-popconfirm 
                    @positive-click="() => configStore.deleteModel(model.id)" 
                    negative-text="取消" 
                    positive-text="好的"
                    :negative-button-props="{size: 'tiny'}"
                    :positive-button-props="{size: 'tiny'}"
                    >
                      <template #trigger>
                        <n-button text size="small" type="error">删除</n-button>
                      </template>
                      确定删除模型「{{ model.name }}」吗？
                    </n-popconfirm>
                  </n-space>
                </template>
                <div>
                  <n-text strong>{{ model.name }}</n-text>
                  <n-text depth="3"> · {{ model.type === 'local' ? '本地' : '云端' }}</n-text>
                  <br />
                  <n-text depth="3" style="font-size: 0.8rem">{{ model.modelName }}</n-text>
                </div>
              </n-list-item>
            </n-list>

            <n-button type="primary" block @click="openAddModelDialog">添加模型</n-button>
          </n-space>


        </n-tab-pane>

        <!-- 功能设置 -->
        <n-tab-pane name="function" tab="功能设置">
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
              <n-flex>
                <n-input style="width:70%" v-model:value="workspacePath" placeholder="选择或输入目录路径" @change="saveWorkspace(workspacePath)"/>
                <n-button text @click="selectFolder">选择目录</n-button>
              </n-flex>
            </n-form-item>
          </n-form>

          <!-- ========== 角色管理 ========== -->
          <div v-if="chatStore.enableProfile">
            <div>
              <n-divider />
              <h3 style="margin-bottom: 12px;">角色管理</h3>
              <n-select
                v-model:value="profileId"
                :options="profileOptions"
                placeholder="选择角色"
                clearable
                style="margin-bottom: 12px;"
              />
              <n-space>
                <n-button @click="openCreateProfile" size="small" secondary type="primary">新建角色</n-button>
                <n-button @click="openEditProfile" size="small" secondary :disabled="!profileId">编辑</n-button>
                <n-button @click="openProfileSkills" size="small" secondary :disabled="!profileId">习得技能</n-button>
                <n-popconfirm
                  @positive-click="deleteCurrentProfile"
                >
                  <template #trigger>
                    <n-button size="small" secondary type="error" :disabled="!profileId">删除</n-button>
                  </template>
                  确定删除当前角色吗？
                </n-popconfirm>
                
              </n-space>
            </div>
          </div>
        </n-tab-pane>

        <!-- 技能管理 -->
        <n-tab-pane v-if="chatStore.enableProfile" name="skills" tab="技能管理">
          <div style="overflow:auto;height:80vh;">
            <SkillManager />
          </div>
        </n-tab-pane>
      </n-tabs>
      <div style="font-size:.6rem;color:#666;width:100%;text-align:center;position: absolute;left:0;right:10px;bottom: 6px">版本：{{ version }}</div>
    </n-drawer-content>
  </n-drawer>

  <!-- 新增/编辑模型对话框 -->
  <edit-model-modal v-model:show="showModalVisible" :model-data="editingModel" />

  <!-- 新建/编辑角色模态框 -->
  <edit-profile-modal v-model:show="profileModalVisible" :is-editing="isEditing" :profile-id="profileId"/>

  <!-- 习得技能 -->
   <edit-skill-modal v-model:show="skillModalVisible" :profile-id="profileId"/>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, computed } from 'vue'
import {
  NDrawer, NDrawerContent, NForm, NFormItem, NInput, NFlex,
  NSwitch, NButton, NSpace, NDivider, NIcon,
  NTabs, NTabPane, NList, NListItem, NPopconfirm, NTag, NAlert, 
  NSelect, NText, useMessage
} from 'naive-ui'
import SkillManager from '@/components/SkillManager.vue'
import EditProfileModal from '@/components/Modals/EditProfileModal.vue'
import EditModelModal from '@/components/Modals/EditModelModal.vue'
import EditSkillModal from '@/components/Modals/EditSkillModal.vue'
import { useChatStore } from '@/stores/chat'
import { useConfigStore, type ModelConfig } from '@/stores/config'
import { useProfileStore } from '@/stores/profiles'
import mSvg from '@/components/MSvg.vue'


const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{ 'update:show': [value: boolean] }>()

const message = useMessage()
const chatStore = useChatStore()
const configStore = useConfigStore()
const profileStore = useProfileStore()
const version = ref(import.meta.env.VITE_APP_VERSION)
const profileId = ref()

// 对话框状态
const showModalVisible = ref(false)
const editingModel = ref<ModelConfig | null>(null)

watch(() => props.show, (val) => {
  if (val) {
    profileId.value = profileStore.activeProfileId
  }
})

watch(() => profileStore.activeProfileId, (val) => {
  profileId.value = val
})

const handleProfile = (val: boolean) => {
  localStorage.setItem('enableProfile', val.toString())
}

const openAddModelDialog = () => {
  editingModel.value = null
  showModalVisible.value = true
}

const editModel = (model: ModelConfig) => {
  editingModel.value = model
  showModalVisible.value = true
}

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

onMounted(() => {
  configStore.loadModels()
  if (!workspacePath.value) {
    getWorkspace()
  } else {
    saveWorkspace(workspacePath.value, false)
  }
})
</script>

<style scoped>
.n-tab-pane {margin-bottom:20px;}
</style>