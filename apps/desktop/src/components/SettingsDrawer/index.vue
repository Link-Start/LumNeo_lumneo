<template>
  <n-drawer :show="show" :auto-focus="false" @update:show="(val: boolean) => emit('update:show', val)" width="520">
    <n-drawer-content title="系统设置" closable>
      <n-tabs v-model:value="activeTab">
        <n-tab-pane name="model" tab="模型管理">
          <ModelManager/>
        </n-tab-pane>

        <n-tab-pane name="collaboration" tab="模型协作">
          <CollaborationManager/>
        </n-tab-pane>

        <!-- 执行策略 -->
        <n-tab-pane name="strategy" tab="执行策略">
          <StrategyManager />
        </n-tab-pane>

        <!-- 技能管理 -->
        <n-tab-pane name="skills" tab="技能管理">
          <div style="overflow:auto;height:80vh;">
            <SkillsManager />
          </div>
        </n-tab-pane>

        <!-- 功能设置 -->
        <n-tab-pane name="function" tab="功能设置">
          <SettingsManager/>
        </n-tab-pane>
      </n-tabs>
    </n-drawer-content>
  </n-drawer>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { NDrawer, NDrawerContent, NTabs, NTabPane } from 'naive-ui'
import ModelManager from './ModelManager.vue'
import CollaborationManager from './CollaborationManager.vue'
import StrategyManager from './StrategyManager.vue'
import SkillsManager from './SkillsManager.vue'
import SettingsManager from './SettingsManager.vue'


const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{ 'update:show': [value: boolean] }>()
const activeTab = ref('model')
</script>

<style scoped>
.n-tab-pane {margin-bottom:20px;}
</style>