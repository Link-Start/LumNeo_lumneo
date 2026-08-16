<template>
  <div
    v-if="!isMobile && tocItems.length > 1"
    class="toc-container"
    :class="{ 'toc-dark': isDark, 'is-hovered': isHovered }"
    @mouseenter="isHovered = true"
    @mouseleave="isHovered = false"
  >
    <!-- 展开后的内容 -->
    <div class="toc-content">
      <div class="toc-title">消息列表</div>
      <div class="toc-list">
        <div
          v-for="item in tocItems"
          :key="item.id"
          class="toc-item"
          @click="handleClick(item.id)"
        >
            <n-ellipsis style="max-width: 180px" :tooltip="{placement: 'left', delay: 500}">
                {{ item.preview }}
            </n-ellipsis>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, type PropType } from 'vue'
import { NEllipsis } from 'naive-ui'
import type { Message } from '@/stores/chat'

const props = defineProps({
  messages: { type: Array as PropType<Message[]>, required: true },
  isMobile: { type: Boolean, default: false },
  isDark: { type: Boolean, default: false }
})

const emit = defineEmits<{
  (e: 'scrollTo', id: number | string): void
}>()

// 控制是否处于鼠标悬浮状态
const isHovered = ref(false)

// 提取用户消息作为目录项
const tocItems = computed(() => {
  return props.messages
    .filter(m => m.role === 'user')
    .map(m => {
      const content = m.content.trim()
      return {
        id: m.id,
        preview: content.slice(0, 30)
      }
    })
})

function handleClick(id: number | string | undefined) {
    if (!id) return
    emit('scrollTo', id)
    // 点击后自动收起，提升体验
    isHovered.value = false
}
</script>

<style scoped>
/* ========== 目录悬浮窗 ========== */
.toc-container {
  position: absolute;
  right: 15px;
  top: 50%;
  width: 36px; /* 默认宽度，只显示图标 */
  height: auto;
  background: rgba(255, 255, 255, 0.75);
  backdrop-filter: blur(10px);
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
  border: 1px solid rgba(0,0,0,0.05);
  z-index: 100;
  overflow: hidden;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  justify-content: center; /* 添加：垂直居中 */
  transform: translateY(-50%);
  transition: width 0.3s ease, padding 0.3s ease, background 0.3s ease;
}

/* 悬浮展开状态 */
.toc-container.is-hovered {
  width: 200px;
  padding: 8px;
  cursor: default;
  height: auto;
}

.toc-dark {
  background: rgba(40, 40, 40, 0.25);
  border: 1px solid rgba(255,255,255,0.05);
  box-shadow: 0 2px 8px rgba(0,0,0,0.3);
}

/* 目录内容区域 */
.toc-content {
  opacity: 0;
  pointer-events: none; /* 收起时不可点击 */
  transition: opacity 0.2s ease 0.1s; /* 延迟一点淡入，等宽度撑开 */
  white-space: nowrap;
}

/* 展开时显示内容 */
.toc-container.is-hovered .toc-content {
  opacity: 1;
  pointer-events: auto;
}

.toc-title {
  font-size: 12px;
  font-weight: bold;
  color: #888;
  padding: 4px 8px;
  margin-bottom: 4px;
  border-bottom: 1px solid rgba(0,0,0,0.05);
}
.toc-dark .toc-title {
  color: #aaa;
  border-bottom: 1px solid rgba(255,255,255,0.1);
}

/* 目录列表 - 修复高度问题 */
.toc-list {
  overflow-y: auto; /* 添加垂直滚动 */
  max-height: 300px; /* 设置最大高度 */
  display: block; /* 改为块级布局 */
  gap: 2px;
  padding-right: 4px; /* 为滚动条留出空间 */
}

/* 自定义滚动条样式 */
.toc-list::-webkit-scrollbar {
  width: 4px;
}
.toc-list::-webkit-scrollbar-track {
  background: rgba(0, 0, 0, 0.02);
  border-radius: 2px;
}
.toc-list::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.05);
  border-radius: 2px;
}
.toc-list::-webkit-scrollbar-thumb:hover {
  background: rgba(0, 0, 0, 0.1);
}

.toc-dark .toc-list::-webkit-scrollbar-track {
  background: rgba(255, 255, 255, 0.02);
}
.toc-dark .toc-list::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.05);
}
.toc-dark .toc-list::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.1);
}

.toc-item {
  padding: 6px 8px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  color: #333;
  min-height: 24px; /* 确保最小高度 */
  line-height: 24px; /* 调整行高 */
  overflow: hidden;
  transition: background 0.2s;
}
.toc-dark .toc-item {
  color: #ddd;
}
.toc-item:hover {
  background: rgba(0, 0, 0, 0.06);
}
.toc-dark .toc-item:hover {
  background: rgba(255, 255, 255, 0.1);
}
</style>
