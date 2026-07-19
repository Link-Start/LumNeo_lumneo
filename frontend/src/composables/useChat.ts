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

type StreamEndCallback = (chatId: string, turnIndex: number) => void
const onStreamEnd = ref<StreamEndCallback | null>(null)

async function readStream(response: Response): Promise<{ finalSegments?: any[] }> {
  if (!response.ok || !response.body) throw new Error('网络响应失败')
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let fullText = ''
  let finalSegments: any[] | undefined = undefined

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    const chunk = decoder.decode(value, { stream: true })
    fullText += chunk
    streamingContent.value = fullText

    // 尝试从流中提取最终的结构化 JSON
    const match = chunk.match(/<!--segments_complete:([\s\S]*?)-->/)
    if (match) {
      try {
        finalSegments = JSON.parse(match[1])
      } catch (e) {
        console.error('解析最终结构化数据失败', e)
      }
    }
  }
  return { finalSegments }
}

/**
   * 保存被中断的消息到本地和后端
   */
  async function saveAbortedMessage(chatId: string, turnIndex: number, streamingText: string) {
    const chat = chatStore.chats.find(c => c.id === chatId)
    if (!chat) return

    // 1. 获取当前轮次的占位消息（它必然存在于 Store 中，因为我们一开始就插入了空占位）
    let targetMsg = chat.messages.find(m => m.turn_index === turnIndex && m.role === 'assistant')
    
    // 极端兜底：如果还没插入，手动补一个（极少数情况）
    if (!targetMsg) {
      targetMsg = {
        id: Date.now(),
        role: 'assistant',
        content: '',
        turn_index: turnIndex
      }
      chatStore.addMessageToLocal(targetMsg)
    }

    // 2. 构造最终显示的文本（追加停止标记）
    const suffix = '\n\n[用户停止了生成]'
    let displayContent = streamingText.trim()
    if (displayContent) {
      displayContent += suffix
    } else {
      displayContent = '用户停止了生成'
    }

    // 3. 将纯文本封装成合法的结构化 JSON 数组落盘
    const finalSegments = [{ type: "text", content: displayContent }]
    targetMsg.content = JSON.stringify(finalSegments)

    // 4. 调用后端接口，将当前轮次的消息真正保存到数据库！
    await chatStore.saveMessageToBackend(targetMsg)
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
        turn_index: assistantTurnIndex
      })

      setTimeout(() => scrollToBottom(), 160)
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
        signal: controller.signal
      })
      
      const { finalSegments } = await readStream(response)

      if (chatStore.activeChatId === chatId) {
        if (finalSegments) {
          const chat = chatStore.chats.find(c => c.id === chatId)
          if (chat) {
            const targetMsg = chat.messages.find(m => m.turn_index === assistantTurnIndex && m.role === 'assistant')
            if (targetMsg) {
              targetMsg.content = JSON.stringify(finalSegments) 
            }
          }
        }
        streamingContent.value = ''
      }
    } catch (error: any) {
      if (error.name === 'AbortError') {
        if (chatStore.activeChatId === chatId) {
          await saveAbortedMessage(chatId, assistantTurnIndex, streamingContent.value)
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
        onStreamEnd.value(chatId, assistantTurnIndex)
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
      const { finalSegments } = await readStream(response)
      if (chatStore.activeChatId === chatId && finalSegments) {
        const chat = chatStore.chats.find(c => c.id === chatId)
        if (chat) {
          const targetMsg = chat.messages.find(m => m.turn_index === assistantTurnIndex && m.role === 'assistant')
          if (targetMsg) targetMsg.content = JSON.stringify(finalSegments)
        }
        streamingContent.value = ''
      }
    } catch (error: any) {
      if (error.name === 'AbortError') {
        await saveAbortedMessage(chatId, assistantTurnIndex, streamingContent.value)
        return
      }
      const errContent = `**错误：** ${error.message}`
      const localMsg = chatStore.currentChatMessages.find(m => m.turn_index === assistantTurnIndex && m.role === 'assistant')
      if (localMsg) localMsg.content = errContent
    } finally {
      abortController.value = null
      isLoading.value = false
      streamingContent.value = ''
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

    // 2. 开始一个新的流式生成 (复用原本的轮次 turn_index)
    isLoading.value = true
    if (abortController.value) abortController.value.abort()
    const controller = new AbortController()
    abortController.value = controller

    // 3. 插入新的占位消息
    const newMsg: Message = {
      id: Date.now() + 1,
      role: 'assistant',
      content: '',
      turn_index: assistantMsg.turn_index
    }
    chatStore.addMessageToLocal(newMsg)

    try {
      const allMessages = chatStore.getActiveMessages()
      // 注意：这里要去掉我们刚加的占位符，因为发请求时不需要它
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
        turn_index: assistantMsg.turn_index
      })

      const response = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body, signal: controller.signal })
      // ✅ 流式读取，解构出 finalSegments
      const { finalSegments } = await readStream(response)

      if (chatStore.activeChatId === chatId) {
        if (finalSegments) {
          // ✅ 精准更新本地占位消息
          const chat = chatStore.chats.find(c => c.id === chatId)
          if (chat) {
            const targetMsg = chat.messages.find(m => m.turn_index === assistantMsg.turn_index && m.role === 'assistant')
            if (targetMsg) {
              targetMsg.content = JSON.stringify(finalSegments)
            }
          }
        }
        streamingContent.value = ''
      }

      if (onStreamEnd.value) onStreamEnd.value(chatId, assistantMsg.turn_index)
    } catch (error: any) {
      if (error.name === 'AbortError') {
        await saveAbortedMessage(chatId, assistantMsg.turn_index, streamingContent.value)
        return
      }
      const errContent = `**错误：** ${error.message}`
      const chat = chatStore.chats.find(c => c.id === chatId)
      if (chat) {
        const targetMsg = chat.messages.find(m => m.turn_index === assistantMsg.turn_index && m.role === 'assistant')
        if (targetMsg) targetMsg.content = errContent
      }
    } finally {
      abortController.value = null
      regeneratingMsg.value = null
      isLoading.value = false
      streamingContent.value = ''
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