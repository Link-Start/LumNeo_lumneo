// src/composables/useChat.ts
import { ref } from 'vue'
import { useChatStore, type Message } from '@/stores/chat'
import { useConfigStore } from '@/stores/config'
import { useProfileStore } from '@/stores/profiles'
import { useMessage } from 'naive-ui'
import { cleanMessages } from '@/utils/message'
import type { UploadedFile } from '@/composables/useFileUpload'

export function useChat() {
  const chatStore = useChatStore()
  const configStore = useConfigStore()
  const profileStore = useProfileStore()
  const message = useMessage()

  const currentInput = ref('')
  const isLoading = ref(false)
  const streamingContent = ref('')
  const abortController = ref<AbortController | null>(null)
  const regeneratingMsg = ref<Message | null>(null)

  function stopGeneration() {
    if (abortController.value) {
      abortController.value.abort()
    } else {
      isLoading.value = false
      regeneratingMsg.value = null
    }
  }

  const onStreamEnd = ref<((fullText: string) => void) | null>(null)

  async function readStream(response: Response): Promise<string> {
    if (!response.ok || !response.body) throw new Error('网络响应失败')
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let fullText = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      fullText += decoder.decode(value, { stream: true })
      streamingContent.value = fullText
    }
    return fullText
  }

  /**
   * 流式正常结束后，直接重载对话列表，保证本地数据与后端 JSON 结构严格一致
   */
  async function finalizeAssistantMessage(chatId: string) {
    await chatStore.loadMessages(chatId)
    streamingContent.value = ''
  }

  /**
   * 流式中断时的保存逻辑
   */
  async function handleAbort(chatId: string, turnIndex: number) {
    const chat = chatStore.chats.find(c => c.id === chatId)
    if (!chat) return
    const placeholder = chat.messages.find(m => m.turn_index === turnIndex && m.role === 'assistant')
    if (placeholder) {
      const partialContent = (streamingContent.value.trim() ? streamingContent.value.trim() + '\n\n' : '') + '[已停止]'
      placeholder.content = partialContent
    }
    streamingContent.value = ''
  }

  /**
   * 发送新消息
   */
  async function sendMessage(uploadedFiles: UploadedFile[], scrollToBottom: () => void) {
    if (!currentInput.value.trim() || isLoading.value || !chatStore.activeChatId) return

    const currentModel = configStore.activeModel
    if (!currentModel) {
      message.error('请先选择一个模型')
      return
    }

    const chatId = chatStore.activeChatId
    const displayContent = currentInput.value.trim()
    currentInput.value = ''

    // 1. 获取并计算当前对话的轮次索引（让后端严格按顺序落盘）
    const userTurnIndex = chatStore.getNextTurnIndex()
    const userMsg: Message = {
      id: Date.now(),
      role: 'user',
      content: displayContent,
      file_ref: uploadedFiles.length > 0 ? uploadedFiles.map((f) => ({ filename: f.filename, type: f.type, url: f.url })) : null,
      turn_index: userTurnIndex
    }

    chatStore.addMessageToLocal(userMsg)
    await chatStore.saveMessageToBackend(userMsg)

    // 2. 预先在本地插入一个空的助手占位符，用于展示流式输出
    const assistantTurnIndex = chatStore.getNextTurnIndex()
    const assistantMsg: Message = {
      id: Date.now() + 1,
      role: 'assistant',
      content: '',
      turn_index: assistantTurnIndex
    }
    // 注意：此处不调用 saveMessageToBackend，而是让后端流式结束时通过 turn_index 精准落盘并覆盖
    chatStore.addMessageToLocal(assistantMsg)

    isLoading.value = true
    streamingContent.value = ''

    if (abortController.value) abortController.value.abort()
    const controller = new AbortController()
    abortController.value = controller

    try {
      const allMessages = chatStore.getActiveMessages()
      // 剔除最后一个我们刚加的助手占位符（因为实际发送给模型的上下文不需要这个空占位）
      allMessages.pop()
      
      const apiMessages = await cleanMessages(allMessages)
      const body = JSON.stringify({
        messages: apiMessages,
        enable_tools: chatStore.enableProfile,
        llm_config: {
          type: currentModel.type,
          model_name: currentModel.modelName,
          base_url: currentModel.baseUrl,
          api_key: currentModel.apiKey,
          thinking: localStorage.getItem('thinking') === 'true' ? 'enabled' : 'disabled'
        },
        profile_id: chatStore.enableProfile ? profileStore.activeProfileId : null,
        chat_id: chatStore.activeChatId,
        turn_index: assistantTurnIndex // 【核心】将助手的轮次索引传给后端，作为存储依据
      })

      setTimeout(() => scrollToBottom(), 160)
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
        signal: controller.signal
      })
      
      const fullText = await readStream(response)

      if (chatStore.activeChatId === chatId) {
        await finalizeAssistantMessage(chatId)
      }
    } catch (error: any) {
      if (error.name === 'AbortError') {
        if (chatStore.activeChatId === chatId) {
          await handleAbort(chatId, assistantTurnIndex)
        }
        return
      }
      if (chatStore.activeChatId === chatId) {
        console.error('发送失败:', error)
        const errorContent = `**错误：** ${error.message}`
        const localMsg = chatStore.currentChatMessages.find(m => m.turn_index === assistantTurnIndex && m.role === 'assistant')
        if (localMsg) localMsg.content = errorContent
      }
    } finally {
      abortController.value = null
      isLoading.value = false
      if (onStreamEnd.value && chatStore.activeChatId === chatId) {
        // 由于已经重载过数据，此处仅用于外部回调通知
        onStreamEnd.value('')
      }
    }
  }

  /**
   * 强制重新生成当前对话的最后一条回答
   */
  async function regenerateFromCurrentHistory() {
    if (!chatStore.activeChatId || isLoading.value) return
    const currentModel = configStore.activeModel
    if (!currentModel) { message.error('请先选择一个模型'); return }

    const chatId = chatStore.activeChatId
    // 获取最新的占位轮次
    const assistantTurnIndex = chatStore.getNextTurnIndex()
    const assistantMsg: Message = {
      id: Date.now() + 1,
      role: 'assistant',
      content: '',
      turn_index: assistantTurnIndex
    }
    chatStore.addMessageToLocal(assistantMsg)

    isLoading.value = true
    if (abortController.value) abortController.value.abort()
    const controller = new AbortController()
    abortController.value = controller

    try {
      const allMessages = chatStore.getActiveMessages()
      // 同样，去掉我们刚加的占位符
      allMessages.pop()

      const body = JSON.stringify({
        messages: await cleanMessages(allMessages),
        enable_tools: chatStore.enableProfile,
        llm_config: {
          type: currentModel.type,
          model_name: currentModel.modelName,
          base_url: currentModel.baseUrl,
          api_key: currentModel.apiKey,
          thinking: localStorage.getItem('thinking') === 'true' ? 'enabled' : 'disabled'
        },
        profile_id: chatStore.enableProfile ? profileStore.activeProfileId : null,
        chat_id: chatStore.activeChatId,
        turn_index: assistantTurnIndex
      })

      const response = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body, signal: controller.signal })
      await readStream(response)
      await finalizeAssistantMessage(chatId)
    } catch (error: any) {
      if (error.name === 'AbortError') {
        await handleAbort(chatId, assistantTurnIndex)
        return
      }
      const errContent = `**错误：** ${error.message}`
      const localMsg = chatStore.currentChatMessages.find(m => m.turn_index === assistantTurnIndex && m.role === 'assistant')
      if (localMsg) localMsg.content = errContent
    } finally {
      abortController.value = null
      isLoading.value = false
    }
  }

  /**
   * 针对某条具体的助手消息进行重新生成（替换/截断后续内容）
   */
  async function regenerateResponse(assistantMsg: Message) {
    if (!chatStore.activeChatId || isLoading.value) return
    const currentModel = configStore.activeModel
    if (!currentModel) { message.error('请先选择一个模型'); return }

    const chatId = chatStore.activeChatId
    regeneratingMsg.value = assistantMsg

    // 1. 截断该条助手消息及之后的所有消息
    await chatStore.truncateAtTurn(assistantMsg.turn_index)

    // 2. 开始一个新的流式生成 (复用助手该轮次)
    isLoading.value = true
    if (abortController.value) abortController.value.abort()
    const controller = new AbortController()
    abortController.value = controller

    // 3. 由于截断后，原助手消息已被删除，重新放入占位
    const newMsg: Message = {
      id: Date.now() + 1,
      role: 'assistant',
      content: '',
      turn_index: assistantMsg.turn_index
    }
    chatStore.addMessageToLocal(newMsg)

    try {
      const allMessages = chatStore.getActiveMessages()
      allMessages.pop() // 去掉刚加的占位符

      const body = JSON.stringify({
        messages: await cleanMessages(allMessages),
        enable_tools: chatStore.enableProfile,
        llm_config: {
          type: currentModel.type,
          model_name: currentModel.modelName,
          base_url: currentModel.baseUrl,
          api_key: currentModel.apiKey,
          thinking: localStorage.getItem('thinking') === 'true' ? 'enabled' : 'disabled'
        },
        profile_id: chatStore.enableProfile ? profileStore.activeProfileId : null,
        chat_id: chatStore.activeChatId,
        turn_index: assistantMsg.turn_index
      })

      const response = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body, signal: controller.signal })
      await readStream(response)
      await finalizeAssistantMessage(chatId)

      if (onStreamEnd.value) onStreamEnd.value('')
    } catch (error: any) {
      if (error.name === 'AbortError') {
        await handleAbort(chatId, assistantMsg.turn_index)
        return
      }
      const errContent = `**错误：** ${error.message}`
      const localMsg = chatStore.currentChatMessages.find(m => m.turn_index === assistantMsg.turn_index && m.role === 'assistant')
      if (localMsg) localMsg.content = errContent
    } finally {
      abortController.value = null
      regeneratingMsg.value = null
      isLoading.value = false
    }
  }

  return {
    currentInput,
    isLoading,
    streamingContent,
    regeneratingMsg,
    onStreamEnd,
    sendMessage,
    regenerateResponse,
    regenerateFromCurrentHistory,
    stopGeneration,
  }
}