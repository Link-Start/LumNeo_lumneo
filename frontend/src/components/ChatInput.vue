<template>
  <div class="compose-area">
    <!-- 滚动到底部按钮 -->
    <transition name="fade">
      <n-button v-if="showScrollBtn" circle class="scroll-to-bottom-btn" @click="$emit('scrollBottom')">
        <n-icon size="22"><ArrowDownOutline /></n-icon>
        <div v-show="isLoading" class="rotate-circle"></div>
      </n-button>
    </transition>

    <!-- 文件预览列表 -->
    <div v-if="uploadedFiles.length" class="file-preview-list">
      <div v-for="(f, index) in uploadedFiles" :key="f.filename" class="file-preview-item">
        <div class="file-info">
          <img v-if="f.type.startsWith('image/')" :src="f.url" class="file-thumb" />
          <div v-else class="file-name">
            <n-icon><DocumentOutline /></n-icon>
            <span>{{ f.filename }}</span>
          </div>
          <n-button text class="file-close" @click="$emit('removeFile', index)">
            <template #icon><m-svg name="close" /></template>
          </n-button>
        </div>
      </div>
    </div>

    <!-- 重新生成提示 -->
    <div v-if="showRegenerateHint" class="compose-input-container">
      <div style="width:100%;text-align:center;position:absolute;top:-30px;">
        <n-button text @click="$emit('regenerateCurrent')">
          <template #icon><n-icon size="22"><m-svg name="wave" /></n-icon></template>
          点击重新生成AI响应
        </n-button>
      </div>
    </div>

    <!-- 输入框 -->
    <div class="compose-input-container">
      <n-input
        :value="modelValue"
        @update:value="emit('update:modelValue', $event)"
        type="textarea"
        name="talk"
        placeholder="今天要做点什么呢？"
        :autosize="{ minRows: 4, maxRows: 6 }"
        @keydown.enter.exact.prevent="handleSend"
        :disabled="disabled"
        class="compose-input"
        :class="{ 'jelly-effect': isJellyActive }"
        @focus="triggerJelly"
        @paste="onPaste"
      />
    </div>

    <!-- 工具栏 -->
    <div class="compose-tools-tar">
      <n-button
        v-if="showDeepThink"
        round
        secondary
        class="compose-thinking"
        :type="selected ? 'primary' : 'default'"
        @click="$emit('update:selected', !selected)"
      >
        深度思考
      </n-button>

      <n-upload
        :disabled="disabled"
        v-model:file-list="internalFileList"
        multiple
        :max="maxFiles"
        :accept="fileAccept"
        :show-file-list="false"
        @change="handleUploadChange"
        @before-upload="beforeUpload"
        @update:file-list="(files: UploadFileInfo[]) => emit('update:fileList', files)"
      >
        <n-button text class="upload-btn" title="上传文件">
          <template #icon><n-icon><m-svg name="attach" /></n-icon></template>
        </n-button>
      </n-upload>

      <n-button v-if="!isLoading" class="send-btn" @click="handleSend"
        strong secondary type="primary"
        :disabled="!modelValue.trim().length"
      >
        <template #icon><n-icon><m-svg name="send"/></n-icon></template>
      </n-button>
      <n-button v-else class="send-btn" @click="$emit('stop')" strong secondary type="primary">
        <template #icon><n-icon><m-svg name="stop"/></n-icon></template>
      </n-button>
    </div>

    <div class="compose-disclaimer">内容由 AI 生成，未必正确无误</div>
  </div>
</template>

<script setup lang="ts">
import { ref, PropType } from 'vue'
import { NButton, NInput, NUpload, NIcon, type UploadFileInfo } from 'naive-ui'
import { ArrowDownOutline, DocumentOutline } from '@vicons/ionicons5'
import mSvg from '@/components/MSvg.vue'


const props = defineProps({
  modelValue: { type: String, required: true },
  isLoading: { type: Boolean, required: true },
  disabled: { type: Boolean, default: false },
  uploadedFiles: { type: Array<{ filename: string; type: string; url: string }>, default: () => [] },
  selected: { type: Boolean, default: false },
  showScrollBtn: { type: Boolean, default: false },
  showRegenerateHint: { type: Boolean, default: false },
  showDeepThink: { type: Boolean, default: false },
  maxFiles: { type: Number, default: 10 },
  fileAccept: { type: String, default: '' },
  fileList: {
    type: Array as PropType<UploadFileInfo[]>,
    default: () => []
  },
  beforeUpload: { type: Function as unknown as () => (data: { file: UploadFileInfo; fileList: UploadFileInfo[] }) => boolean | Promise<boolean>, default: undefined },
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  send: []
  stop: []
  scrollBottom: []
  removeFile: [index: number]
  regenerateCurrent: []
  'update:selected': [value: boolean]
  'filesPaste': [files: File[]]
  'uploadChange': [options: { file: UploadFileInfo; fileList: UploadFileInfo[] }]
  'update:fileList': [files: UploadFileInfo[]]
}>()

// 内部 n-upload 文件列表（不暴露给父组件）
const internalFileList = ref<UploadFileInfo[]>([])

function handleUploadChange(options: { file: UploadFileInfo; fileList: UploadFileInfo[] }) {
  emit('uploadChange', options)
}

function handleSend() {
  if (props.disabled) return
  emit('send')
}

// 粘贴处理
function onPaste(e: ClipboardEvent) {
  if (!props.disabled) {
    const clipboardData = e.clipboardData
    if (!clipboardData) return
    const items = clipboardData.items
    if (!items || items.length === 0) return
    const pastedFiles: File[] = []
    for (let i = 0; i < items.length; i++) {
      const item = items[i]
      if (item.kind === 'file') {
        const file = item.getAsFile()
        if (file && file.size > 0) pastedFiles.push(file)
      }
    }
    if (pastedFiles.length) {
      e.preventDefault()
      emit('filesPaste', pastedFiles)
    }
  }
}

// 果冻动效
const isJellyActive = ref(false)
let jellyTimer: ReturnType<typeof setTimeout> | null = null

function triggerJelly() {
  if (isJellyActive.value) return
  isJellyActive.value = true
  if (jellyTimer) clearTimeout(jellyTimer)
  jellyTimer = setTimeout(() => { isJellyActive.value = false }, 600)
}
</script>

<style scoped>
/* ========== 输入区 ========== */
.compose-area {  
  width: 80%;
  max-width: 1000px;
  margin: 0 auto;
  backdrop-filter: blur(10px);
  gap: 12px;
  position: relative;
}

.rotate-circle {
    opacity: 1;
    background-image: url(data:image/png;base64,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);
    background-size: cover;
    width: 100%;
    height: 100%;
    transition: opacity .3s;
    animation: 2s linear infinite rotate-animate;
    position: absolute;
    top: 0;
    left: 0;
}
@keyframes rotate-animate{0%{transform:rotate(0)}to{transform:rotate(360deg)}}
.scroll-to-bottom-btn {
  position: absolute;
  top: -60px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 10;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  /* 根据你的主题调整背景色 */
  background-color: var(--glass-bg); 
  z-index: 1;
}

.compose-thinking {
  position:absolute;
  top:-50px;
  padding:20px 10px;
}

.compose-input-container {
  width: 100%;
  position: relative;
}
.compose-input-container::before {
  content: "";
  position: absolute;
  top: 0;
  left: calc(50% - 40%);
  width: 80%;
  height: 1px;
  z-index: 1;
  background: linear-gradient(
    90deg,
    transparent 0%,
    #6366f1 15%,
    #8b5cf6 25%,
    #6366f1 35%,
    transparent 50%,
    transparent 50%,
    #6366f1 65%,
    #8b5cf6 75%,
    #6366f1 85%,
    transparent 100%
  );
  animation: flow-opacity 2s linear infinite;
}

@keyframes flow-opacity {
  0% {opacity: 0;}
  50% {opacity: 1;}
  100% {opacity: 0;}
}

.compose-input-container::after {
  content: "";
  position: absolute;
  bottom: 0;
  right: calc(50% - 40%);
  width: 80%;
  height: 1px;
  z-index: 1;
  background: linear-gradient(
    90deg,
    transparent 0%,
    #6366f1 15%,
    #8b5cf6 25%,
    #6366f1 35%,
    transparent 50%,
    transparent 50%,
    #6366f1 65%,
    #8b5cf6 75%,
    #6366f1 85%,
    transparent 100%
  );
  animation: flow-opacity-after 2s linear infinite;
}

@keyframes flow-opacity-after {
  0% {opacity: 1;}
  50% {opacity: 0;}
  100% {opacity: 1;}
}

.compose-input {
  border-radius: 20px;
  padding: 8px 120px 8px 8px;
}

.compose-tools-tar {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  position:absolute;
  bottom:34px;right:20px;
}

.send-btn {
  width: 40px;
  height: 40px;
  border-radius: 30px;
  background: var(--accent-gradient) !important;
  border: none !important;
  color: white !important;
  box-shadow: var(--shadow-glow);
}

.file-preview-list {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  padding: 8px;
  background: var(--bg-secondary);
  border-radius: 8px;
}
.file-preview-item {
  background: var(--bg-secondary);
  padding: 8px 12px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  position:relative;
}

.file-info {
  display: flex;
  align-items: center;
}

.file-close {
  font-size: 1.2rem;
  color: var(--text-secondary);
  cursor: pointer;
  display: inline-block;
  opacity: 0;
  position: absolute;
  top: 0;
  right: 10px;
}

.file-preview-item:hover .file-close {
  opacity: 1;
}

.file-thumb {
  width: 32px;
  height: 32px;
  object-fit: cover;
  border-radius: 4px;
}
.file-name {
  display: flex;
    justify-content: center; /* 水平居中 */
    align-items: center;
  font-size: 0.85rem;
  color: var(--text-secondary);
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
.compose-disclaimer {
    text-align: center;
    font-size: 12px;
    color: var(--text-secondary);
}
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease, transform 0.3s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(10px);
}
</style>