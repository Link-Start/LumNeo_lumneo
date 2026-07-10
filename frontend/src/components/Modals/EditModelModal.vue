<template>
    <n-modal 
    :show="show" 
    :auto-focus="false" 
    preset="dialog" 
    draggable 
    :mask-closable="false" 
    :loading="configStore.loading" 
    :title="modelId ? '编辑模型' : '添加模型'"
    positive-text="保存" 
    negative-text="取消" 
    @update:show="negativeClick"
    @positive-click="saveModel">
    <n-form :model="modelForm" label-placement="left" label-width="80">
      <n-form-item label="名称" required>
        <n-input v-model:value="modelForm.name" placeholder="例如：我的 GPT-4" />
      </n-form-item>
      <n-form-item label="类型">
        <n-radio-group v-model:value="modelForm.type">
          <n-radio value="local">本地模型</n-radio>
          <n-radio value="online">线上模型</n-radio>
        </n-radio-group>
      </n-form-item>
      <n-form-item label="模型 ID" required>
        <n-space>
          <n-select
            style="width: 240px"
            v-model:value="modelForm.modelName"
            :options="modelOptions"
            filterable
            placeholder="请选择或输入模型名称"
            :loading="modelsLoading"
            @focus="autoFetchModels"
          />
          <n-button @click="fetchModels">获取</n-button>
        </n-space>
      </n-form-item>
      <n-form-item label="Base URL">
        <n-input v-model:value="modelForm.baseUrl" placeholder="http://localhost:1234/v1" />
      </n-form-item>
      <n-form-item label="API Key">
        <n-input v-model:value="modelForm.apiKey" type="password" placeholder="sk-..." />
      </n-form-item>
    </n-form>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, reactive, watch, PropType  } from 'vue'
import { NForm, NFormItem, NRadio, NRadioGroup, NInput, NSelect, NButton, NSpace, NModal, useMessage } from 'naive-ui'
import { useConfigStore, type ModelConfig } from '@/stores/config'

const props = defineProps({
    show: {
        type: Boolean,
        default: false
    },
    modelData: {
        type: Object as PropType<ModelConfig | null>,
        default: null
    },
})

const message = useMessage()
const configStore = useConfigStore()

const modelForm = reactive<{
  name: string
  type: 'local' | 'online'
  modelName?: string
  baseUrl: string
  apiKey: string
}>({
  name: '',
  type: 'local',
  modelName: undefined,
  baseUrl: '',
  apiKey: ''
})

const emit = defineEmits(['update:show'])

const modelId = ref(props.modelData?.id)

const modelOptions = ref<{ label: string; value: string }[]>([])
const modelsLoading = ref(false)

let abortController: AbortController | null = null

async function fetchModels() {
  if (modelsLoading.value) return
  if (!modelForm.baseUrl) {
    message.warning('请先填写 Base URL')
    return
  }
  if (abortController) {
    abortController.abort()
    abortController = null
  }
  abortController = new AbortController()
  modelsLoading.value = true
  try {
    const res = await fetch('/api/model', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        base_url: modelForm.baseUrl,
        api_key: modelForm.apiKey || ''
      }),
      signal: abortController.signal
    })
    const data = await res.json()
    if(data.detail) {
      if (data.detail.indexOf('timed out') !== -1) {
        message.error('请求超时，请检查网络')
      } else {
        message.error("请正确填写API Key")
      }
      modelOptions.value = []
      return
    }
    modelOptions.value = data.map((id: string) => ({ label: id, value: id }))
    if (data.length === 0) {
      message.info('未检测到可用模型，请检查服务或手动输入')
    }
  } catch (e) {
    if (e instanceof Error && e.name === 'AbortError') {
      return
    }
    message.error('获取模型列表失败')
  } finally {
    modelsLoading.value = false
    abortController = null
  }
}

function cancelFetch() {
  if (abortController) {
    abortController.abort()
    abortController = null
  }
}

// 当 baseUrl 或 apiKey 改变时，可自动刷新（可选）
watch(() => [modelForm.baseUrl, modelForm.apiKey], () => {
  modelOptions.value = []
})

// 在打开添加/编辑对话框时，若已有 baseUrl 可自动拉取
watch(() => props.show, (newVal) => {
  if (!newVal) {
    cancelFetch()
  } else {
    if (props.modelData) {
        modelForm.name = props.modelData.name
        modelForm.type = props.modelData.type
        modelForm.modelName = props.modelData.modelName
        modelForm.baseUrl = props.modelData.baseUrl
        modelForm.apiKey = props.modelData.apiKey || ''
    } else {
      modelForm.name = ''
      modelForm.type = 'local'
      modelForm.modelName = undefined
      modelForm.baseUrl = ''
      modelForm.apiKey = ''
    }
  }
})

function autoFetchModels() {
  if (!modelOptions.value.length && modelForm.baseUrl) {
    fetchModels()
  }
}

function saveModel() {
  if ( !modelForm.modelName || (!modelForm.name.trim() || !modelForm.modelName.trim())) {
    message.warning('名称和模型 ID 不能为空')
    return false
  }
  if (props.modelData && props.modelData.id) {
    configStore.updateModel(props.modelData.id, { ...modelForm })
  } else {
    configStore.addModel({ ...modelForm })
  }
  emit('update:show', false)
}


const negativeClick = () => {
    cancelFetch()
    emit('update:show', false)
}
</script>