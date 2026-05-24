import { ref, computed } from 'vue'
import { useConfigStore } from '@/stores/config'


export function useModel() {
  const configStore = useConfigStore()

  const activeModelId = ref()
  const modelName = ref('')

  setTimeout(() => {
    activeModelId.value = configStore.getActiveModelId()
    if (activeModelId.value) configStore.setActiveModel(activeModelId.value)
  }, 120)

  const modelOptions = computed(() =>
    configStore.savedModels.map(m => ({
      label: m.name,
      value: m.id,
    }))
  )

  function switchActiveModel(id: string) {
    configStore.setActiveModel(id)
  }

  return {
    activeModelId,
    modelName,
    modelOptions,
    switchActiveModel,
  }
}