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
      <div ref="virtualContainerRef" class="virtual-scroller" @scroll="onScroll">
        <div :style="{ height: virtualizer.getTotalSize() + 'px', width: isMobile ? '90%' : '80%', maxWidth: '1000px', position: 'relative', margin: '0 auto' }">
          <div v-for="virtualRow in virtualRows"
            :key="String(virtualRow.key)"
            :ref="(el) => setItemRef(el, virtualRow.index)"
            :data-index="virtualRow.index"
            :style="{ position: 'absolute', top: 0, left: 0, width: '100%', transform: `translateY(${virtualRow.start}px)` }"
          >
            <!-- 正常消息 -->
            <template  v-if="!listItems[virtualRow.index]?.__streaming">
              <div v-if="listItems[virtualRow.index] === regeneratingMsg" style="height: 1px; overflow: hidden"></div>
              <div v-else :class="['message-row', listItems[virtualRow.index].role]">
                <div class="bubble" :class="{ 'has-file': normalizeFileRef(listItems[virtualRow.index].file_ref).length }">
                  <!-- 文件附件 -->
                  <div v-if="normalizeFileRef(listItems[virtualRow.index].file_ref).length" class="message-files">
                    <div
                      v-for="f in normalizeFileRef(listItems[virtualRow.index].file_ref)"
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

                  <!-- 用户消息纯文本 -->
                  <template v-if="listItems[virtualRow.index].role === 'user'">
                    <div class="message-content user-content" v-text="listItems[virtualRow.index].content.trim()"></div>
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
                    <n-button text class="icon-btn" size="small" title="复制" @click="$emit('copy', listItems[virtualRow.index])">
                      <template #icon><n-icon><m-svg :name="copySvgName" /></n-icon></template>
                    </n-button>
                    <n-button
                      v-if="listItems[virtualRow.index].role === 'assistant' && virtualRow.index === currentMessages.length - 1"
                      text class="icon-btn" size="small" title="重新生成"
                      @click="$emit('regenerate', listItems[virtualRow.index])"
                    >
                      <template #icon><n-icon><m-svg name="refresh" /></n-icon></template>
                    </n-button>
                    <n-button text class="icon-btn" size="small" title="编辑" @click="$emit('edit', listItems[virtualRow.index])">
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
import { MarkdownRender, setCustomComponents, removeCustomComponents } from 'markstream-vue'
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
let scrollTimeout: ReturnType<typeof setTimeout> | null = null
const SCROLL_STOP_DELAY = 200

// 关键修复：用 Map 存储元素引用，key 是 index
const itemRefs = ref<Map<number, HTMLElement>>(new Map())

function setItemRef(el: any, index: number) {
  if (el) {
    itemRefs.value.set(index, el)
  }
}

// 滚动事件处理
function onScroll() {
   // 滚动过程中，如果当前已经在底部附近，先不显示按钮
  // 等滚动完全停止后再做最终判断
  if (scrollTimeout) clearTimeout(scrollTimeout)
  scrollTimeout = setTimeout(() => {
    const atEnd = virtualizer.value?.isAtEnd(80) ?? true
    showScrollBtn.value = !atEnd
  }, SCROLL_STOP_DELAY)
}

// 主动回到底部：强制开启跟随并滚动
function scrollToLatest() {
  virtualizer.value?.scrollToEnd()
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
  // 关键修复：使用默认的 measureElement，让 ResizeObserver 处理
  // 不覆盖 measureElement，使用库内部的实现
  overscan: 15,
  anchorTo: 'end',
  followOnAppend: true,
  scrollEndThreshold: 80
}))

const virtualizer = useVirtualizer(virtualizerOptions)

const virtualRows = computed(() => virtualizer.value?.getVirtualItems() ?? [])

// 关键修复：measureAll 只测量当前在视口内的元素
function measureAll() {
  // 只测量当前虚拟列表返回的元素
  virtualRows.value.forEach((row: any) => {
    const el = itemRefs.value.get(row.index)
    if (el) {
      virtualizer.value?.measureElement(el)
    }
  })
}

// 关键修复：监听虚拟行变化，新元素进入视口时自动测量
watch(() => virtualRows.value, async (newRows, oldRows) => {
  await nextTick()

  // 找出新进入视口的元素
  const oldIndices = new Set(oldRows?.map((r: any) => r.index) || [])
  const newRowsList = newRows.filter((r: any) => !oldIndices.has(r.index))

  if (newRowsList.length > 0) {
    // 延迟测量，等 MarkdownRender 完成
    setTimeout(() => {
      newRowsList.forEach((row: any) => {
        const el = itemRefs.value.get(row.index)
        if (el) {
          virtualizer.value?.measureElement(el)
        }
      })
    }, 120)
  }
}, { flush: 'post' })

const welcomeDark = computed(() => props.showWelcome && props.isDark ? svgWelcomeDark : null)
const welcomeLight = computed(() => props.showWelcome && !props.isDark ? svgWelcomeLight : null)

defineExpose({ 
    scrollToLatest,
    showScrollBtn,
    isAtEnd: computed(() => virtualizer.value?.isAtEnd() ?? true),
})

onMounted(() => {
  setCustomComponents('chat', {
    reasoning: ReasoningNode,
    toolcalls: ToolCallsNode,
    tokenusage: TokenUsageNode,
    image: ImageNode,
    link: LinkNode
  })
  // 初始测量
  setTimeout(() => {
    measureAll()
  }, 1000)
})

onUnmounted(() => {
  removeCustomComponents('chat')
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
.virtual-scroller {
  height: 100%;
  flex: 1;
  overflow-y: auto; /* 滚动条出现在这里 */
  contain: strict;
  scroll-behavior: auto;
  overflow-anchor: none;
}
.streaming-after-item {
  width: 100%;
  max-width:1000px;
  flex: 1;
  margin:0 auto;
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
  width:100%;
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
  justify-content: flex-end;
}
.message-row.assistant {
  justify-content: flex-start;
  padding-bottom: 20px;
}


.bubble {
  padding: 6px;
  border-radius: 12px;
  backdrop-filter: blur(6px); /* 添加模糊效果 */
  word-break: break-word; /* 允许长单词换行 */
  position: relative;
  font-size: 16px;
  line-height:1.8;
}
.assistant .bubble {
  width: 100%;
}
.user .bubble {
  max-width: 75%;
  background: var(--accent-gradient);
  color: white;
  border: none;
  margin-top: 30px;
  margin-bottom: 40px;
}
.user-content {
  max-height: 200px;
  padding: 6px;
  overflow-y: auto;
  white-space: pre-wrap;
}
.user-content::-webkit-scrollbar-thumb { background: rgba(0,0,0,.2); border-radius: 3px; }
.user-content::-webkit-scrollbar-thumb:hover { background: rgba(0,0,0,.4); }

.streaming {
  border-left: 3px solid var(--accent);
  animation: breathe 1.2s ease-in-out infinite;
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
  padding: 6px;
  background: rgba(0,0,0,0.1);
  color: white;
  border-radius: 6px;
  font-size: 0.9rem;
}
.msg-file-other a {
  color: white;
}
.msg-file-other:hover {
  background: rgba(0,0,0,0.2);
}
</style>