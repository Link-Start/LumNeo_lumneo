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
      primaryColor: '#4a7cf7',
      borderRadius: '8px',
    },
  }

  return { naiveTheme, themeOverrides }
}