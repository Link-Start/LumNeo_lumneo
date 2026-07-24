<template>
    <n-card title="调度控制" hoverable size="small">
        <n-form inline label-placement="left" label-width="auto" label-align="right">
            <n-form-item label="蓝图模式">
                <n-switch v-model:value="strategyStore.blueprintMode" />
            </n-form-item>
            <n-form-item label="审批模式">
                <n-switch v-model:value="strategyStore.approvalMode" />
            </n-form-item>
            <n-form-item label="自主决策">
                <n-switch v-model:value="strategyStore.autoDecision" />
            </n-form-item>
        </n-form>
        <n-form label-placement="left" label-width="auto" label-align="right">
            <n-form-item label="最大迭代轮次">
                <n-select v-model:value="strategyStore.maxIterations" :options="iterationOptions" />
            </n-form-item>
            <n-form-item label="最大并行数">
                <n-select v-model:value="strategyStore.maxParallel" :options="parallelOptions" />
            </n-form-item>
            <n-form-item label="工具超时">
                <n-select v-model:value="strategyStore.toolTimeout" :options="timeoutOptions" />
            </n-form-item>
        </n-form>
    </n-card>
    <br>
    <n-card title="容错机制" hoverable size="small">
        <n-form label-placement="left" label-width="auto" label-align="right">
            <n-form-item label="自动重试次数">
                <n-select v-model:value="strategyStore.retryCount" :options="retryOptions" />
            </n-form-item>
            <n-form-item label="重试间隔">
                <n-select v-model:value="strategyStore.retryDelay" :options="retryDelayOptions" />
            </n-form-item>
            <n-form-item label="连续失败阈值">
                <n-select v-model:value="strategyStore.failureThreshold" :options="failureThresholdOptions" />
            </n-form-item>
            <n-form-item label="失败后行为">
                <n-select v-model:value="strategyStore.failureBehavior" :options="behaviorOptions" />
            </n-form-item>
        </n-form>
    </n-card>
</template>

<script setup lang="ts">
import { NCard, NForm, NFormItem, NSwitch, NSelect } from 'naive-ui'
import { useStrategyStore } from '@/stores/strategy'


const strategyStore = useStrategyStore()

// 选项定义
const iterationOptions = [
    { label: '5 轮', value: 5 },
    { label: '10 轮', value: 10 },
    { label: '15 轮', value: 15 },
    { label: '20 轮', value: 20 },
    { label: '25 轮', value: 25 },
    { label: '30 轮', value: 30 },
    { label: '40 轮', value: 40 },
    { label: '50 轮', value: 50 }
]

const parallelOptions = [
    { label: '1', value: 1 },
    { label: '2', value: 2 },
    { label: '3', value: 3 },
    { label: '5', value: 5 },
    { label: '8', value: 8 },
    { label: '10', value: 10 }
]

const timeoutOptions = [
    { label: '10 秒', value: 10 },
    { label: '30 秒', value: 30 },
    { label: '60 秒', value: 60 },
    { label: '120 秒', value: 120 },
    { label: '300 秒', value: 300 },
    { label: '600 秒', value: 600 }
]

const retryOptions = [
    { label: '0 次', value: 0 },
    { label: '1 次', value: 1 },
    { label: '2 次', value: 2 },
    { label: '3 次', value: 3 },
    { label: '5 次', value: 5 }
]

const retryDelayOptions = [
    { label: '0 秒', value: 0 },
    { label: '1 秒', value: 1 },
    { label: '2 秒', value: 2 },
    { label: '3 秒', value: 3 },
    { label: '5 秒', value: 5 },
    { label: '10 秒', value: 10 }
]

const failureThresholdOptions = [
    { label: '1 次', value: 1 },
    { label: '2 次', value: 2 },
    { label: '3 次', value: 3 },
    { label: '5 次', value: 5 },
    { label: '10 次', value: 10 }
]

const behaviorOptions = [
    { label: '继续执行', value: 'continue' },
    { label: '停止并提示', value: 'stop' },
    { label: '询问用户', value: 'ask' }
]
</script>