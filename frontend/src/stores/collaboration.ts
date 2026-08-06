// src/stores/collaboration.ts
import { createDiscreteApi } from 'naive-ui'
import { defineStore } from 'pinia'


  const { message } = createDiscreteApi(['message'])

export type CollabStrategy = 'auto' | 'primary' | 'secondary' | 'hybrid'
export type ModelTypeTarget = 'primary' | 'secondary'

export interface KeywordTrigger {
  keyword: string
  target: ModelTypeTarget
}

export interface CollabConditions {
  complexity_threshold: number
  tool_heavy_priority: ModelTypeTarget
  keyword_triggers: KeywordTrigger[]
  message_length_threshold: number
  enable_complexity_detect: boolean
  enable_keyword_detect: boolean
  enable_length_detect: boolean
}

export interface CollaborationState {
  enabled: boolean
  primary_model_id: string
  secondary_model_id: string | null
  strategy: CollabStrategy
  primary_ratio: number
  fallback_enabled: boolean
  conditions: CollabConditions
}

const DEFAULT_CONDITIONS: CollabConditions = {
  complexity_threshold: 0.6,
  tool_heavy_priority: 'primary',
  keyword_triggers: [
    { keyword: '代码', target: 'primary' },
    { keyword: '分析', target: 'secondary' },
    { keyword: '总结', target: 'primary' }
  ],
  message_length_threshold: 500,
  enable_complexity_detect: true,
  enable_keyword_detect: true,
  enable_length_detect: true
}

export const useCollaborationStore = defineStore('collaboration', {
  state: (): CollaborationState => ({
    enabled: false,
    primary_model_id: '',
    secondary_model_id: null,
    strategy: 'auto',
    primary_ratio: 70,
    fallback_enabled: true,
    conditions: { ...DEFAULT_CONDITIONS }
  }),

  getters: {
    isActive: (state) => state.enabled && !!state.primary_model_id,
    
    strategyLabel: (state) => {
      const labels: Record<CollabStrategy, string> = {
        auto: '智能调度',
        primary: '固定主模型',
        secondary: '固定副模型',
        hybrid: '混合占比'
      }
      return labels[state.strategy]
    },

    // 用于发送给后端的完整 payload
    payload: (state): any => {
      if (!state.enabled || !state.primary_model_id) return null
      const validTriggers = state.conditions.keyword_triggers.filter(r => r.keyword.trim())
      return {
        enabled: state.enabled,
        primary_model_id: state.primary_model_id,
        secondary_model_id: state.secondary_model_id,
        strategy: state.strategy,
        primary_ratio: state.primary_ratio,
        fallback_enabled: state.fallback_enabled,
        conditions: {
          complexity_threshold: state.conditions.complexity_threshold,
          tool_heavy_priority: state.conditions.tool_heavy_priority,
          keyword_triggers: validTriggers,
          message_length_threshold: state.conditions.message_length_threshold,
          enable_complexity_detect: state.conditions.enable_complexity_detect,
          enable_keyword_detect: state.conditions.enable_keyword_detect,
          enable_length_detect: state.conditions.enable_length_detect
        }
      }
    }
  },

  actions: {

    // 重置为默认值
    reset() {
      this.enabled = false
      this.primary_model_id = ''
      this.secondary_model_id = null
      this.strategy = 'auto'
      this.primary_ratio = 70
      this.fallback_enabled = true
      this.conditions = { ...DEFAULT_CONDITIONS }
    },

    // 更新主模型时自动清理冲突的副模型
    setPrimaryModel(id: string) {
      this.primary_model_id = id
      if (this.secondary_model_id === id) {
        this.secondary_model_id = null
      }
    },

    // 添加/删除关键词规则
    addKeywordRule() {
      if(this.conditions.keyword_triggers.length < 9) {
        this.conditions.keyword_triggers.push({ keyword: '', target: 'primary' })
      } else {
        message.warning('最多只能添加9条规则')
      }
    },
    removeKeywordRule(idx: number) {
      this.conditions.keyword_triggers.splice(idx, 1)
    }
  },

  persist: {
    key: 'lumneo_collaboration',
    // 只持久化核心配置，预览结果等不需要
    pick: [
      'enabled',
      'primary_model_id',
      'secondary_model_id',
      'strategy',
      'primary_ratio',
      'fallback_enabled',
      'conditions'
    ]
  }
})