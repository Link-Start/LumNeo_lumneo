<template>
    <n-space vertical>
        <!-- 当前活跃模型指示 -->
        <n-alert v-if="!configStore.activeModel" type="warning" title="尚未选择模型" />
        <div v-else>
            <n-tag type="info" :bordered="false" size="large" style="border-radius:4px;">当前使用：{{ configStore.activeModel.name }} · {{ configStore.activeModel.type === 'local' ? '本地' : '云端' }}</n-tag>
        </div>


        <!-- 模型列表 -->
        <n-list clickable bordered>
            <n-list-item v-for="model in configStore.modelList" :key="model.id">
            <template #suffix>
                <n-space>
                <n-button text size="small" @click="editModel(model)">
                    <template #icon><n-icon><create-outline /></n-icon></template>
                    编辑
                </n-button>
                <n-popconfirm 
                @positive-click="() => configStore.deleteModel(model.id)" 
                negative-text="取消" 
                positive-text="好的"
                :negative-button-props="{size: 'tiny'}"
                :positive-button-props="{size: 'tiny'}"
                >
                    <template #trigger>
                    <n-button text size="small" type="error">
                        <template #icon><n-icon><trash-outline /></n-icon></template>
                        删除
                    </n-button>
                    </template>
                    确定删除模型「{{ model.name }}」吗？
                </n-popconfirm>
                </n-space>
            </template>
            <div>
                <n-text strong>{{ model.name }}</n-text>
                <n-text depth="3"> · {{ model.type === 'local' ? '本地' : '云端' }}</n-text>
                <br />
                <n-text depth="3" style="font-size: 0.8rem">{{ model.modelName }}</n-text>
            </div>
            </n-list-item>
        </n-list>
        <br>
        <n-button type="primary" block size="large" @click="openAddModelDialog">
            <template #icon><n-icon><add /></n-icon></template>
            添加模型
        </n-button>
    </n-space>

    <!-- 新增/编辑模型对话框 -->
    <edit-model-modal v-model:show="showModalVisible" :model-data="editingModel" />
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { NSpace, NAlert, NList, NListItem, NTag, NIcon, NText, NPopconfirm, NButton } from 'naive-ui'
import { Add, CreateOutline, TrashOutline } from '@vicons/ionicons5'
import { useConfigStore, type ModelConfig } from '@/stores/config'
import EditModelModal from '@/components/Modals/EditModelModal.vue'


const configStore = useConfigStore()

// 对话框状态
const showModalVisible = ref(false)
const editingModel = ref<ModelConfig | null>(null)

const openAddModelDialog = () => {
  editingModel.value = null
  showModalVisible.value = true
}

const editModel = (model: ModelConfig) => {
  editingModel.value = model
  showModalVisible.value = true
}
</script>