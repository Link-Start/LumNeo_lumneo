<template>
  <div class="strategy-details">
    <!-- 基础配置 -->
    <div class="section-title">协作策略配置</div>

    <n-flex vertical size="small">
      <n-flex justify="space-between" align="center">
        <span class="label">策略模式</span>
        <n-tag size="small" :bordered="false" type="primary">{{ collaborationStore.strategyLabel }}</n-tag>
      </n-flex>

      <n-flex justify="space-between" align="center">
        <span class="label">主模型</span>
        <span class="value">{{ primaryModelText }}</span>
      </n-flex>

      <n-flex justify="space-between" align="center">
        <span class="label">副模型</span>
        <span class="value">{{ secondaryModelText }}</span>
      </n-flex>

      <n-flex v-if="collaborationStore.strategy === 'hybrid'" justify="space-between" align="center">
        <span class="label">主模型占比</span>
        <span class="value">{{ collaborationStore.primary_ratio }}%</span>
      </n-flex>

      <n-flex v-if="collaborationStore.strategy !== 'primary'" justify="space-between" align="center">
        <span class="label">故障回退</span>
        <n-tag size="small" :bordered="false" :type="collaborationStore.fallback_enabled ? 'success' : 'default'">
          {{ collaborationStore.fallback_enabled ? '已开启' : '已关闭' }}
        </n-tag>
      </n-flex>
    </n-flex>

    <!-- 智能检测 -->
    <template v-if="!['primary', 'secondary', 'hybrid'].includes(collaborationStore.strategy)">
      <div class="section-title" style="margin-top: 14px;">智能检测规则</div>

      <n-flex vertical size="small">
        <!-- 复杂度 -->
        <n-flex justify="space-between" align="center">
          <span class="label">复杂度检测</span>
          <n-flex align="center" :size="6">
            <span v-if="collaborationStore.conditions.enable_complexity_detect" class="hint">
              阈值 {{ (collaborationStore.conditions.complexity_threshold * 100).toFixed(0) }}%
            </span>
            <n-tag size="small" :bordered="false" :type="collaborationStore.conditions.enable_complexity_detect ? 'success' : 'default'">
              {{ collaborationStore.conditions.enable_complexity_detect ? '已开启' : '已关闭' }}
            </n-tag>
          </n-flex>
        </n-flex>

        <!-- 长度 -->
        <n-flex justify="space-between" align="center">
          <span class="label">长度检测</span>
          <n-flex align="center" :size="6">
            <span v-if="collaborationStore.conditions.enable_length_detect" class="hint">
              {{ collaborationStore.conditions.message_length_threshold }} 字
            </span>
            <n-tag size="small" :bordered="false" :type="collaborationStore.conditions.enable_length_detect ? 'success' : 'default'">
              {{ collaborationStore.conditions.enable_length_detect ? '已开启' : '已关闭' }}
            </n-tag>
          </n-flex>
        </n-flex>

        <!-- 关键词 -->
        <n-flex justify="space-between" align="center">
          <span class="label">关键词触发</span>
          <n-tag size="small" :bordered="false" :type="collaborationStore.conditions.enable_keyword_detect ? 'success' : 'default'">
            {{ collaborationStore.conditions.enable_keyword_detect ? '已开启' : '已关闭' }}
          </n-tag>
        </n-flex>

        <!-- 工具优先 -->
        <n-flex justify="space-between" align="center">
          <span class="label">工具调用优先</span>
          <n-tag size="small" :bordered="false" type="info">
            {{ collaborationStore.conditions.tool_heavy_priority === 'primary' ? '主模型' : '副模型' }}
          </n-tag>
        </n-flex>
      </n-flex>

      <!-- 关键词规则 -->
      <div v-if="collaborationStore.conditions.keyword_triggers.length" class="keyword-section">
        <div class="section-title" style="margin-bottom: 8px;">关键词规则</div>
        <n-flex wrap :size="6" justify="center">
          <n-tag
            v-for="(rule, idx) in collaborationStore.conditions.keyword_triggers"
            :key="idx"
            size="small"
            :bordered="false"
            :type="rule.target === 'primary' ? 'info' : 'warning'"
          >
            {{ rule.keyword }} → {{ rule.target === 'primary' ? '主' : '副' }}
          </n-tag>
        </n-flex>
      </div>
    </template>

    <!-- 固定模式提示 -->
    <div v-else class="fixed-mode-tip">
      <span v-if="collaborationStore.strategy !== 'hybrid'">当前为固定模式，始终使用 「 {{ collaborationStore.strategy === 'primary' ? '主模型' : '副模型' }} 」</span>
      <span v-else>当前为混合占比模式，按照占比随机分配</span>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { computed } from 'vue'
import { NFlex, NTag } from 'naive-ui'
import { useConfigStore } from '@/stores/config'
import { useCollaborationStore } from '@/stores/collaboration'

const configStore = useConfigStore()
const collaborationStore = useCollaborationStore()

// 安全的模型信息获取
const modelMap = computed(() => {
  return configStore.modelList.reduce((acc, cur) => {
    acc[cur.id] = cur
    return acc
  }, {} as Record<string, any>)
})

function getModelLabel(modelId: string|null): string {
  const model = modelId ? modelMap.value[modelId] : null
  if (!model) return '未设置'
  const typeLabel = model.type === 'local' ? '本地' : '云端'
  return `${model.name} · ${typeLabel}`
}

const primaryModelText = computed(() => getModelLabel(collaborationStore.primary_model_id))
const secondaryModelText = computed(() => getModelLabel(collaborationStore.secondary_model_id))
</script>

<style scoped>
.strategy-details {
  padding: 10px 14px;
  font-size: 13px;
  line-height: 1.8;
  min-width: 260px;
  max-width: 320px;
}

.section-title {
  font-weight: 600;
  margin-bottom: 8px;
  font-size: 14px;
  border-bottom: 1px solid var(--border-color);
  padding-bottom: 6px;
}

.label {
  color: var(--text-secondary);
}

.value {
  font-size: 12px;
}

.hint {
  color: var(--text-secondary);
  font-size: 12px;
}

.keyword-section {
  margin-top: 12px;
}

.fixed-mode-tip {
  margin-top: 20px;
  color: grey;
  text-align: center;
  font-size: 12px;
}
</style>