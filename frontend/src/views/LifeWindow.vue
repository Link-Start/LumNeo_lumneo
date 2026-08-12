<template>
  <div class="life-container" :class="configStore.themeMode">
    <!-- 极简顶部栏 -->
    <header class="life-top-bar">
      <div class="life-brand">
        <m-svg name="star" style="margin-right:6px;"/>
        <span class="gradient-text-small">LumNeo</span>
        <span class="mode-badge life">数字生命</span>
      </div>
      <n-flex align="center" :size="12">
        <n-button text size="large" class="life-settings-btn" @click="showLifeSettings = true">
          <template #icon><n-icon :size="20"><SettingsOutline /></n-icon></template>
          设置
        </n-button>
        <n-button text size="large" class="life-exit-btn" @click="exitLifeMode">
          <template #icon><n-icon :size="20"><LogOutOutline /></n-icon></template>
          退出
        </n-button>
      </n-flex>
    </header>

    <!-- 消息列表 -->
    <MessageList
      ref="messageListRef"
      v-if="chatStore.activeChatId"
      :chat-id="chatStore.activeChatId"
      :messages="currentMessages"
      mode-type="life"
      :is-mobile="isMobile"
      :is-loading="isLoading"
      :streaming-content="streamingContent"
      :regenerating-msg="regeneratingMsg"
      :is-dark="isDark"
      :show-welcome="false"
      :copy-svg-name="copySvgName"
      @copy="copyContent"
      @regenerate="handleRegenerateResponse"
      @edit="startEditMessage"
      @delete="chatStore.deleteMessage"
    />

    <!-- 空状态：仅当所有 life 对话被删除且创建失败时兜底 -->
    <!-- <div v-else class="life-empty">
      <div class="life-empty-card">
        <div class="life-empty-icon">🌟</div>
        <h3 class="life-empty-title">数字生命空间</h3>
        <p class="life-empty-desc">会话初始化中，或当前无可用对话</p>
        <n-flex justify="center" :size="16">
          <n-button type="primary" size="large" round @click="initLifeChat">
            <template #icon><n-icon><ChatbubbleOutline /></n-icon></template>
            开始对话
          </n-button>
          <n-button size="large" round @click="exitLifeMode">
            <template #icon><n-icon><LogOutOutline /></n-icon></template>
            返回首页
          </n-button>
        </n-flex>
      </div>
    </div> -->

    <!-- 聊天输入框 -->
    <ChatInput
      v-if="chatStore.activeChatId"
      v-model="currentInput"
      v-model:selected="selected"
      v-model:thinking-mode="thinkingMode"
      v-model:file-list="uploadFileList"
      mode-type="life"
      :is-loading="isLoading"
      :disabled="isLoading || !chatStore.activeChatId || !activeModelId"
      :uploaded-files="uploadedFiles"
      :show-scroll-btn="messageListRef?.showScrollBtn && currentMessages.length > 0"
      :show-regenerate-hint="!isLoading && currentMessages.length >= 1 && currentMessages[currentMessages.length - 1]?.role === 'user'"
      :show-deep-think="false"
      :max-files="fileConfig.max"
      :file-accept="fileConfig.accept"
      :before-upload="onBeforeUpload"
      @send="onSendMessage"
      @stop="stopGeneration"
      @scroll-bottom="messageListRef?.scrollToLatestSmooth()"
      @remove-file="removeFile"
      @regenerate-current="onRegenerateFromCurrentHistory"
      @files-paste="handlePasteFiles"
      @upload-change="handleFileUpload"
    />

    <!-- 设置弹框：仅大模型选择 -->
    <n-modal
      v-model:show="showLifeSettings"
      preset="card"
      title="数字生命设置"
      style="width: 420px"
      :mask-closable="false"
    >
      <n-form label-placement="left" label-width="80">
        <n-form-item label="大模型">
          <n-select
            v-model:value="lifeModelId"
            :options="modelOptions"
            placeholder="选择陪伴你的大模型"
            clearable
          />
        </n-form-item>
      </n-form>
      <template #action>
        <n-flex justify="end">
          <n-button @click="showLifeSettings = false">取消</n-button>
          <n-button type="primary" @click="saveLifeSettings">保存</n-button>
        </n-flex>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, provide, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NIcon, NFlex, NSelect, NModal, NForm, NFormItem, useMessage } from 'naive-ui'
import type { UploadFileInfo } from 'naive-ui'
import { SettingsOutline, LogOutOutline, ChatbubbleOutline } from '@vicons/ionicons5'
import { useChatStore, type Message } from '@/stores/chat'
import { useConfigStore, fileConfig } from '@/stores/config'

import mSvg from '@/components/MSvg.vue'
import MessageList from '@/components/MessageList.vue'
import ChatInput from '@/components/ChatInput.vue'

import { useModel } from '@/composables/useModel'
import { useFileUpload } from '@/composables/useFileUpload'
import { useChat } from '@/composables/useChat'
import { useMessageActions } from '@/composables/useMessageActions'

const router = useRouter()
const chatStore = useChatStore()
const configStore = useConfigStore()
const message = useMessage()

const isMobile = ref(false)

const { activeModelId, modelOptions, switchActiveModel } = useModel()
const { uploadFileList, uploadedFiles, onBeforeUpload, handleFileUpload, removeFile, clearFiles } = useFileUpload()
const { currentInput, isLoading, streamingContent, regeneratingMsg, onStreamEnd,
    sendMessage, regenerateResponse, regenerateFromCurrentHistory, stopGeneration
} = useChat()
const { copySvgName, copyContent, startEditMessage } = useMessageActions()

// ========== Life Mode 专属状态 ==========
const showLifeSettings = ref(false)
const lifeModelId = ref(localStorage.getItem('life_model_id') || '')

function saveLifeSettings() {
  if (lifeModelId.value) {
    switchActiveModel(lifeModelId.value)
    localStorage.setItem('life_model_id', lifeModelId.value)
    message.success('设置已保存')
  } else {
    message.warning('请选择一个大模型')
    return
  }
  showLifeSettings.value = false
}

// 初始化 Life 模型同步
if (chatStore.mode === 'life' && lifeModelId.value && !activeModelId.value) {
  switchActiveModel(lifeModelId.value)
}

const isDark = computed(() => configStore.themeMode === 'dark')

const selected = ref(localStorage.getItem('thinking') === 'true')
const thinkingMode = ref<'high' | 'xhigh'>(
  (localStorage.getItem('thinkingMode') as 'high' | 'xhigh') || 'high'
)

const messageListRef = ref<InstanceType<typeof MessageList> | null>(null)

provide('scrollToBottom', () => {
  messageListRef.value?.scrollToLatest()
})

const currentMessages = computed(() => chatStore.currentChatMessages)

/**
 * 退出数字生命模式，返回欢迎页
 */
function exitLifeMode() {
  chatStore.setMode('chat')
  chatStore.activeChatId = ''
  router.push({ name: 'chatIndex' })
}

onStreamEnd.value = async (chatId: string, turnIndex: number) => {
  try {
    const res = await fetch(`/api/chats/${chatId}/messages/by-turn?turn_index=${turnIndex}`)
    if (res.ok) {
      const data = await res.json()
      if (data.id) {
        chatStore.updateMessageId(turnIndex, data.id)
      }
    }
  } catch (e) {
    console.warn('获取消息 ID 失败', e)
  }
}

function handlePasteFiles(files: File[]) {
  if (!chatStore.activeChatId || isLoading.value || !activeModelId.value) return
  const acceptedFiles = files.filter(f => {
    const suffix = '.' + f.name.split('.').pop()?.toLowerCase()
    const acceptList = fileConfig.accept.split(',').map(s => s.trim())
    return acceptList.includes(suffix)
  })
  if (acceptedFiles.length === 0) return
  const remaining = fileConfig.max - uploadedFiles.value.length
  if (remaining <= 0) return
  const filesToAdd = acceptedFiles.slice(0, remaining)
  for (const file of filesToAdd) {
    let filename = file.name
    if (!filename || filename === 'image.png' || filename === 'blob' || filename === 'clipboard') {
      const ext = file.name.split('.').pop() || 'bin'
      const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)
      filename = `paste-${timestamp}-${Math.random().toString(36).slice(2, 6)}.${ext}`
    }
    const uploadFile: UploadFileInfo = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
      name: filename,
      status: 'pending',
      file: new File([file], filename, { type: file.type }),
    }
    uploadFileList.value.push(uploadFile)
  }
  handleFileUpload({ fileList: uploadFileList.value })
}

const onSendMessage = () => {
  if (!currentInput.value.trim() || isLoading.value || !chatStore.activeChatId || !activeModelId.value) return
  sendMessage(uploadedFiles.value, () => {
    messageListRef.value?.scrollToLatest()
  })
  clearFiles()
}

const onRegenerateFromCurrentHistory = async () => {
  await regenerateFromCurrentHistory()
}

const handleRegenerateResponse = async (msg: Message, prevMsg: Message) => {
  await regenerateResponse(msg, prevMsg)
}

function checkMobile() {
  isMobile.value = window.innerWidth <= 768
}

// ========== 核心改动：自动初始化 Life 会话 ==========
async function initLifeChat() {
  await chatStore.loadChats()
  
  // Life 模式单例：有就复用，没有就新建
  const existingLife = chatStore.chats.find(c => c.type === 'life')
  if (existingLife) {
    chatStore.activeChatId = existingLife.id
    await chatStore.loadMessages(existingLife.id)
  } else {
    const newId = await chatStore.addChat('life')
    chatStore.activeChatId = newId
  }
  
  await nextTick()
  messageListRef.value?.scrollToLatest()
}

onMounted(async () => {
  checkMobile()
  chatStore.setMode('life')
  configStore.loadModels()
  
  // 进入 /life 自动初始化，不让用户看到空状态
  if (!chatStore.activeChatId) {
    await initLifeChat()
  }
  
  await nextTick()
  if (chatStore.activeChatId) {
    messageListRef.value?.scrollToLatest()
  }
})
</script>

<style scoped>
.life-container {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: linear-gradient(180deg, var(--bg-primary) 0%, rgba(99,102,241,0.02) 50%, var(--bg-primary) 100%);
  color: var(--text-primary);
  font-family: 'Inter', 'Segoe UI', sans-serif;
  overflow: hidden;
  position: relative;
}

/* 极简顶部栏 */
.life-top-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
  background: transparent;
  border-bottom: none;
  flex-shrink: 0;
}

.life-brand {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 1.1rem;
  font-weight: 600;
}

.gradient-text-small {
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.life-settings-btn {
  color: var(--text-secondary);
  transition: color 0.2s;
}
.life-settings-btn:hover {
  color: var(--accent);
}

.life-exit-btn {
  color: var(--text-secondary);
  transition: color 0.2s;
}
.life-exit-btn:hover {
  color: #ef4444;
}

/* 模式标签 */
.mode-badge {
  font-size: 0.65rem;
  padding: 2px 8px;
  border-radius: 10px;
  margin-left: 8px;
  vertical-align: middle;
  font-weight: 500;
}
.mode-badge.life {
  background: linear-gradient(135deg, #f59e0b, #fbbf24);
  color: white;
}

/* 空状态 */
.life-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex: 1;
  width: 100%;
}

.life-empty-card {
  background: var(--glass-bg);
  backdrop-filter: blur(12px);
  border: 1px solid var(--border-color);
  border-radius: 20px;
  padding: 48px 40px;
  text-align: center;
  max-width: 420px;
  animation: fade-up 0.5s ease;
}

.life-empty-icon {
  font-size: 3.5rem;
  margin-bottom: 8px;
  filter: drop-shadow(0 4px 8px rgba(245, 158, 11, 0.2));
}

.life-empty-title {
  margin: 16px 0 8px;
  font-size: 1.3rem;
  font-weight: 600;
  color: var(--text-primary);
}

.life-empty-desc {
  color: var(--text-secondary);
  margin-bottom: 28px;
  font-size: 0.95rem;
}

.edit-modal-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding-right: 8px;
}
.edit-modal-title .fullscreen-btn {
  margin-left: 12px;
  color: var(--text-secondary);
  transition: color 0.2s, background 0.2s;
}
.edit-modal-title .fullscreen-btn:hover {
  color: var(--accent);
  background: rgba(74, 124, 247, 0.12);
}

:deep(.edit-modal-fullscreen) {
  width: 100vw !important;
  max-width: 100vw !important;
  height: 100vh !important;
  max-height: 100vh !important;
  margin: 0 !important;
  top: 0 !important;
  border-radius: 0 !important;
}
:deep(.edit-modal-fullscreen .n-modal-dialog) {
  width: 100vw !important;
  max-width: 100vw !important;
  height: 100vh !important;
  max-height: 100vh !important;
  margin: 0 !important;
  border-radius: 0 !important;
}
:deep(.edit-modal-fullscreen .n-modal__content) {
  height: calc(100vh - 130px);
}
:deep(.edit-modal-fullscreen .n-input) {
  height: 100%;
}
:deep(.edit-modal-fullscreen .n-input .n-input__textarea-el) {
  min-height: 100% !important;
  height: 100% !important;
}

@keyframes fade-up {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>