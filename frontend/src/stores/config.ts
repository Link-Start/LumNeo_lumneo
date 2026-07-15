// src/stores/config.ts
import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import { getModels, createModel, updateModel, deleteModel } from '@/api/models'


export interface ModelConfig {
  id: string          // 唯一标识
  name: string        // 显示名称
  type: 'local' | 'online'
  modelName?: string   // 模型 ID
  baseUrl: string     // 本地模型需要，线上可为空
  apiKey: string      // 线上模型需要，本地可为空
}

const ACTIVE_KEY = 'llm_active_model_id'

const fileAcceptedSuffixes = [
  '.txt', '.md', '.markdown', '.rst', '.py', '.js', '.ts', '.jsx', '.vue',
  '.pdf', '.doc', '.docx', '.xlsx', '.tsx', '.csv', '.tsv',
  '.json', '.yaml', '.yml', '.xml', '.html', '.htm', '.css', '.scss', '.less',
  '.sh', '.bash', '.zsh', '.fish', '.ps1', '.bat', '.cmd',
  '.sql', '.c', '.cpp', '.h', '.hpp', '.java', '.go', '.rs', '.rb', '.php',
  '.swift', '.kt', '.scala', '.r', '.m', '.mm', '.pl', '.lua', '.vim',
  '.dockerfile', '.gitignore', '.env', '.ini', '.cfg', '.conf', '.properties',
  '.log', '.svg', '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.ico', '.webp', '.tiff'
]

export const fileConfig = {
  max: 3,
  size: 10, // 10MB
  accept: fileAcceptedSuffixes.join(',')
}

export const useConfigStore = defineStore('config', () => {
  // 从 localStorage 初始化
  const savedModels = ref<ModelConfig[]>([])
  const activeModelId = ref<string|null>(null)
  const themeMode = ref<'light' | 'dark'>('dark')

  localStorage.getItem('themeMode') && (themeMode.value = localStorage.getItem('themeMode') as 'light' | 'dark')

  const savedActive = localStorage.getItem(ACTIVE_KEY)
  if (savedActive && savedModels.value.some(m => m.id === savedActive)) {
    activeModelId.value = savedActive
  } else if (savedModels.value.length > 0) {
    activeModelId.value = savedModels.value[0].id
  }

  watch(activeModelId, (val) => {
    if (val) localStorage.setItem(ACTIVE_KEY, val)
  })

  const activeModel = computed(() => savedModels.value.find(m => m.id === activeModelId.value))
  const loading = ref(false)
  // 从后端加载模型列表
  async function loadModels() {
    loading.value = true
    try {
      const models = await getModels()
      savedModels.value = models
      // 如果当前激活的ID不在列表中，重置为第一个或清空
      // if (activeModelId.value && !savedModels.value.some(m => m.id === activeModelId.value)) {
      //   activeModelId.value = savedModels.value[0]?.id || ''
      //   localStorage.setItem(ACTIVE_KEY, activeModelId.value)
      // }
    } catch (err) {
      console.error('Failed to load models:', err)
    } finally {
      loading.value = false
    }
  }

  // 添加模型
  async function addModel(model: Omit<ModelConfig, 'id'>) {
    const newModel = await createModel(model)
    savedModels.value.push(newModel)
    if (!activeModelId.value) {
      activeModelId.value = newModel.id
      localStorage.setItem(ACTIVE_KEY, activeModelId.value)
    }
  }

  // 更新模型
  async function updateModelById(id: string, updates: Partial<Omit<ModelConfig, 'id'>>) {
    await updateModel(id, updates)
    const idx = savedModels.value.findIndex(m => m.id === id)
    if (idx !== -1) Object.assign(savedModels.value[idx], updates)
  }

  // 删除模型
  async function deleteModelById(id: string) {
    await deleteModel(id)
    savedModels.value = savedModels.value.filter(m => m.id !== id)
    if (activeModelId.value === id && savedModels.value.length > 0) {
      activeModelId.value = savedModels.value[0].id
      localStorage.setItem(ACTIVE_KEY, activeModelId.value)
    } else if (savedModels.value.length === 0) {
      activeModelId.value = ''
      localStorage.setItem(ACTIVE_KEY, '')
    }
  }

  function setActiveModel(id: string) {
    activeModelId.value = id
    localStorage.setItem(ACTIVE_KEY, id)    
  }
  function getActiveModelId() {
    return localStorage.getItem(ACTIVE_KEY) || null
  }

  function toggleTheme() {
    themeMode.value = themeMode.value === 'light' ? 'dark' : 'light'
    localStorage.setItem('themeMode', themeMode.value)
  }

  return {
    savedModels,
    activeModel,
    themeMode,
    loading,
    loadModels,
    addModel,
    updateModel: updateModelById,
    deleteModel: deleteModelById,
    getActiveModelId,
    setActiveModel,
    toggleTheme,
  }
})