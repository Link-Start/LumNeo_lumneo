<template>
  <n-config-provider :theme-overrides="themeOverrides">
    <n-message-provider>
      <HomeView />
    </n-message-provider>
  </n-config-provider>
</template>

<script setup lang="ts">
import { watch } from 'vue'
import { NConfigProvider, NMessageProvider, GlobalThemeOverrides } from 'naive-ui'
import { useConfigStore } from '@/stores/config'
import HomeView from '@/views/HomeView.vue'


const configStore = useConfigStore()

const themeOverrides: GlobalThemeOverrides = {
  "common": {
    "primaryColor": "#6366f1",
    "primaryColorHover": "#6366f1",
    "primaryColorPressed": "#8b5cf6",
    "primaryColorSuppl": "#3967B4FF"
  },
}

// 同步 HTML 属性，使全局 CSS 变量生效
watch(() => configStore.themeMode, (mode) => {
  document.documentElement.setAttribute('theme-mode', mode)
}, { immediate: true })
</script>