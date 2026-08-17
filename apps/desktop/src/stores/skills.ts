// src/stores/skills.ts
import { defineStore } from 'pinia'
import { ref } from 'vue'


export interface SkillItem {
  id: string
  name: string
  isGlobal: boolean
  description?: string
}

export const useSkillStore = defineStore('skills', () => {
    // 技能相关
    const allSkills = ref<SkillItem[]>([])

    async function loadAllSkills(profileId?: number) {
      try {
          const res = await fetch(`/api/skills/list?profile_id=${profileId}`)
          const data = await res.json()
          allSkills.value = (data || []).map((item: any) => ({
            id: item.id,
            name: item.name || item.id,
            isGlobal: !!item.is_global,
            description: item.description,
          }))
      } catch (e) {}
    }

    function getSkillNameById(id: string): string {
      const skill = allSkills.value.find(s => s.id === id)
      return skill?.name ?? '未知技能'
    }

  return {
    allSkills,
    loadAllSkills,
    getSkillNameById
  }
})