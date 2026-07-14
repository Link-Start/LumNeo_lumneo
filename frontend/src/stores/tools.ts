// src/stores/tools.ts
import { defineStore } from 'pinia'
import { ref } from 'vue'


export interface toolConfig {
  title: string        // 名称
  description: string  // 描述
}

export const useToolStore = defineStore('tools', () => {
  const toolsInfo = ref<Record<string, toolConfig>>({})
    async function loadToolsInfo() {
        const res = await fetch('/api/tools-info')
        const data = await res.json()
        toolsInfo.value = data
    }

  return {
    loadToolsInfo,
    toolsInfo
  }
})