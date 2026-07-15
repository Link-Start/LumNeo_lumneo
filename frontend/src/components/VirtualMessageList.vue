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
      <!-- 增加目录组件 -->
      <MessageToc
        :messages="messages"
        :is-mobile="isMobile"
        :is-dark="isDark"
        @scroll-to="scrollToMessage"
      />
      <div ref="virtualContainerRef" class="virtual-scroller" @scroll="onScroll">
        <div
          :style="{
            height: virtualizer.getTotalSize() + 'px',
            width: isMobile ? '90%' : '80%',
            maxWidth: '1000px',
            position: 'relative',
            margin: '0 auto'
          }"
        >
          <div
            v-for="virtualRow in virtualRows"
            :key="String(virtualRow.key)"
            :ref="(el) => setItemRef(el, virtualRow.index)"
            :data-index="virtualRow.index"
            :style="{
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              transform: `translateY(${virtualRow.start}px)`
            }"
          >
            <!-- 正常消息 -->
            <template v-if="!listItems[virtualRow.index]?.__streaming">
              <div
                v-if="listItems[virtualRow.index] === regeneratingMsg"
                style="height: 1px; overflow: hidden"
              ></div>
              <div
                v-else
                :id="listItems[virtualRow.index].role === 'user' ? 'msg-anchor-' + listItems[virtualRow.index].id : undefined"
                :class="['message-row', listItems[virtualRow.index].role]"
              >
                <!-- 文件附件 -->
                <div 
                  v-if="listItems[virtualRow.index].file_ref" 
                  :class="{ 'has-file': normalizeFileRef(listItems[virtualRow.index].file_ref).length }"
                >
                  <div 
                    v-if="normalizeFileRef(listItems[virtualRow.index].file_ref).length" 
                    class="message-files"
                  >
                    <div
                      v-for="f in normalizeFileRef(listItems[virtualRow.index].file_ref)"
                      :key="f.filename"
                      class="msg-file-item"
                    >
                      <n-image
                        v-if="f.type.startsWith('image/')"
                        width="200"
                        :src="f.url"
                        class="msg-file-img"
                      />
                      <div v-else class="msg-file-other">
                        <n-icon><DocumentOutline /></n-icon>
                        <a :href="f.url" target="_blank">{{ f.filename }}</a>
                      </div>
                    </div>
                  </div>
                </div>
                <!-- 气泡内容 -->
                <div class="bubble">
                  <!-- 用户消息纯文本 -->
                  <template v-if="listItems[virtualRow.index].role === 'user'">
                    <div
                      class="message-content user-content"
                      v-text="listItems[virtualRow.index].content.trim()"
                    ></div>
                  </template>
                  <!-- 助手消息 Markdown -->
                  <template v-else>
                    <div class="message-content" :data-theme="isDark">
                      <MarkdownRender
                        :key="'msg-' + chatId + '-' + listItems[virtualRow.index].id + '-' + virtualRow.index"
                        custom-id="chat"
                        :is-dark="isDark"
                        :themes="['vitesse-light', 'vitesse-dark']"
                        code-block-dark-theme="vitesse-dark"
                        code-block-light-theme="vitesse-light"
                        :content="processMessageContent(listItems[virtualRow.index].content.trim(), false)"
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
                    :class="'message-actions ' + (listItems[virtualRow.index].role === 'assistant' ? 'assistant-actions' : 'user-actions')"
                    v-if="!isLoading || listItems[virtualRow.index] !== regeneratingMsg"
                  >
                    <n-button
                      text
                      class="icon-btn"
                      size="small"
                      title="复制"
                      @click="$emit('copy', listItems[virtualRow.index])"
                    >
                      <template #icon><n-icon><m-svg :name="copySvgName" /></n-icon></template>
                    </n-button>
                    <n-button
                      v-if="listItems[virtualRow.index].role === 'assistant' && virtualRow.index === currentMessages.length - 1"
                      text
                      class="icon-btn"
                      size="small"
                      title="重新生成"
                      @click="$emit('regenerate', listItems[virtualRow.index])"
                    >
                      <template #icon><n-icon><m-svg name="refresh" /></n-icon></template>
                    </n-button>
                    <n-button
                      text
                      class="icon-btn"
                      size="small"
                      title="编辑"
                      @click="$emit('edit', listItems[virtualRow.index])"
                    >
                      <template #icon><n-icon :size="20"><m-svg name="edit" /></n-icon></template>
                    </n-button>
                    <n-popconfirm
                      @positive-click="$emit('delete', listItems[virtualRow.index].id)"
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
                      将删除此消息之后的所有后续对话，<br/>是否继续？
                    </n-popconfirm>
                  </div>
                </div>
              </div>
            </template>
            <!-- 流式输出占位 -->
            <template v-else>
              <div class="streaming-after-item message-row assistant">
                <div v-if="streamingContent" class="bubble streaming">
                  <MarkdownRender
                    :key="'streaming-' + virtualRow.index"
                    custom-id="chat"
                    :is-dark="isDark"
                    :themes="['vitesse-light', 'vitesse-dark']"
                    code-block-dark-theme="vitesse-dark"
                    code-block-light-theme="vitesse-light"
                    :content="processMessageContent(streamingContent, true)"
                    :final="false"
                    mode="chat"
                    :fade="false"
                    :typewriter="false"
                    :max-live-nodes="0"
                    :live-node-buffer="80"
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
import { ref, computed, onMounted, onUnmounted, type PropType, watch, nextTick } from 'vue'
import { NButton, NIcon, NImage, NPopconfirm } from 'naive-ui'
import { DocumentOutline } from '@vicons/ionicons5'
import { MarkdownRender, setCustomComponents, removeCustomComponents, setInfographicLoader } from 'markstream-vue'
import 'markstream-vue/index.css'
import { useVirtualizer } from '@tanstack/vue-virtual'
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
defineEmits<{
  copy: [msg: Message]
  regenerate: [msg: Message]
  edit: [msg: Message]
  delete: [id: number]
}>()
const virtualContainerRef = ref<HTMLElement | null>(null)
const currentMessages = computed(() => props.messages)
const listItems = computed<any>(() => {
  const msgs = currentMessages.value as (Message | { __streaming: boolean })[]
  return props.isLoading ? [...msgs, { __streaming: true }] : msgs
})
const showScrollBtn = ref(false)
const userHasScrolledUp = ref(false)
let scrollTimeout: ReturnType<typeof setTimeout> | null = null
let scrollAnimationId: number | null = null
const SCROLL_STOP_DELAY = 200
// 存储元素引用
const itemRefs = ref<Map<number, HTMLElement>>(new Map())
function setItemRef(el: any, index: number) {
  if (el) {
    itemRefs.value.set(index, el)
  }
}
// 缓动函数
function easeOutCubic(t: number): number {
  return 1 - Math.pow(1 - t, 3)
}
// 滚动事件处理
function onScroll() {
  if (scrollTimeout) clearTimeout(scrollTimeout)
  const atEnd = virtualizer.value?.isAtEnd(80) ?? true
  if (!atEnd && !userHasScrolledUp.value) {
    userHasScrolledUp.value = true
  }
  scrollTimeout = setTimeout(() => {
    const finalAtEnd = virtualizer.value?.isAtEnd(80) ?? true
    showScrollBtn.value = !finalAtEnd
    if (finalAtEnd && userHasScrolledUp.value) {
      userHasScrolledUp.value = false
    }
  }, SCROLL_STOP_DELAY)
}
// 立即回到底部（无动画）
function scrollToLatest() {
  virtualizer.value?.scrollToEnd()
  userHasScrolledUp.value = false
}
// 平滑回到底部（核心修复）
function scrollToLatestSmooth(duration: number = 400) {
  const el: any = virtualContainerRef.value
  if (!el) return
  // 取消之前的动画
  if (scrollAnimationId !== null) {
    cancelAnimationFrame(scrollAnimationId)
    scrollAnimationId = null
  }
  const target = el.scrollHeight - el.clientHeight
  const start = el.scrollTop
  const distance = target - start
  // 已经在底部附近，不需要动画
  if (Math.abs(distance) < 5) {
    userHasScrolledUp.value = false
    return
  }
  // 根据距离动态调整时长
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
// 点击目录跳转到指定消息
function scrollToMessage(msgId: number | string) {
  const index = listItems.value.findIndex((item: any) => String(item.id) === String(msgId))
  if (index !== -1) {
    // 虚拟列表跳转通常比较生硬，这里可以使用 scrollToIndex，然后依赖浏览器的 scroll-behavior 或者手动动画
    // 这里为了简单且稳定，使用 virtualizer 的 index 跳转
    virtualizer.value?.scrollToIndex(index, { align: 'start' })
    userHasScrolledUp.value = false
  }
}
// 虚拟列表配置
const virtualizerOptions: any = computed(() => ({
  count: listItems.value.length,
  getScrollElement: () => virtualContainerRef.value,
  getItemKey: (index: number) => {
    const msg = listItems.value[index]
    if (!msg) return `fallback-${index}`
    return (msg as any).__streaming ? `streaming-temp-${index}` : `msg-${(msg as Message).id || index}`
  },
  estimateSize: (index: number) => {
    const msg = listItems.value[index]
    if (!msg) return 150
    if ((msg as any).__streaming) return 300
    const content = (msg as Message).content || ''
    const codeBlockCount = (content.match(/```/g) || []).length / 2
    const imageCount = (content.match(/!\[.*\]\(.*\)/g) || []).length
    const baseLines = Math.ceil(content.length / 80) + 1
    if ((msg as Message).role === 'user') {
      return Math.min(60 + baseLines * 20, 300)
    }
    let estimate = 120 + baseLines * 26
    estimate += codeBlockCount * 300
    estimate += imageCount * 256
    return Math.max(200, Math.min(estimate, 5000))
  },
  overscan: 15,
  anchorTo: 'end', 
  followOnAppend: true,
  scrollEndThreshold: 80
}))
const virtualizer = useVirtualizer(virtualizerOptions)
const virtualRows = computed(() => virtualizer.value?.getVirtualItems() ?? [])
// 测量逻辑
function measureAll() {
  virtualRows.value.forEach((row: any) => {
    const el = itemRefs.value.get(row.index)
    if (el) {
      virtualizer.value?.measureElement(el)
    }
  })
}
watch(
  () => virtualRows.value,
  async (newRows, oldRows) => {
    await nextTick()
    const oldIndices = new Set(oldRows?.map((r: any) => r.index) || [])
    const newRowsList = newRows.filter((r: any) => !oldIndices.has(r.index))
    if (newRowsList.length > 0) {
      setTimeout(() => {
        newRowsList.forEach((row: any) => {
          const el = itemRefs.value.get(row.index)
          if (el) {
            virtualizer.value?.measureElement(el)
          }
        })
      }, 120)
    }
  },
  { flush: 'post' }
)
watch(
  () => props.streamingContent,
  () => {
    if (props.isLoading && !userHasScrolledUp.value) {
      scrollToLatest()
    }
  }
)
watch(
  () => props.messages.length,
  () => {
    if (!userHasScrolledUp.value) {
      scrollToLatest()
    }
  }
)
const welcomeDark = computed(() =>
  props.showWelcome && props.isDark ? svgWelcomeDark : null
)
const welcomeLight = computed(() =>
  props.showWelcome && !props.isDark ? svgWelcomeLight : null
)
defineExpose({
  scrollToLatest,
  scrollToLatestSmooth,
  showScrollBtn,
  isAtEnd: computed(() => virtualizer.value?.isAtEnd() ?? true)
})
onMounted(() => {
  setInfographicLoader(() => import('@antv/infographic'))
  setCustomComponents('chat', {
    reasoning: ReasoningNode,
    toolcalls: ToolCallsNode,
    tokenusage: TokenUsageNode,
    image: ImageNode,
    link: LinkNode
  })
  setTimeout(() => {
    measureAll()
    scrollToLatest()
  }, 1000)
})
onUnmounted(() => {
  removeCustomComponents('chat')
  if (scrollAnimationId !== null) {
    cancelAnimationFrame(scrollAnimationId)
  }
})
</script>
<style scoped>
/* 样式保持不变 */
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
.virtual-scroller {
  height: 100%;
  flex: 1;
  overflow-y: auto;
  contain: strict;
  scroll-behavior: auto; /* 禁用浏览器默认行为，使用手动控制 */
  overflow-anchor: none;
}
.streaming-after-item {
  width: 100%;
  max-width: 1000px;
  flex: 1;
  margin: 0 auto;
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
.user-content::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.2);
  border-radius: 3px;
}
.user-content::-webkit-scrollbar-thumb:hover {
  background: rgba(0, 0, 0, 0.4);
}
.streaming {
  border: 1px solid var(--accent);
  padding: 12px;
  animation: breathe 0.8s ease-in-out infinite;
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
  background: rgba(0, 0, 0, 0.2);
  color: white;
  border-radius: 6px;
  font-size: 0.9rem;
  cursor: pointer;
}
.msg-file-other a {
  color: white;
}
.msg-file-other:hover {
  background: rgba(0, 0, 0, 0.1);
}
</style>