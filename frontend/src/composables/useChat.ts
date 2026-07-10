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

/** 解析流式文本中的工具完整数据 */
  function parseToolData(text: string) {
    const regex = /<!--tool_data:([^:]+):([\s\S]*?)-->/g
    const results = []
    let match
    while ((match = regex.exec(text)) !== null) {
      try {
        results.push({ call_id: match[1], ...JSON.parse(match[2]) })
      } catch (e) {
        console.error('解析 tool_data 失败', e)
      }
    }
    return results
  }
  
  /**
   * 辅助函数：处理流式正常结束后的消息保存逻辑
   */
async function finalizeAssistantMessage(chatId: string, assistantMsgId: number, fullText: string) {
    const toolDataList = parseToolData(fullText)
    
    // ✅ 核心：获取底层的真实 chat 对象，而不是 computed 属性
    const chat = chatStore.chats.find(c => c.id === chatId)
    if (!chat) return

    if (toolDataList.length > 0) {
      // 1. 更新原占位 assistant 消息为带 tool_calls 的消息
      const assistantToolMsg = chat.messages.find((m: any) => m.id === assistantMsgId)
      if (assistantToolMsg) {
        assistantToolMsg.tool_calls = toolDataList.map((d: any) => ({
          id: d.call_id,
          type: 'function',
          function: { name: d.name, arguments: d.arguments || '{}' }
        }))
        assistantToolMsg.content = '' // 工具调用时 content 置空
      }
      
      // 2. 插入 tool 消息到底层 messages 列表
      const insertIndex = chat.messages.findIndex(m => m.id === assistantMsgId) + 1
      let insertedCount = 0
      
      for (const d of toolDataList) {
        const exist = chat.messages.find(m => m.role === 'tool' && m.tool_call_id === d.call_id)
        if (!exist) {
          const toolMsg: Message = {
            id: Date.now() + insertedCount, // 临时 ID
            role: 'tool',
            tool_call_id: d.call_id,
            content: d.result
          }
          // 向底层数组中插入
          chat.messages.splice(insertIndex + insertedCount, 0, toolMsg)
          insertedCount++
        }
      }
      
      // 3. 提取最终回答，作为新消息保存
      let finalContent = fullText
      finalContent = finalContent.replace(/<!--tool_data:[^:]+:[\s\S]*?-->/g, '')

      if (finalContent) {
        const finalMsg: Message = { id: Date.now() + 1000, role: 'assistant', content: finalContent }
        // addMessageToLocal 会自动向 chat.messages push
        chatStore.addMessageToLocal(finalMsg)
        // 后端没有存这条最终回答，需要前端保存
        await chatStore.saveMessageToBackend(finalMsg)
      }
    } else {
      // 未触发工具调用：直接更新原预建的空消息
      const localMsg = chat.messages.find((m: any) => m.id === assistantMsgId)
      if (localMsg) localMsg.content = fullText
      await chatStore.editMessage(<number>assistantMsgId, fullText).catch((e: any) =>
        console.warn('更新助手消息失败', e)
      )
    }
  }

  /**
   * 辅助函数：处理流式中断后的消息保存逻辑
   */
  async function handleAbort(chatId: string, assistantMsgId: number) {
    const partialContent = (streamingContent.value.trim() ? streamingContent.value.trim() + '\n\n' : '') + '[已停止]'
    const hasToolCalls = streamingContent.value.includes('<!--tool_calls:start-->')
    
    // ✅ 获取底层 chat 对象
    const chat = chatStore.chats.find(c => c.id === chatId)
    if (!chat) return

    if (hasToolCalls) {
      // 如果中断时已经发生了工具调用，不要覆盖原消息，新建消息保存截断内容
      const finalMsg: Message = { id: Date.now(), role: 'assistant', content: partialContent }
      chatStore.addMessageToLocal(finalMsg)
      await chatStore.saveMessageToBackend(finalMsg)
      
      const localEmptyMsg = chat.messages.find((m: any) => m.id === assistantMsgId)
      if (localEmptyMsg) localEmptyMsg.content = ''
    } else {
      // 未发生工具调用，直接更新原消息
      const localMsg = chat.messages.find((m: any) => m.id === assistantMsgId)
      if (localMsg) localMsg.content = partialContent
      await chatStore.editMessage(<number>assistantMsgId, partialContent).catch((e) =>
        console.warn('保存截断消息失败', e)
      )
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
    const userMsg: Message = {
      id: Date.now(),
      role: 'user',
      content: displayContent,
      file_ref: uploadedFiles.length > 0 ? uploadedFiles.map((f) => ({ filename: f.filename, type: f.type, url: f.url })) : null,
    }

    chatStore.addMessageToLocal(userMsg)
    await chatStore.saveMessageToBackend(userMsg)

    const assistantMsg: Message = { id: Date.now() + 1, role: 'assistant', content: '' }
    chatStore.addMessageToLocal(assistantMsg)
    await chatStore.saveMessageToBackend(assistantMsg)
    
    const assistantMessageId = assistantMsg.id
    isLoading.value = true
    streamingContent.value = ''
    currentInput.value = ''

    if (abortController.value) abortController.value.abort()
    const controller = new AbortController()
    abortController.value = controller
    let fullText = ''

    try {
      const allMessages = chatStore.getActiveMessages()
      const apiMessages = await cleanMessages(allMessages)
      // 删除最后一条消息
      apiMessages.pop()
      const body = JSON.stringify({
        messages: apiMessages,
        enable_tools: chatStore.enableProfile,
        llm_config: {
          type: currentModel.type, model_name: currentModel.modelName, base_url: currentModel.baseUrl,
          api_key: currentModel.apiKey,
          thinking: localStorage.getItem('thinking') === 'true' ? 'enabled' : 'disabled'
        },
        profile_id: chatStore.enableProfile ? profileStore.activeProfileId : null,
        message_id: assistantMessageId,
        chat_id: chatStore.activeChatId,
      })

      setTimeout(() => scrollToBottom(), 160)
      const response = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body, signal: controller.signal })
      fullText = await readStream(response)

      if (chatStore.activeChatId === chatId) {
        await finalizeAssistantMessage(chatId, assistantMsg.id, fullText)
      }
    } catch (error: any) {
      if (error.name === 'AbortError') {
        if (chatStore.activeChatId === chatId) {
          await handleAbort(chatId, assistantMsg.id)
        }
        return
      }
      if (chatStore.activeChatId === chatId) {
        console.error('发送失败:', error)
        const errorContent = `**错误：** ${error.message}`
        const localMsg = chatStore.currentChatMessages.find((m: any) => m.id === assistantMsg.id)
        if (localMsg) localMsg.content = errorContent
        chatStore.editMessage(<number>assistantMsg.id, errorContent).catch((e: any) => console.warn('保存错误消息失败', e))
      }
    } finally {
      abortController.value = null
      isLoading.value = false
      streamingContent.value = ''
      if (onStreamEnd.value && fullText && chatStore.activeChatId === chatId) {
        onStreamEnd.value(fullText)
      }
    }
  }

  /**
   * 重新生成当前对话（通常用于编辑用户消息后）
   */
  async function regenerateFromCurrentHistory() {
    if (!chatStore.activeChatId || isLoading.value) return
    const currentModel = configStore.activeModel
    if (!currentModel) { message.error('请先选择一个模型'); return }

    isLoading.value = true
    if (abortController.value) abortController.value.abort()
    const controller = new AbortController()
    abortController.value = controller

    const assistantMsg: Message = { id: Date.now() + 1, role: 'assistant', content: '' }
    chatStore.addMessageToLocal(assistantMsg)
    await chatStore.saveMessageToBackend(assistantMsg)
    try {
      const body = JSON.stringify({
        messages: await cleanMessages(chatStore.getActiveMessages()),
        enable_tools: chatStore.enableProfile,
        llm_config: { type: currentModel.type, model_name: currentModel.modelName, base_url: currentModel.baseUrl, api_key: currentModel.apiKey, thinking: localStorage.getItem('thinking') === 'true' ? 'enabled' : 'disabled' },
        profile_id: chatStore.enableProfile ? profileStore.activeProfileId : null,
        message_id: assistantMsg.id,
        chat_id: chatStore.activeChatId,
      })

      const response = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body, signal: controller.signal })
      const fullText = await readStream(response)
      await finalizeAssistantMessage(chatStore.activeChatId, assistantMsg.id, fullText)
    } catch (error: any) {
      if (error.name === 'AbortError') {
        await handleAbort(chatStore.activeChatId, assistantMsg.id)
        return
      }
      const errContent = `**错误：** ${error.message}`
      const localMsg = chatStore.currentChatMessages.find(m => m.id === assistantMsg.id)
      if (localMsg) localMsg.content = errContent
      chatStore.editMessage(<number>assistantMsg.id, errContent).catch((e) => console.warn('保存错误消息失败', e))
    } finally {
      abortController.value = null
      isLoading.value = false
      streamingContent.value = ''
    }
  }

  /**
   * 针对某条助手消息重新生成（使用该消息前的历史）
   */
  async function regenerateResponse(assistantMsg: Message) {
    if (!chatStore.activeChatId || isLoading.value) return
    const currentModel = configStore.activeModel
    if (!currentModel) { message.error('请先选择一个模型'); return }

    const allMessages = chatStore.getActiveMessages()
    const idx = allMessages.indexOf(assistantMsg)
    if (idx === -1) return

    const history = allMessages.slice(0, idx)
    regeneratingMsg.value = assistantMsg

    isLoading.value = true
    if (abortController.value) abortController.value.abort()
    const controller = new AbortController()
    abortController.value = controller

    assistantMsg.content = ''
    streamingContent.value = ''

    try {
      const body = JSON.stringify({
        messages: await cleanMessages(history),
        enable_tools: chatStore.enableProfile,
        llm_config: { type: currentModel.type, model_name: currentModel.modelName, base_url: currentModel.baseUrl, api_key: currentModel.apiKey, thinking: localStorage.getItem('thinking') === 'true' ? 'enabled' : 'disabled' },
        profile_id: chatStore.enableProfile ? profileStore.activeProfileId : null,
        message_id: assistantMsg.id,
        chat_id: chatStore.activeChatId,
      })

      const response = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body, signal: controller.signal })
      const fullText = await readStream(response)
      await finalizeAssistantMessage(chatStore.activeChatId, assistantMsg.id, fullText)
      
      if (onStreamEnd.value) onStreamEnd.value(fullText)
    } catch (error: any) {
      if (error.name === 'AbortError') {
        await handleAbort(chatStore.activeChatId, assistantMsg.id)
        return
      }
      const errContent = `**错误：** ${error.message}`
      assistantMsg.content = errContent
      if (assistantMsg.id) {
        fetch(`/api/chats/${chatStore.activeChatId}/messages/${assistantMsg.id}`, {
          method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ role: 'assistant', content: errContent }),
        }).catch((e) => console.warn('更新错误消息失败', e))
      }
    } finally {
      abortController.value = null
      regeneratingMsg.value = null
      isLoading.value = false
      streamingContent.value = ''
    }
  }

  return {
    currentInput, isLoading, streamingContent, regeneratingMsg, onStreamEnd,
    sendMessage, regenerateResponse, regenerateFromCurrentHistory, stopGeneration,
  }
}
