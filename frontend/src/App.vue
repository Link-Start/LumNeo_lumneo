<template>
  <n-config-provider :locale="zhCN" :date-locale="dateZhCN" :theme="naiveTheme" :theme-overrides="themeOverrides">
    <n-message-provider>
      <n-dialog-provider>
        <router-view />
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup lang="ts">
import { watch } from 'vue'
import { NConfigProvider, NMessageProvider, NDialogProvider, zhCN, dateZhCN } from 'naive-ui'
import { useTheme } from '@/composables/useTheme'
import { useConfigStore } from '@/stores/config'


const { naiveTheme, themeOverrides } = useTheme()
const configStore = useConfigStore()


// 同步 HTML 属性，使全局 CSS 变量生效
watch(() => configStore.themeMode, (mode) => {
  document.documentElement.setAttribute('theme-mode', mode)
  document.body.setAttribute('style', mode === 'dark' ? 'background:#0b0e14' : 'background:#f8f7fc')
}, { immediate: true })
</script>