// src/stores/strategy.ts
import { defineStore } from 'pinia'


export interface StrategyConfig {
  blueprintMode: boolean
  approvalMode: boolean
  autoDecision: boolean
  maxIterations: number
  maxParallel: number
  toolTimeout: number
  retryCount: number
  retryDelay: number
  failureThreshold: number
  failureBehavior: 'continue' | 'stop' | 'ask'
}

export const useStrategyStore = defineStore('strategy', {
  state: (): StrategyConfig => ({
    blueprintMode: false,
    approvalMode: true,
    autoDecision: false,
    maxIterations: 10,
    maxParallel: 5,
    toolTimeout: 30,
    retryCount: 2,
    retryDelay: 1,
    failureThreshold: 3,
    failureBehavior: 'continue'
  }),
  actions: {
    updateConfig(payload: Partial<StrategyConfig>) {
      Object.assign(this, payload)
    },
    // 获取后端所需的参数格式
    getBackendParams() {
      return {
        blueprint_mode: this.blueprintMode,
        approval_mode: this.approvalMode,
        auto_decision: this.autoDecision,
        max_iterations: this.maxIterations,
        max_parallel: this.maxParallel,
        tool_timeout: this.toolTimeout,
        retry_count: this.retryCount,
        retry_delay: this.retryDelay,
        failure_threshold: this.failureThreshold,
        failure_behavior: this.failureBehavior
      }
    }
  },
  persist: {
    key: 'strategy-config'
  }
})