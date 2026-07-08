<template>
  <div class="message-container">
    <div v-if="!messages.length && showWelcome" class="introduction">
      <div v-if="welcomeDark">
        <component :is="welcomeDark" />
      </div>
      <div v-else>
        <component :is="welcomeLight" />
      </div>
    </div>

    <div v-else class="message-main">
      <!-- 使用抽离出来的目录组件 -->
      <MessageToc
        :messages="messages"
        :is-mobile="isMobile"
        :is-dark="isDark"
        @scroll-to="scrollToMessage"
      />

      <div ref="scrollContainerRef" class="message-scroller" @scroll="onScroll">
        <div ref="messageListRef" class="message-list" :style="{ width: isMobile ? '90%' : '80%', maxWidth: '1000px', margin: '0 auto' }">
          <div
            v-for="(msg, index) in listItems"
            :key="getItemKey(msg, index)"
          >
            <!-- 正常消息 -->
            <template v-if="!msg.__streaming">
              <div v-if="msg === regeneratingMsg" style="height: 1px; overflow: hidden"></div>
              <!-- 给 user 消息加上 id 锚点 -->
              <div v-else :id="msg.role === 'user' ? 'msg-anchor-' + msg.id : undefined" :class="['message-row', msg.role]">
                <div v-if="msg.file_ref" :class="{ 'has-file': normalizeFileRef(msg.file_ref).length }">
                  <!-- 文件附件 -->
                  <div v-if="normalizeFileRef(msg.file_ref).length" class="message-files">
                    <div
                      v-for="f in normalizeFileRef(msg.file_ref)"
                      :key="f.filename"
                      class="msg-file-item"
                    >
                      <n-image v-if="f.type.startsWith('image/')" width="200" :src="f.url" class="msg-file-img" />
                      <div v-else class="msg-file-other">
                        <n-icon><DocumentOutline /></n-icon>
                        <a :href="f.url" target="_blank">{{ f.filename }}</a>
                      </div>
                    </div>
                  </div>
                </div>
                <div class="bubble">
                  <!-- 用户消息纯文本 -->
                  <template v-if="msg.role === 'user'">
                    <div class="message-content user-content" v-text="msg.content.trim()"></div>
                  </template>
                  <!-- 助手消息 Markdown -->
                  <template v-else-if="msg.role === 'assistant'">
                    <div class="message-content" :data-theme="isDark">
                      <MarkdownRender
                        :key="'msg-' + chatId + '-' + msg.id + '-' + index"
                        custom-id="chat"
                        :is-dark="isDark"
                        :themes="['vitesse-light', 'vitesse-dark']"
                        code-block-dark-theme="vitesse-dark"
                        code-block-light-theme="vitesse-light"
                        :content="processMessageContent(msg.content.trim(), false)"
                        :final="true"
                        :fade="false"
                        :typewriter="false"
                        :max-live-nodes="320"
                        :live-node-buffer="80"
                        :custom-html-tags="customHtmlTags"
                      />
                    </div>
                  </template>

                  <!-- 操作按钮 -->
                  <div
                    :class="'message-actions ' + (msg.role === 'assistant' ? 'assistant-actions' : 'user-actions')"
                    v-if="!isLoading || msg !== regeneratingMsg"
                  >
                    <n-button text class="icon-btn" size="small" title="复制" @click="$emit('copy', msg)">
                      <template #icon><n-icon><m-svg :name="copySvgName" /></n-icon></template>
                    </n-button>
                    <n-button
                      v-if="msg.role === 'assistant' && index === currentMessages.length - 1"
                      text class="icon-btn" size="small" title="重新生成"
                      @click="$emit('regenerate', msg)"
                    >
                      <template #icon><n-icon><m-svg name="refresh" /></n-icon></template>
                    </n-button>
                    <n-button text class="icon-btn" size="small" title="编辑" @click="$emit('edit', msg)">
                      <template #icon><n-icon :size="20"><m-svg name="edit" /></n-icon></template>
                    </n-button>
                    <n-popconfirm
                      @positive-click="$emit('delete', msg.id)"
                      :negative-button-props="{ size: 'tiny' }"
                      :positive-button-props="{ size: 'tiny' }"
                      negative-text="取消"
                      positive-text="好的"
                    >
                      <template #trigger>
                        <n-button text class="icon-btn" size="small" title="删除">
                          <template #icon><n-icon :size="22"><m-svg name="del" /></n-icon></template>
                        </n-button>
                      </template>
                      确定要删除这条消息吗？
                    </n-popconfirm>
                  </div>
                </div>
              </div>
            </template>

            <!-- 流式输出占位（列表最后一项） -->
            <template v-else>
              <div class="streaming-after-item message-row assistant">
                <div v-if="streamingContent" class="bubble streaming">
                  <MarkdownRender
                    :key="'streaming-' + index"
                    custom-id="chat"
                    :is-dark="isDark"
                    :themes="['vitesse-light', 'vitesse-dark']"
                    code-block-dark-theme="vitesse-dark"
                    code-block-light-theme="vitesse-light"
                    :content="processMessageContent(streamingContent, true)"
                    :final="false"
                    :typewriter="false"
                    :max-live-nodes="0"
                    :viewport-priority="false"
                    :defer-nodes-until-visible="false"
                    :batch-rendering="true"
                    :custom-html-tags="customHtmlTags"
                  />
                </div>
                <svgLoading v-else />
              </div>
            </template>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, type PropType, nextTick, watch } from 'vue'
import { NButton, NIcon, NImage, NPopconfirm } from 'naive-ui'
import { DocumentOutline } from '@vicons/ionicons5'
import { MarkdownRender, setCustomComponents, removeCustomComponents, setInfographicLoader } from 'markstream-vue'
import 'markstream-vue/index.css'
import type { Message } from '@/stores/chat'
import { normalizeFileRef, processMessageContent } from '@/utils/message'
import svgWelcomeDark from '@/components-svg/svgWelcomeDark.vue'
import svgWelcomeLight from '@/components-svg/svgWelcomeLight.vue'
import svgLoading from '@/components-svg/svgLoading.vue'
import mSvg from '@/components/MSvg.vue'
import ReasoningNode from '@/components/CustomNodes/ReasoningNode.vue'
import ToolCallsNode from '@/components/CustomNodes/ToolCallsNode.vue'
import TokenUsageNode from '@/components/CustomNodes/TokenUsageNode.vue'
import ImageNode from '@/components/CustomNodes/ImageNode.vue'
import LinkNode from '@/components/CustomNodes/LinkNode.vue'
// 引入目录组件 (请根据实际路径调整)
import MessageToc from '@/components/MessageToc.vue'

const customHtmlTags = ['reasoning', 'toolcalls', 'tokenusage']

const props = defineProps({
  chatId: { type: String, default: 'nochat' },
  messages: { type: Array as PropType<Message[]>, required: true },
  isMobile: { type: Boolean, required: false },
  isLoading: { type: Boolean, required: true },
  streamingContent: { type: String, default: '' },
  regeneratingMsg: { type: Object as PropType<Message | null>, default: null },
  isDark: { type: Boolean, required: true },
  showWelcome: { type: Boolean, default: false },
  copySvgName: { type: String, default: 'copy' }
})

const emit = defineEmits<{
  copy: [msg: Message]
  regenerate: [msg: Message]
  edit: [msg: Message]
  delete: [id: number]
}>()

const scrollContainerRef = ref<HTMLElement | null>(null)
const messageListRef = ref<HTMLElement | null>(null)

const currentMessages = computed(() => props.messages)

const listItems = computed<any>(() => {
  const msgs = currentMessages.value as (Message | { __streaming: boolean })[]
  return props.isLoading ? [...msgs, { __streaming: true }] : msgs
})

const showScrollBtn = ref(false)
let scrollTimeout: ReturnType<typeof setTimeout> | null = null
const SCROLL_END_THRESHOLD = 80

function isAtEnd(): boolean {
  if (!scrollContainerRef.value) return true
  const el = scrollContainerRef.value
  return el.scrollHeight - el.scrollTop - el.clientHeight < SCROLL_END_THRESHOLD
}

const userHasScrolledUp = ref(false)

// 滚动事件处理
function onScroll() {
    if (scrollTimeout) clearTimeout(scrollTimeout)
    const atEnd = isAtEnd()
    showScrollBtn.value = !atEnd
    if (!atEnd && !userHasScrolledUp.value) {
        userHasScrolledUp.value = true
    } else if (atEnd && userHasScrolledUp.value) {
        userHasScrolledUp.value = false
    }
}

// 主动回到底部
function scrollToLatest() {
  if (!scrollContainerRef.value) return
  scrollContainerRef.value.scrollTop = scrollContainerRef.value.scrollHeight
  userHasScrolledUp.value = false
}

let scrollAnimationId: number | null = null

// 缓动函数：开始快，结束慢，感觉自然
function easeOutCubic(t: number): number {
  return 1 - Math.pow(1 - t, 3)
}

// 平滑回到底部
function scrollToLatestSmooth(duration: number = 400) {
  const el: any = scrollContainerRef.value
  if (!el) return

  // 取消之前的动画，防止重复触发导致冲突
  if (scrollAnimationId !== null) {
    cancelAnimationFrame(scrollAnimationId)
    scrollAnimationId = null
  }

  const target = el.scrollHeight - el.clientHeight
  const start = el.scrollTop
  const distance = target - start

  // 已经在底部附近（5px 内），不需要动画
  if (Math.abs(distance) < 5) {
    userHasScrolledUp.value = false
    return
  }

  // 根据距离动态调整时长：短距离快，长距离慢
  const dynamicDuration = Math.min(
    600,
    Math.max(250, Math.abs(distance) * 0.8)
  )
  const finalDuration = duration || dynamicDuration
  const startTime = performance.now()

  function animate(currentTime: number) {
    const elapsed = currentTime - startTime
    const progress = Math.min(elapsed / finalDuration, 1)
    const eased = easeOutCubic(progress)

    el.scrollTop = start + distance * eased

    if (progress < 1) {
      scrollAnimationId = requestAnimationFrame(animate)
    } else {
      scrollAnimationId = null
      userHasScrolledUp.value = false
    }
  }
  scrollAnimationId = requestAnimationFrame(animate)
}

// 接收子组件触发的滚动事件，平滑滚动到指定消息
function scrollToMessage(msgId: number | string) {
  const el = document.getElementById(`msg-anchor-${msgId}`)
  const container: any = scrollContainerRef.value
  if (!el || !container) return

  // 取消正在进行的滚动动画
  if (scrollAnimationId !== null) {
    cancelAnimationFrame(scrollAnimationId)
    scrollAnimationId = null
  }

  // 计算相对于滚动容器的偏移量
  const containerRect = container.getBoundingClientRect()
  const elRect = el.getBoundingClientRect()
  const offsetTop = elRect.top - containerRect.top + container.scrollTop - 20 // 减去 20px 留点顶部边距

  const start = container.scrollTop
  const distance = offsetTop - start

  if (Math.abs(distance) < 5) {
    container.scrollTop = offsetTop
    return
  }

  const dynamicDuration = Math.min(800, Math.max(300, Math.abs(distance) * 0.5))
  const startTime = performance.now()

  function animate(currentTime: number) {
    const elapsed = currentTime - startTime
    const progress = Math.min(elapsed / dynamicDuration, 1)
    const eased = easeOutCubic(progress)

    container.scrollTop = start + distance * eased

    if (progress < 1) {
      scrollAnimationId = requestAnimationFrame(animate)
    } else {
      scrollAnimationId = null
    }
  }
  scrollAnimationId = requestAnimationFrame(animate)
}

// 生成 item key
function getItemKey(msg: any, index: number|string): string {
  if (msg.__streaming) return `streaming-${index}`
  return `msg-${msg.id || index}`
}

const welcomeDark = computed(() => props.showWelcome && props.isDark ? svgWelcomeDark : null)
const welcomeLight = computed(() => props.showWelcome && !props.isDark ? svgWelcomeLight : null)

defineExpose({
  scrollToLatest,
  showScrollBtn,
  scrollToLatestSmooth,
  isAtEnd: computed(() => isAtEnd()),
})

// 监听消息变化，自动滚动到底部
watch(() => props.messages.length, async () => {
  await nextTick()
  if (!userHasScrolledUp.value) {
    scrollToLatest()
  }
})

// 监听流式内容变化，自动滚动到底部
watch(() => props.streamingContent, async () => {
  if (props.isLoading && !userHasScrolledUp.value) {
    await nextTick()
    scrollToLatest()
  }
})

let resizeObserver: ResizeObserver | null = null

onMounted(() => {
  setInfographicLoader(() => import('@antv/infographic'))
  setCustomComponents('chat', {
    reasoning: ReasoningNode,
    toolcalls: ToolCallsNode,
    tokenusage: TokenUsageNode,
    image: ImageNode,
    link: LinkNode
  })
  // 初始化时滚动到底部
  nextTick(() => scrollToLatest())

  if (scrollContainerRef.value) {
    resizeObserver = new ResizeObserver(() => {
      // 尺寸变化时，重新计算是否在底部
      if (!userHasScrolledUp.value) {
        scrollToLatest()
      } else {
        showScrollBtn.value = !isAtEnd()
      }
    })
    resizeObserver.observe(scrollContainerRef.value)
    if (messageListRef.value) {
      resizeObserver.observe(messageListRef.value)
    }
  }
})

onUnmounted(() => {
  removeCustomComponents('chat')
  resizeObserver?.disconnect()
})
</script>

<style scoped>
/* ========== 消息容器 ========== */
.message-container {
  flex: 1;
  overflow: hidden;
  padding: 20px 0;
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.message-scroller {
  height: 100%;
  flex: 1;
  overflow-y: auto;
  scroll-behavior: auto;
}
.message-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding-bottom: 20px;
}
.streaming-after-item {
  width: 100%;
  max-width: 1000px;
  flex: 1;
  margin: 0 auto;
}

/* 简单的淡入淡出动画 */
.fade-enter-active, .fade-leave-active {
  transition: opacity 0.3s ease, transform 0.3s ease;
}
.fade-enter-from, .fade-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(10px);
}
.message-main {
  width: 100%;
  overflow: hidden;
  position: relative;
  flex: 1;
  display: flex;
  flex-direction: column;
}
.message-row {
  display: flex;
}
.message-row.user {
  flex-direction: column;
  align-items: flex-end;
  margin-top: 10px;
}
.message-row.assistant {
  justify-content: flex-start;
  padding-bottom: 20px;
}

.bubble {
  border-radius: 8px;
  backdrop-filter: blur(6px);
  word-break: break-word;
  position: relative;
  font-size: 16px;
  line-height: 1.8;
}
.assistant .bubble {
  width: 100%;
}
.user .bubble {
  max-width: 75%;
  background: var(--accent-gradient);
  color: white;
  border: none;
  margin-top: 10px;
  margin-bottom: 40px;
}
.user-content {
  max-height: 200px;
  padding: 12px;
  overflow-y: auto;
  white-space: pre-wrap;
}
.user-content::-webkit-scrollbar-thumb { background: rgba(0,0,0,.2); border-radius: 3px; }
.user-content::-webkit-scrollbar-thumb:hover { background: rgba(0,0,0,.4); }

.streaming {
  border: 1px solid var(--accent);
  padding: 12px;
  animation: breathe .8s ease-in-out infinite;
}

@keyframes breathe {
  0% {
    box-shadow: -0 0 4px rgba(0, 0, 0, 0.1);
  }
  50% {
    box-shadow: 0 0 12px var(--accent);
  }
  100% {
    box-shadow: 0 0 4px rgba(0, 0, 0, 0.1);
  }
}

.message-actions {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.2s;
  position: absolute;
  left: 0;
}
.user-actions {
  right: 0;
  margin-top: 16px;
}
.message-row:hover .message-actions {
  opacity: 1;
  pointer-events: unset;
}
.msg-file-img {
  border-radius: 8px;
  cursor: pointer;
}
.msg-file-other {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: var(--border-color);
  color: var(--text-primary);
  border-radius: 6px;
  font-size: 0.9rem;
  cursor: pointer;
}
.msg-file-other a {
  color: var(--text-primary);
}
.msg-file-other:hover {
  background: var(--border-color-hover);
}
</style>
