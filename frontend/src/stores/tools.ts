// src/stores/tools.ts
import { defineStore } from 'pinia'
import { ref } from 'vue'


export interface toolConfig {
  title: string        // 名称
  description: string  // 描述
}

export const useToolStore = defineStore('tools', () => {
  const defaultTools = ['system_get_weather', 'system_read_file', 'system_use_skill', 'system_execute_script']
  const toolsInfo = ref<Record<string, toolConfig>>({})
    async function loadToolsInfo() {
        const res = await fetch('/api/tools-info')
        const data = await res.json()
        toolsInfo.value = data
    }

  return {
    loadToolsInfo,
    toolsInfo,
    defaultTools
  }
})