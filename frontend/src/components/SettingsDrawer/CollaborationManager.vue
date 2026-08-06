<template>
    <div>
        <n-space vertical>
            <!-- 顶部开关 -->
            <n-card size="small" :bordered="false" style="background: transparent">
                <n-space align="center" justify="space-between">
                    <n-space align="center" :size="12">
                        <n-icon size="28" :depth="2"><git-compare-outline /></n-icon>
                        <div>
                            <n-text strong style="font-size: 16px">模型协作调度</n-text>
                            <n-text depth="3" style="font-size: 12px; display: block">根据任务特征自动在主模型与副模型间切换，实现智能负载均衡</n-text>
                        </div>
                    </n-space>
                    <n-switch v-model:value="store.enabled" size="large" @update:value="handleToggle">
                        <template #checked>已启用</template>
                        <template #unchecked>已关闭</template>
                    </n-switch>
                </n-space>
            </n-card>

            <n-divider style="margin: 4px 0" />

            <!-- 未启用时的空状态 -->
            <n-empty v-if="!store.enabled" description="协作调度已关闭，所有请求将使用默认模型">
            <template #icon>
                <n-icon size="48" :depth="3"><flash-off-outline /></n-icon>
            </template>
            <template #extra>
                <n-text depth="3" style="font-size: 13px">
                开启后，系统将根据消息复杂度、关键词、长度等条件自动选择最适合的模型
                </n-text>
            </template>
            </n-empty>

            <!-- 启用后的配置面板 -->
            <n-space v-else vertical :size="20">
                <!-- 模型配对 -->
                <n-card title="模型配对" size="small" hoverable>
                    <n-grid :cols="2" :x-gap="16">
                    <n-gi>
                        <n-form-item label="主模型" label-placement="top" :show-feedback="false" required>
                        <n-select
                            v-model:value="store.primary_model_id"
                            :options="modelOptions"
                            placeholder="选择主模型"
                            @update:value="store.setPrimaryModel"
                        />
                        </n-form-item>
                        <n-text depth="3" style="font-size: 12px">
                        默认首选模型，当无特殊触发条件或副模型不可用时使用
                        </n-text>
                    </n-gi>
                    <n-gi>
                        <n-form-item label="副模型" label-placement="top" :show-feedback="false">
                        <n-select
                            v-model:value="store.secondary_model_id"
                            :options="secondaryModelOptions"
                            placeholder="选择副模型（可选）"
                            clearable
                        />
                        </n-form-item>
                        <n-text depth="3" style="font-size: 12px">
                        辅助模型，用于分流复杂任务或实现负载均衡
                        </n-text>
                    </n-gi>
                    </n-grid>
                </n-card>

                <!-- 调度策略 -->
                <n-card title="调度策略" size="small" hoverable>
                    <n-space justify="center">
                        <n-radio-group v-model:value="store.strategy" :disabled="!store.enabled" size="large">
                            <n-radio-button value="auto">智能调度</n-radio-button>
                            <n-radio-button value="primary">固定主模型</n-radio-button>
                            <n-radio-button value="secondary">固定副模型</n-radio-button>
                            <n-radio-button value="hybrid">混合占比</n-radio-button>
                        </n-radio-group>
                    </n-space>

                    <!-- 策略说明 -->
                    <n-alert type="info" :show-icon="false" :bordered="false" style="margin-top: 16px; background: rgba(64,128,255,0.06)">
                    <n-text style="font-size: 13px">{{ strategyDesc.title }}</n-text>
                    <n-text depth="3" style="font-size: 12px; display: block; margin-top: 4px">
                        {{ strategyDesc.desc }}
                    </n-text>
                    </n-alert>

                    <!-- 混合模式：占比滑块 -->
                    <n-collapse-transition :show="store.strategy === 'hybrid'">
                    <n-card size="small" embedded :bordered="false" style="margin-top: 16px; background: rgba(125,125,125,0.04)">
                        <n-space vertical>
                        <div style="display: flex; justify-content: space-between; align-items: center">
                            <n-text style="font-size: 14px">主模型调用占比</n-text>
                            <n-text strong style="font-size: 20px; color: var(--primary-color)">
                            {{ store.primary_ratio }}%
                            </n-text>
                        </div>
                        <n-slider v-model:value="store.primary_ratio" :step="5" :marks="{0: '0%', 25: '25%', 50: '50%', 75: '75%', 100: '100%'}" />
                        <n-space justify="space-between" style="margin-top: 8px">
                            <n-statistic label="主模型" :value="`${store.primary_ratio}%`" size="small" />
                            <n-statistic label="副模型" :value="`${100 - store.primary_ratio}%`" size="small" />
                        </n-space>
                        </n-space>
                    </n-card>
                    </n-collapse-transition>
                </n-card>

                <!-- 自动模式：触发条件 -->
                <n-collapse-transition :show="store.strategy === 'auto'">
                    <n-card title="智能触发条件" size="small" hoverable>
                    <n-space vertical :size="16">

                        <!-- 检测项总开关 -->
                        <n-space justify="space-around" align="center" :size="20" style="flex-wrap: wrap;">
                            <n-space align="center" :size="6">
                                <n-switch v-model:value="store.conditions.enable_complexity_detect" size="small" />
                                <n-text style="font-size: 13px">复杂度检测</n-text>
                            </n-space>
                            <n-space align="center" :size="6">
                                <n-switch v-model:value="store.conditions.enable_length_detect" size="small" />
                                <n-text style="font-size: 13px">长度检测</n-text>
                            </n-space>
                            <n-space align="center" :size="6">
                                <n-switch v-model:value="store.conditions.enable_keyword_detect" size="small" />
                                <n-text style="font-size: 13px">关键词检测</n-text>
                            </n-space>
                        </n-space>
                        <n-divider style="margin: 8px 0" />

                        <!-- 复杂度阈值 -->
                        <n-form-item label="复杂度阈值" label-placement="left" label-width="120" :show-feedback="false">
                        <template #label>
                            <n-tooltip placement="top" :keep-alive-on-hover="false">
                            <template #trigger>
                                <span style="cursor: help; border-bottom: 1px dashed #999">复杂度阈值</span>
                            </template>
                            当消息复杂度超过此阈值时，优先使用副模型处理。复杂度基于代码块、任务步骤、专业术语等因素估算。
                            </n-tooltip>
                        </template>
                        <n-slider v-model:value="store.conditions.complexity_threshold" :step="0.05" :max="1" :min="0" style="max-width: 300px" :disabled="!store.conditions.enable_complexity_detect" />
                        <n-text strong style="margin-left: 16px; min-width: 50px">
                            {{ (store.conditions.complexity_threshold * 100).toFixed(0) }}%
                        </n-text>
                        </n-form-item>

                        <!-- 消息长度阈值 -->
                        <n-form-item label="长度阈值" label-placement="left" label-width="120" :show-feedback="false">
                        <template #label>
                            <n-tooltip placement="top" :keep-alive-on-hover="false">
                            <template #trigger>
                                <span style="cursor: help; border-bottom: 1px dashed #999">长度阈值</span>
                            </template>
                            当单条消息超过此字符数时，优先使用副模型处理长文本。
                            </n-tooltip>
                        </template>
                        <n-input-number
                            v-model:value="store.conditions.message_length_threshold"
                            :min="100"
                            :max="10000"
                            :step="100"
                            size="medium"
                            style="width: 140px"
                            :disabled="!store.conditions.enable_length_detect"
                        />
                        <n-text depth="3" style="margin-left: 8px">字符</n-text>
                        </n-form-item>

                        <!-- 工具调用优先级 -->
                        <n-form-item label="工具任务优先" label-placement="left" label-width="120" :show-feedback="false">
                        <template #label>
                            <n-tooltip placement="top" :keep-alive-on-hover="false">
                            <template #trigger>
                                <span style="cursor: help; border-bottom: 1px dashed #999">工具任务优先</span>
                            </template>
                            当请求启用工具调用时，优先使用指定模型处理工具密集型任务。
                            </n-tooltip>
                        </template>
                        <n-radio-group v-model:value="store.conditions.tool_heavy_priority" size="medium">
                            <n-radio value="primary">
                            <n-space align="center" :size="4">
                                <span>主模型</span>
                            </n-space>
                            </n-radio>
                            <n-radio value="secondary">
                            <n-space align="center" :size="4">
                                <span>副模型</span>
                            </n-space>
                            </n-radio>
                        </n-radio-group>
                        </n-form-item>

                        <n-divider style="margin: 8px 0" />

                        <!-- 关键词触发规则 -->
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px">
                            <n-text strong style="font-size: 14px">关键词触发规则</n-text>
                            <n-button text size="small" type="primary" @click="store.addKeywordRule" :disabled="!store.conditions.enable_keyword_detect">
                                <template #icon><n-icon><add /></n-icon></template>
                                添加规则
                            </n-button>
                        </div>

                        <n-empty v-if="!store.conditions.keyword_triggers.length" description="暂无规则，点击上方按钮添加" size="small" />

                        <div v-show="store.conditions.enable_keyword_detect">
                            <n-space v-for="(rule, idx) in store.conditions.keyword_triggers" :key="idx" align="center" :size="12" style="margin-bottom: 8px">
                            <n-input v-model:value="rule.keyword" size="medium" :maxlength="6" placeholder="输入关键词" style="width: 160px" :disabled="!store.conditions.enable_keyword_detect" />
                            <n-text depth="3">命中后使用</n-text>
                            <n-select
                                v-model:value="rule.target"
                                size="medium"
                                style="width: 120px"
                                :options="[
                                { label: '主模型', value: 'primary' },
                                { label: '副模型', value: 'secondary' }
                                ]"
                                :disabled="!store.conditions.enable_keyword_detect"
                            />
                            <n-button text size="small" type="error" @click="store.removeKeywordRule(idx)" :disabled="!store.conditions.enable_keyword_detect">
                                <n-icon size="18"><trash-outline /></n-icon>
                            </n-button>
                            </n-space>
                        </div>
                    </n-space>
                    </n-card>
                </n-collapse-transition>

                <!-- 回退与容错 -->
                <n-card v-if="store.strategy !== 'primary'" title="容错设置" size="small" hoverable>
                    <n-form-item label="故障回退" label-placement="left" label-width="100">
                    <n-switch v-model:value="store.fallback_enabled">
                        <template #checked>启用</template>
                        <template #unchecked>关闭</template>
                    </n-switch>
                    <template #feedback>
                        <span style="font-size: 12px; color: #888">当副模型调用失败或不可用时，自动回退到主模型继续处理</span>
                    </template>
                    </n-form-item>
                </n-card>

                <!-- 策略预览 -->
                <n-card title="策略预览" size="small" hoverable style="background: rgba(64,128,255,0.03);margin-bottom:10px;">
                    <n-space vertical :size="16" v-if="!['primary', 'secondary'].includes(store.strategy)">
                        <n-input
                            v-model:value="previewMessage"
                            type="textarea"
                            placeholder="输入一条测试消息，查看当前协作策略会选择哪个模型..."
                            :autosize="{ minRows: 3, maxRows: 5 }"
                            size="medium"
                        />
                        <n-button size="medium" type="primary" secondary block @click="runPreview" :loading="previewLoading">
                            <template #icon><n-icon><flash-outline /></n-icon></template>
                            运行策略模拟
                        </n-button>

                        <n-collapse-transition :show="!!previewResult">
                            <n-alert v-if="previewResult" :type="previewResult.selected ? 'success' : 'warning'" :bordered="false">
                            <n-space vertical :size="8">
                                <n-text strong style="font-size: 14px">{{ previewResult.reason }}</n-text>
                                <n-divider style="margin: 4px 0" />
                                <n-space v-if="previewResult.selected" align="center" :size="16">
                                <n-tag size="large" :bordered="false" :type="previewResult.selected.type === 'local' ? 'success' : 'info'">
                                    {{ previewResult.selected.name }}
                                </n-tag>
                                <n-text depth="3" style="font-size: 12px">
                                    {{ previewResult.selected.id === store.primary_model_id ? '主模型' : '副模型' }}
                                </n-text>
                                </n-space>
                                <n-space v-else>
                                <n-tag size="large" :bordered="false" type="warning">未选择模型</n-tag>
                                </n-space>
                            </n-space>
                            </n-alert>
                        </n-collapse-transition>
                    </n-space>
                    <n-empty :description="`当前为固定模式，始终使用 「 ${store.strategy === 'primary' ? '主模型' : '副模型'} 」`" v-else />
                </n-card>
            </n-space>
        </n-space>
    </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import {
  NSpace, NCard, NSwitch, NFormItem, NSelect, NRadioGroup, NRadioButton, NRadio,
  NSlider, NInputNumber, NInput, NDivider, NGrid, NGi, NCollapseTransition,
  NAlert, NText, NIcon, NButton, NTag, NStatistic, NEmpty, NTooltip,
  useMessage } from 'naive-ui'
import { GitCompareOutline, FlashOutline, FlashOffOutline, Add, TrashOutline } from '@vicons/ionicons5'
import { useConfigStore } from '@/stores/config'
import { useCollaborationStore, type CollabStrategy } from '@/stores/collaboration'

const configStore = useConfigStore()
const store = useCollaborationStore()
const message = useMessage()

const previewLoading = ref(false)
const previewMessage = ref('')
const previewResult = ref<any>(null)

// ========== 计算属性 ==========
const modelOptions = computed(() =>
  configStore.modelList.map(m => ({
    label: `${m.name} (${m.type === 'local' ? '本地' : '云端'})`,
    value: m.id,
    type: m.type
  }))
)

const secondaryModelOptions = computed(() =>
  modelOptions.value.filter(m => m.value !== store.primary_model_id)
)

const strategyDesc = computed(() => {
  const descs: Record<CollabStrategy, { title: string; desc: string }> = {
    auto: {
      title: '智能调度',
      desc: '系统根据消息复杂度、关键词、长度和工具调用需求自动选择最适合的模型。适合大多数场景。'
    },
    primary: {
      title: '固定主模型',
      desc: '所有请求始终使用主模型，协作策略仅作为备用。适合对稳定性要求高的场景。'
    },
    secondary: {
      title: '固定副模型',
      desc: '所有请求始终使用副模型。适合需要集中使用副模型算力的场景。'
    },
    hybrid: {
      title: '混合占比调度',
      desc: '按照设定的主/副模型占比随机分配请求。适合负载均衡和成本优化场景。'
    }
  }
  return descs[store.strategy] || descs.auto
})

// ========== 方法 ==========
const handleToggle = async (val: boolean) => {
  if (!val) {
    message.info('协作调度已关闭')
  }
}

const runPreview = async () => {
  if (!previewMessage.value.trim()) {
    message.warning('请输入测试消息')
    return
  }
  previewLoading.value = true
  try {
    const res = await fetch('/api/collaboration/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: previewMessage.value,
        collaboration: store.payload
      })
    })
    const data = await res.json()
    previewResult.value = data
  } catch (e) {
    message.error('预览请求失败')
  } finally {
    previewLoading.value = false
  }
}
</script>