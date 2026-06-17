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
      abortController.value = null
    }
    isLoading.value = false
    regeneratingMsg.value = null
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
      // ✅ 只更新原始文本，绝不等待 DOM 更新
      streamingContent.value = fullText
    }
    
    return fullText
  }

  /**
   * 发送新消息
   * @param uploadedFiles 当前上传的文件列表
   * @param scrollToBottom 外部传入的滚动到底部方法
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

    // 1. 构建用户消息
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

    // 2. 加入本地 store
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

    // 3. 准备 API 调用
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
        // 更新本地消息
        const localMsg = chatStore.currentChatMessages.find((m: any) => m.id === assistantMsg.id)
        if (localMsg) {
          localMsg.content = fullText
        }
        // 更新后端
        chatStore.editMessage(<number>assistantMsg.id, fullText).catch((e: any) => 
          console.warn('更新助手消息失败', e)
        )
      }

    } catch (error: any) {
      if (error.name === 'AbortError') {
        if (streamingContent.value.trim()) {
          const partialContent = streamingContent.value.trim() + '\n\n[已停止]'
          const localMsg = chatStore.currentChatMessages.find((m: any) => m.id === assistantMsg.id)
          if (localMsg) {
            localMsg.content = partialContent
          }
          chatStore.editMessage(<number>assistantMsg.id, partialContent).catch((e) =>
            console.warn('保存截断消息失败', e)
          )
          streamingContent.value = ''
        }
        return
      }
      if (chatStore.activeChatId === chatId) {
        console.error('发送失败:', error)
        const errorContent = `**错误：** ${error.message}`
        const localMsg = chatStore.currentChatMessages.find((m: any) => m.id === assistantMsg.id)
        if (localMsg) {
          localMsg.content = errorContent
        }
        chatStore.editMessage(<number>assistantMsg.id, errorContent).catch((e) => 
          console.warn('保存错误消息失败', e)
        )
      }
    } finally {
      abortController.value = null
      isLoading.value = false
      streamingContent.value = ''
      // 流结束后，触发外部传入的缓存回调
      if (onStreamEnd.value && fullText && chatStore.activeChatId === chatId) {
        onStreamEnd.value(fullText) 
      }
    }
  }

  /**
   * 重新生成当前对话（通常用于编辑用户消息后）
   */
  async function regenerateFromCurrentHistory() {
    if (!chatStore.activeChatId) return
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
        if (streamingContent.value.trim()) {
          const partialMsg: Message = {
            role: 'assistant',
            content: streamingContent.value.trim() + '\n\n[已停止]',  // 可加标记
          }
          chatStore.addMessageToLocal(partialMsg)
          chatStore.saveMessageToBackend(partialMsg).catch((e) =>
            console.warn('保存截断消息失败', e)
          )
          streamingContent.value = ''   // 保存后再清空
        }
        return
      }
      const errMsg: Message = { role: 'assistant', content: `错误：${error.message}` }
      chatStore.addMessageToLocal(errMsg)
      chatStore.saveMessageToBackend(errMsg).catch((e) => console.warn(e))
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
    if (!chatStore.activeChatId) return
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
			})

      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
        signal: controller.signal,
      })

      const fullText = await readStream(response)

      // 直接更新原消息对象
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
        if (streamingContent.value.trim()) {
          const partialMsg: Message = {
            role: 'assistant',
            content: streamingContent.value.trim() + '\n\n[已停止]',  // 可加标记
          }
          chatStore.addMessageToLocal(partialMsg)
          chatStore.saveMessageToBackend(partialMsg).catch((e) =>
            console.warn('保存截断消息失败', e)
          )
          streamingContent.value = ''   // 保存后再清空
        }
        return
      }
      console.error('重新生成失败:', error)
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