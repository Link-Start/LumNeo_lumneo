<template>
    <n-card title="调度控制" hoverable size="small">
        <n-form inline label-placement="left" label-width="auto" label-align="right">
            <n-form-item>
                <template #label>
                    <n-tooltip placement="top" :keep-alive-on-hover="false">
                        <template #trigger>
                            <span class="mode-title">蓝图模式</span>
                        </template>
                        开启后，Agent 生成可编辑的结构化执行计划，经确认后按序执行，确保复杂任务过程透明、结果可控。
                    </n-tooltip>
                </template>
                <n-switch v-model:value="strategyStore.blueprintMode" />
            </n-form-item>
            <n-form-item>
                <template #label>
                    <n-tooltip placement="top" :keep-alive-on-hover="false">
                        <template #trigger>
                            <span class="mode-title">审批模式</span>
                        </template>
                        开启后，工具调用、关键操作等步骤需要人工确认才能继续。由于审批流程天然串行，系统会自动将工具调用并发数锁定为 1，避免并行调用导致的审批状态混乱。
                    </n-tooltip>
                </template>
                <n-switch v-model:value="strategyStore.approvalMode" />
            </n-form-item>
            <n-form-item>
                <template #label>
                    <n-tooltip placement="top" :keep-alive-on-hover="false">
                        <template #trigger>
                            <span class="mode-title">自主决策</span>
                        </template>
                        允许 Agent 在设定的边界内自主选择工具和分支，无需每步都等待用户指令。适用于信任度较高的自动化场景；关闭时则更偏向于“按部就班”的交互式执行。
                    </n-tooltip>
                </template>
                <n-switch v-model:value="strategyStore.autoDecision" />
            </n-form-item>
        </n-form>

        <n-form label-placement="left" label-width="auto" label-align="right">
            <n-form-item>
                <template #label>
                    <n-tooltip placement="left" :keep-alive-on-hover="false">
                        <template #trigger>
                            <span class="mode-title">最大迭代轮次</span>
                        </template>
                        Agent 在执行任务过程中，允许的“思考-行动”循环次数上限。用于防止无限递归或资源耗尽，数值越大，解决问题的可能性越高，但耗时也越长。
                    </n-tooltip>
                </template>
                <n-select v-model:value="strategyStore.maxIterations" :options="iterationOptions" />
            </n-form-item>

            <n-form-item>
                <template #label>
                    <n-tooltip placement="left" :keep-alive-on-hover="false">
                        <template #trigger>
                            <span class="mode-title">最大并行数</span>
                        </template>
                        指单轮迭代中，Agent 可以同时调用的外部工具数量。适当提高数值可显著缩短总响应时间，但会消耗更多系统资源。审批模式下该值被强制设为 1。
                    </n-tooltip>
                </template>
                <n-select v-model:value="strategyStore.maxParallel" :options="parallelOptions" :disabled="strategyStore.approvalMode" />
            </n-form-item>

            <n-form-item>
                <template #label>
                    <n-tooltip placement="left" :keep-alive-on-hover="false">
                        <template #trigger>
                            <span class="mode-title">工具超时</span>
                        </template>
                        每个外部工具调用的最长等待时间（秒）。超时后按失败处理，触发后续的容错机制。设置过短容易误判，设置过长会拖累整体进度。
                    </n-tooltip>
                </template>
                <n-select v-model:value="strategyStore.toolTimeout" :options="timeoutOptions" />
            </n-form-item>
        </n-form>
    </n-card>

    <br>

    <n-card title="容错机制" hoverable size="small">
        <n-form label-placement="left" label-width="auto" label-align="right">
            <n-form-item>
                <template #label>
                    <n-tooltip placement="left" :keep-alive-on-hover="false">
                        <template #trigger>
                            <span class="mode-title">自动重试次数</span>
                        </template>
                        工具调用失败后，系统自动尝试重新执行的次数。0 表示不重试。用于应对临时性故障（如网络抖动、服务短暂不可用）。
                    </n-tooltip>
                </template>
                <n-select v-model:value="strategyStore.retryCount" :options="retryOptions" />
            </n-form-item>

            <n-form-item>
                <template #label>
                    <n-tooltip placement="left" :keep-alive-on-hover="false">
                        <template #trigger>
                            <span class="mode-title">重试间隔</span>
                        </template>
                        相邻两次重试之间的等待时间（秒）。合理间隔可以避免因服务过载而导致的连续失败，也能给下游系统恢复时间。
                    </n-tooltip>
                </template>
                <n-select v-model:value="strategyStore.retryDelay" :options="retryDelayOptions" />
            </n-form-item>

            <n-form-item>
                <template #label>
                    <n-tooltip placement="left" :keep-alive-on-hover="false">
                        <template #trigger>
                            <span class="mode-title">连续失败阈值</span>
                        </template>
                        允许工具调用连续失败的次数上限，超过该值即触发“失败后行为”。
                    </n-tooltip>
                </template>
                <n-select v-model:value="strategyStore.failureThreshold" :options="failureThresholdOptions" />
            </n-form-item>

            <n-form-item>
                <template #label>
                    <n-tooltip placement="left" :keep-alive-on-hover="false">
                        <template #trigger>
                            <span class="mode-title">失败后行为</span>
                        </template>
                        <pre style="font-family: 'v-sans, system-ui, -apple-system, BlinkMacSystemFont">当连续失败达到阈值时，系统采取的应对策略：
- 继续：忽略该次失败，继续执行后续步骤（适合非关键路径）；
- 终止：立即终止整个任务，标记为失败状态。后续所有步骤均不再执行；
- 询问我：暂停任务执行，向用户发出告警并请求下一步指令。用户可选择继续或终止；</pre>
                    </n-tooltip>
                </template>
                <n-select v-model:value="strategyStore.failureBehavior" :options="behaviorOptions" />
            </n-form-item>
        </n-form>
    </n-card>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { NCard, NForm, NFormItem, NSwitch, NSelect, NTooltip } from 'naive-ui'
import { useStrategyStore } from '@/stores/strategy'

const strategyStore = useStrategyStore()
const previousParallel = ref<number | null>(null)

watch(() => strategyStore.approvalMode, (newVal: boolean) => {
    if (newVal) {
        previousParallel.value = strategyStore.maxParallel
        strategyStore.maxParallel = 1
    } else {
        if (previousParallel.value !== null) {
            strategyStore.maxParallel = previousParallel.value
            previousParallel.value = null
        }
    }
})

// 选项定义
const iterationOptions = [
    { label: '5 轮', value: 5 },
    { label: '10 轮', value: 10 },
    { label: '15 轮', value: 15 },
    { label: '20 轮', value: 20 },
    { label: '30 轮', value: 30 },
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
    { label: '继续', value: 'continue' },
    { label: '终止', value: 'stop' },
    { label: '询问我', value: 'ask' }
]
</script>

<style scoped>
.mode-title {
    cursor: help;
    border-bottom: 1px dashed #999
}
</style>