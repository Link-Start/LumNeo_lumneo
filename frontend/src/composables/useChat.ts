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
      // ✅ 不要在这里重置 isLoading，交给 fetch 的 finally 去处理
      // 否则用户在旧请求未完全清理完时，可能会再次发起新请求导致竞态
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
   * 发送新消息
   */
  async function sendMessage(
    uploadedFiles: UploadedFile[],
    scrollToBottom: () => void
  ) {
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
      file_ref:
        uploadedFiles.length > 0
          ? uploadedFiles.map((f) => ({
              filename: f.filename,
              type: f.type,
              url: f.url,
            }))
          : null,
    }

    chatStore.addMessageToLocal(userMsg)
    await chatStore.saveMessageToBackend(userMsg)

    const assistantMsg: Message = {
      id: Date.now() + 1,
      role: 'assistant',
      content: '',
    }
    chatStore.addMessageToLocal(assistantMsg)
    await chatStore.saveMessageToBackend(assistantMsg)
    const assistantMessageId = assistantMsg.id

    isLoading.value = true
    streamingContent.value = ''
    currentInput.value = ''

    if (abortController.value) {
      abortController.value.abort()
    }
    const controller = new AbortController()
    abortController.value = controller
    let fullText = ''

    try {
      const allMessages = chatStore.getActiveMessages()
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
        message_id: assistantMessageId,
        chat_id: chatStore.activeChatId,
      })

      setTimeout(() => scrollToBottom(), 160)

      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
        signal: controller.signal,
      })

      fullText = await readStream(response)

      if (chatStore.activeChatId === chatId) {
        const localMsg = chatStore.currentChatMessages.find((m: any) => m.id === assistantMsg.id)
        if (localMsg) {
          localMsg.content = fullText
        }
        chatStore.editMessage(<number>assistantMsg.id, fullText).catch((e: any) => 
          console.warn('更新助手消息失败', e)
        )
      }

    } catch (error: any) {
      if (error.name === 'AbortError') {
        // ✅ 不管有没有内容，都更新原消息，不新建
        const partialContent = (streamingContent.value.trim() ? streamingContent.value.trim() + '\n\n' : '') + '[已停止]'
        const localMsg = chatStore.currentChatMessages.find((m: any) => m.id === assistantMsg.id)
        if (localMsg) {
          localMsg.content = partialContent
        }
        chatStore.editMessage(<number>assistantMsg.id, partialContent).catch((e) =>
          console.warn('保存截断消息失败', e)
        )
        streamingContent.value = ''
        return
      }
      if (chatStore.activeChatId === chatId) {
        console.error('发送失败:', error)
        const errorContent = `**错误：** ${error.message}`
        const localMsg = chatStore.currentChatMessages.find((m: any) => m.id === assistantMsg.id)
        if (localMsg) {
          localMsg.content = errorContent
        }
        // ✅ 报错也是更新原消息
        chatStore.editMessage(<number>assistantMsg.id, errorContent).catch((e: any) => 
          console.warn('保存错误消息失败', e)
        )
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
    if (!currentModel) {
      message.error('请先选择一个模型')
      return
    }

    isLoading.value = true

    if (abortController.value) {
      abortController.value.abort()
    }
    const controller = new AbortController()
    abortController.value = controller

    const assistantMsg: Message = {
      id: Date.now() + 1,
      role: 'assistant',
      content: '',
    }
    chatStore.addMessageToLocal(assistantMsg)
    await chatStore.saveMessageToBackend(assistantMsg)
    const messageId = assistantMsg.id 

    try {
			const body = JSON.stringify({
				messages: await cleanMessages(chatStore.getActiveMessages()),
				enable_tools: chatStore.enableProfile,
				llm_config: {
					type: currentModel.type,
					model_name: currentModel.modelName,
					base_url: currentModel.baseUrl,
					api_key: currentModel.apiKey,
					thinking: localStorage.getItem('thinking') === 'true' ? 'enabled' : 'disabled'
				},
				profile_id: chatStore.enableProfile ? profileStore.activeProfileId : null,
				message_id: messageId,
        chat_id: chatStore.activeChatId,
			})

      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
        signal: controller.signal,
      })

      const fullText = await readStream(response)
      
      const localMsg = chatStore.currentChatMessages.find(m => m.id === assistantMsg.id)
      if (localMsg) localMsg.content = fullText
      chatStore.editMessage(<number>assistantMsg.id, fullText).catch(e => console.warn(e))

    } catch (error: any) {
      if (error.name === 'AbortError') {
        // ✅ 中止时：必须更新原消息，不管有没有内容
        const partialContent = (streamingContent.value.trim() ? streamingContent.value.trim() + '\n\n' : '') + '[已停止]'
        const localMsg = chatStore.currentChatMessages.find(m => m.id === assistantMsg.id)
        if (localMsg) localMsg.content = partialContent
        chatStore.editMessage(<number>assistantMsg.id, partialContent).catch((e) =>
          console.warn('保存截断消息失败', e)
        )
        streamingContent.value = ''
        return
      }
      // ✅ 报错时：也必须更新原消息
      const errContent = `**错误：** ${error.message}`
      const localMsg = chatStore.currentChatMessages.find(m => m.id === assistantMsg.id)
      if (localMsg) localMsg.content = errContent
      chatStore.editMessage(<number>assistantMsg.id, errContent).catch((e) =>
        console.warn('保存错误消息失败', e)
      )
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
    if (!currentModel) {
      message.error('请先选择一个模型')
      return
    }

    const allMessages = chatStore.getActiveMessages()
    const idx = allMessages.indexOf(assistantMsg)
    if (idx === -1) return

    const history = allMessages.slice(0, idx)
    regeneratingMsg.value = assistantMsg
    const messageId = assistantMsg.id

    isLoading.value = true

    if (abortController.value) {
      abortController.value.abort()
    }
    const controller = new AbortController()
    abortController.value = controller

    // 清空原消息显示，配合 streamingContent 显示流式
    assistantMsg.content = ''
    streamingContent.value = ''

    try {
			const body = JSON.stringify({
				messages: await cleanMessages(history),
				enable_tools: chatStore.enableProfile,
				llm_config: {
					type: currentModel.type,
					model_name: currentModel.modelName,
					base_url: currentModel.baseUrl,
					api_key: currentModel.apiKey,
					thinking: localStorage.getItem('thinking') === 'true' ? 'enabled' : 'disabled'
				},
				profile_id: chatStore.enableProfile ? profileStore.activeProfileId : null,
        message_id: messageId,
        chat_id: chatStore.activeChatId,
			})

      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
        signal: controller.signal,
      })

      const fullText = await readStream(response)

      assistantMsg.content = fullText
      if (assistantMsg.id) {
        fetch(`/api/chats/${chatStore.activeChatId}/messages/${assistantMsg.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ role: 'assistant', content: fullText }),
        }).catch((e) => console.warn('更新消息失败', e))
      }

      if (onStreamEnd.value) {
        onStreamEnd.value(fullText)
      }
    } catch (error: any) {
      if (error.name === 'AbortError') {
        // ✅ 中止时：直接更新原消息，不新建
        const partialContent = (streamingContent.value.trim() ? streamingContent.value.trim() + '\n\n' : '') + '[已停止]'
        assistantMsg.content = partialContent
        if (assistantMsg.id) {
          fetch(`/api/chats/${chatStore.activeChatId}/messages/${assistantMsg.id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ role: 'assistant', content: partialContent }),
          }).catch((e) => console.warn('更新截断消息失败', e))
        }
        streamingContent.value = ''
        return
      }
      // ✅ 报错时：直接更新原消息，不新建
      const errContent = `**错误：** ${error.message}`
      assistantMsg.content = errContent
      if (assistantMsg.id) {
        fetch(`/api/chats/${chatStore.activeChatId}/messages/${assistantMsg.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ role: 'assistant', content: errContent }),
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