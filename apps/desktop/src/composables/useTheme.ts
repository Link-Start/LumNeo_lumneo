// src/composables/useTheme.ts
import { computed } from 'vue'
import { darkTheme } from 'naive-ui'
import type { GlobalThemeOverrides } from 'naive-ui'
import { useConfigStore } from '@/stores/config'

export function useTheme() {
  const configStore = useConfigStore()

  const naiveTheme = computed(() =>
    configStore.themeMode === 'dark' ? darkTheme : null
  )

  const themeOverrides: GlobalThemeOverrides = {
    common: {
      borderRadius: "8px",
      primaryColor: "#6366f1",
      primaryColorHover: "#6366f1",
      primaryColorPressed: "#8b5cf6",
      primaryColorSuppl: "#3967B4FF"
    },
  }

  return { naiveTheme, themeOverrides }
}