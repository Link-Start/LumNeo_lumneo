import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export interface Profile {
  id: number
  name: string
  tools: string[]
  profile_prompt: string
}

export const useProfileStore = defineStore('profile', () => {
  const profiles = ref<Profile[]>([])
  const activeProfileId = ref<number | null>(null)

  async function loadProfiles() {
    const res = await fetch('/api/profiles/')
    profiles.value = await res.json()
    // 若无当前角色或当前角色不存在，默认选择第一个
    if (!activeProfileId.value || !profiles.value.find(p => p.id === activeProfileId.value)) {
      if (profiles.value.length > 0) activeProfileId.value = profiles.value[0].id
    }
  }

  async function createProfile(name: string, tools: string[] = [], profile_prompt: string = '') {
    const res = await fetch('/api/profiles/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, tools, profile_prompt })
    })
    const newProfile = await res.json()
    profiles.value.push(newProfile)
    activeProfileId.value = newProfile.id
    return newProfile
  }

  async function updateProfile(id: number, name: string, tools: string[], profile_prompt: string = '') {
    await fetch(`/api/profiles/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, tools, profile_prompt })
    })
    const profile = profiles.value.find(p => p.id === id)
    if (profile) {
      profile.name = name
      profile.tools = tools
    }
  }

  async function deleteProfile(id: number) {
    await fetch(`/api/profiles/${id}`, { method: 'DELETE' })
    profiles.value = profiles.value.filter(p => p.id !== id)
    if (activeProfileId.value === id) {
      activeProfileId.value = profiles.value[0]?.id ?? null
    }
  }

  const activeProfile = computed(() => profiles.value.find(p => p.id === activeProfileId.value))

  // 当前角色启用的工具名称集合
  const activeToolsSet = computed(() => {
    const p = activeProfile.value
    return p ? new Set(p.tools) : new Set<string>()
  })

  return { profiles, activeProfileId, activeProfile, activeToolsSet, loadProfiles, createProfile, updateProfile, deleteProfile }
})