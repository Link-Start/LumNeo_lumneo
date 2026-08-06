// src/composables/useChat.ts
import { ref, h } from 'vue'
import { useDialog, useMessage, NIcon } from 'naive-ui'
import { Warning } from '@vicons/ionicons5'
import { useChatStore, type Message } from '@/stores/chat'
import { useConfigStore } from '@/stores/config'
import { useProfileStore } from '@/stores/profiles'
import { useStrategyStore } from '@/stores/strategy'
import { useCollaborationStore } from '@/stores/collaboration'
import { cleanMessages } from '@/utils/message'
import { useToolStore } from '@/stores/tools'
import type { UploadedFile } from '@/composables/useFileUpload'

// ---------- 单例 ----------
let singleton: any | null = null

export function useChat() {
  if (singleton) return singleton

  const chatStore = useChatStore()
  const toolStore = useToolStore()
  const configStore = useConfigStore()
  const profileStore = useProfileStore()
  const strategyStore = useStrategyStore()
  const collabStore = useCollaborationStore()

  const message = useMessage()
  const dialog = useDialog()

  const currentInput = ref('')
  const isLoading = ref(false)
  const streamingContent = ref('')
  const abortController = ref<AbortController | null>(null)
  const regeneratingMsg = ref<Message | null>(null)

  type StreamEndCallback = (chatId: string, turnIndex: number) => void
  const onStreamEnd = ref<StreamEndCallback | null>(null)

  // ---------- 工具函数：确认弹窗 ----------
  function requestToolConfirm(callId: string, funcName: string, argsJson: string) {
    let prettyArgs = argsJson
    try {
      prettyArgs = JSON.stringify(JSON.parse(argsJson), null, 2)
    } catch (e) {}
    const contentNode = h('div', {
      style: { fontSize: '14px', lineHeight: '1.6' }
    }, [
      h('p', { style: { marginBottom: '12px' } }, [
        '工具 「',
        h('strong', { style: { color: 'var(--primary-color)' } }, toolStore.toolsInfo[funcName]?.title || funcName),
        '」 即将执行，请确认调用参数：'
      ]),
      h('pre', {
        style: {
          background: 'var(--bg-secondary)',
          padding: '12px',
          borderRadius: '6px',
          maxHeight: '300px',
          overflow: 'auto',
          fontSize: '13px',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-all',
          margin: '0',
          border: '1px solid var(--border-color)'
        }
      }, prettyArgs)
    ])

    let countdown = 45
    let timer: number | null = null

    const dialogInstance = dialog.warning({
      icon: () => h(NIcon, { component: Warning, color: 'var(--warning-color)' }),
      title: '工具调用确认',
      content: () => contentNode,
      positiveText: '确认执行',
      negativeText: `取消执行 (${countdown}s)`,
      maskClosable: false,
      closeOnEsc: false,
      onPositiveClick: () => {
        if (timer) clearInterval(timer)
        confirmTool(callId, true)
      },
      onNegativeClick: () => {
        if (timer) clearInterval(timer)
        confirmTool(callId, false)
      },
    })

    timer = window.setInterval(() => {
      countdown--
      if (countdown <= 0) {
        if (timer) clearInterval(timer)
        confirmTool(callId, false)
        dialogInstance.destroy()
      } else {
        const formattedTime = String(countdown).padStart(2, '0')
        dialogInstance.negativeText = `取消执行 (${formattedTime}s)`
      }
    }, 1000)
  }

  async function confirmTool(callId: string, confirmed: boolean) {
    try {
      await fetch('/api/tool-calls/confirm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ call_id: callId, confirmed })
      })
    } catch (e) {
      console.error('发送确认状态失败', e)
    }
  }

  // ---------- 决策弹窗 ----------
  function showDecisionDialog(decisionId: number, data: any) {
    let countdown = 45
    let timer: number | null = null

    const contentNode = h('div', { style: { fontSize: '14px', lineHeight: '1.6' } }, [
      h('p', { style: { marginBottom: '8px' } }, [
        '❌ 工具调用失败，详细信息如下：'
      ]),
      h('ul', { style: { listStyle: 'none', padding: '0', margin: '0 0 12px 0' } }, [
        h('li', {}, [`工具：`, h('strong', {}, data.tool_name || '未知')]),
        h('li', {}, [`失败原因：`, h('span', { style: { color: 'var(--error-color)' } }, data.reason || '未知')]),
        h('li', {}, [`已尝试次数：${data.attempts || 0} 次`]),
        h('li', {}, [`已耗时：${data.elapsed || 0} 秒`]),
        data.suggestion ? h('li', {}, [`建议：`, h('span', { style: { color: 'var(--info-color)' } }, data.suggestion)]) : null
      ].filter(Boolean)),
      h('p', { style: { marginTop: '12px', fontSize: '13px', color: 'var(--text-color-secondary)' } },
        '是否继续尝试其他方法？')
    ])

    const dialogInstance = dialog.warning({
      icon: () => h(NIcon, { component: Warning, color: 'var(--warning-color)' }),
      title: '⏳ 工具执行遇阻',
      content: () => contentNode,
      positiveText: '继续',
      negativeText: `终止 (${countdown}s)`,
      maskClosable: false,
      closeOnEsc: false,
      onPositiveClick: () => {
        if (timer) clearInterval(timer)
        fetch('/api/decisions/update', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ decision_id: decisionId, choice: 'continue' })
        }).catch(err => console.error('更新失败', err))
      },
      onNegativeClick: () => {
        if (timer) clearInterval(timer)
        fetch('/api/decisions/update', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ decision_id: decisionId, choice: 'stop' })
        }).catch(err => console.error('更新失败', err))
      }
    })

    timer = window.setInterval(() => {
      countdown--
      if (countdown <= 0) {
        if (timer) clearInterval(timer)
        fetch('/api/decisions/update', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ decision_id: decisionId, choice: 'stop' })
        }).catch(err => console.error('更新决策失败', err))
        dialogInstance.destroy()
      } else {
        dialogInstance.negativeText = `终止 (${countdown}s)`
      }
    }, 1000)
  }

  // ---------- 流读取 ----------
  async function readStream(response: Response, turnIndex: number): Promise<{ finalSegments?: any[], planData?: any }> {
    if (!response.ok || !response.body) throw new Error('网络响应失败')
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let fullText = ''
    let finalSegments: any[] | undefined = undefined
    let planData: any = null // 记录当前计划数据

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      const chunk = decoder.decode(value, { stream: true })
      fullText += chunk
      streamingContent.value = fullText

      // 检测 model_info 标签（协作策略切换模型时推送）
      const modelInfoMatch = chunk.match(/<!--model_info:([\s\S]*?)-->/)
      if (modelInfoMatch) {
        try {
          const info = JSON.parse(modelInfoMatch[1])
          
          const model = configStore.modelList.find(m => m.id === info.model_id)
          if (model) {
            const chat = chatStore.chats.find(c => c.id === chatStore.activeChatId)
            if (chat) {
              const targetMsg = chat.messages.find(m => m.turn_index === turnIndex && m.role === 'assistant')
              if (targetMsg) {
                targetMsg.model_id = model.id
                targetMsg.model = {
                  id: model.id,
                  name: model.name,
                  type: model.type,
                  modelName: model.modelName
                }
                if (info.reason) {
                  targetMsg.modelSwitchReason = info.reason
                }
              }
            }
          }
        } catch (e) {
          console.warn('解析 model_info 失败', e)
        }
      }

      // 检测 plan_ready 标签（新增）
      const planMatch = chunk.match(/<!--plan_ready:([\s\S]*?)-->/)
      if (planMatch) {
        try {
          const parsed = JSON.parse(planMatch[1])
          if (parsed.type === 'plan' && parsed.id && Array.isArray(parsed.content)) {
            planData = parsed   // 存储最新的 plan 数据（通常只有一次）
          }
        } catch (e) {
          console.warn('解析 plan_ready 失败', e)
        }
      }

      // 检测工具确认请求
      const confirmMatch = chunk.match(/<!--tool_confirm_required:([^:]+):([^:]*):([\s\S]*?)-->/)
      if (confirmMatch) {
        const [, callId, funcName, argsJson] = confirmMatch
        requestToolConfirm(callId, funcName, argsJson)
      }
      // 检测决策请求
      const decisionMatch = chunk.match(/<!--ask_decision:(\d+):([\s\S]*?)-->/)
      if (decisionMatch) {
        const decisionId = parseInt(decisionMatch[1])
        const rawMessage = decisionMatch[2]
        let decisionData: any = { message: rawMessage }
        try {
          decisionData = JSON.parse(rawMessage)
        } catch (e) {
          decisionData = { message: rawMessage, options: [{ label: '继续', value: 'continue' }, { label: '终止', value: 'stop' }] }
        }
        showDecisionDialog(decisionId, decisionData)
      }
      // 检测工具重试开始
      const retryStartMatch = chunk.match(/<!--tool_retry:start:([^:]+)-->/)
      if (retryStartMatch) {
        const [, funcName] = retryStartMatch
        message.info(
          `正在尝试工具：${toolStore.toolsInfo[funcName]?.title || funcName}，请稍等...`,
          { duration: 5000 }
        )
      }
      // 检测工具重试结束
      const retryEndMatch = chunk.match(/<!--tool_retry:end:([^:]+)-->/)
      if (retryEndMatch) {
        const [, funcName] = retryEndMatch
        message.success(
          `已切换至工具：${toolStore.toolsInfo[funcName]?.title || funcName}，继续执行...`,
          { duration: 5000 }
        )
      }
      // 检测工具重试次数
      const retryMatch = chunk.match(/<!--tool_retry:([^:]+):([^:]+):(\d+)\/(\d+):([^:]+)-->/)
      if (retryMatch) {
        const [, callId, funcName, attempt, maxRetries, reason] = retryMatch
        message.warning(
          `第 ${attempt}/${maxRetries} 次重试 调用「${toolStore.toolsInfo[funcName]?.title || funcName}」工具，重试原因：${reason}`,
          { duration: 5000 }
        )
      }

      // 检测错误标记（无法回退时的最终错误）
      const errorMatch = chunk.match(/<!--error:([\s\S]*?)-->/)
      if (errorMatch) {
        try {
          const errorData = JSON.parse(errorMatch[1])
          finalSegments = [{ type: 'text', content: `**❌ 错误：** ${errorData.message}` }]
        } catch (e) {
          finalSegments = [{ type: 'text', content: `**❌ 错误：** ${errorMatch[1]}` }]
        }
      }

      // 提取最终结构化数据
      const match = chunk.match(/<!--segments_complete:([\s\S]*?)-->/)
      if (match) {
        try {
          finalSegments = JSON.parse(match[1])
        } catch (e) {
          console.error('解析最终结构化数据失败', e)
        }
      }
    }
    return { finalSegments, planData }
  }

  // ---------- 保存中断消息 ----------
  async function saveAbortedMessage(chatId: string, turnIndex: number, streamingText: string) {
    const chat = chatStore.chats.find(c => c.id === chatId)
    if (!chat) return

    let targetMsg = chat.messages.find(m => m.turn_index === turnIndex && m.role === 'assistant')
    if (!targetMsg) {
      targetMsg = {
        id: Date.now(),
        role: 'assistant',
        content: '',
        turn_index: turnIndex
      }
      chatStore.addMessageToLocal(targetMsg)
    }

    const suffix = '\n\n[用户停止了生成]'
    let displayContent = streamingText.trim()
    if (displayContent) {
      displayContent += suffix
    } else {
      displayContent = '用户停止了生成'
    }

    const finalSegments = [{ type: "text", content: displayContent }]
    targetMsg.content = JSON.stringify(finalSegments)
    await chatStore.saveMessageToBackend(targetMsg)
  }

  // ---------- 核心发送内部函数 ----------
  async function sendMessageInternal(
    content: string,
    files: UploadedFile[] = [],
    scrollToBottom?: () => void,
    isExecutingPlan: boolean = false,
    plan_id?: string,
  ) {
    if (!content.trim() || isLoading.value || !chatStore.activeChatId) return

    const currentModel = configStore.activeModel
    if (!currentModel) {
      message.error('请先选择一个模型')
      return
    }

    const chatId = chatStore.activeChatId

    // 1. 用户消息
    const userMsg: Omit<Message, 'id' | 'turn_index'> = {
      role: 'user',
      content: content,
      file_ref: files.length > 0 ? files.map((f) => ({ filename: f.filename, type: f.type, url: f.url })) : null,
      plan_id: plan_id
    }
    
    const addedMsg = await chatStore.addMessageToLocal(userMsg)
    if (!addedMsg) return
    await chatStore.saveMessageToBackend(addedMsg)

    // 2. 助手占位
    const assistantTurnIndex = chatStore.getNextTurnIndex()
    const assistantMsg: Message = {
      id: Date.now() + 1,
      role: 'assistant',
      content: '',
      turn_index: assistantTurnIndex,
    }
    chatStore.addMessageToLocal(assistantMsg)

    isLoading.value = true
    streamingContent.value = ''
    if (abortController.value) abortController.value.abort()
    const controller = new AbortController()
    abortController.value = controller

    try {
      const allMessages = chatStore.getActiveMessages()
      allMessages.pop() // 移除占位

      const apiMessages = await cleanMessages(allMessages)

      const body = JSON.stringify({
        messages: apiMessages,
        enable_tools: chatStore.enableProfile,
        llm_config: {
          type: currentModel.type,
          name: currentModel.name,
          model_id: currentModel.id,
          model_name: currentModel.modelName,
          base_url: currentModel.baseUrl,
          api_key: currentModel.apiKey,
          thinking: localStorage.getItem('thinking') === 'true' ? 'enabled' : 'disabled',
          reasoning_effort: (localStorage.getItem('thinkingMode') as 'high' | 'xhigh') || 'high',
        },
        profile_id: chatStore.enableProfile ? profileStore.activeProfileId : null,
        chat_id: chatStore.activeChatId,
        turn_index: assistantTurnIndex,
        plan_id: plan_id,
        is_executing_plan: isExecutingPlan,
        params: strategyStore.getBackendParams(),
        collaboration: collabStore.payload
      })

      if (scrollToBottom) setTimeout(scrollToBottom, 160)

      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
        signal: controller.signal,
      })

      const { finalSegments, planData } = await readStream(response, assistantTurnIndex)

      if (chatStore.activeChatId === chatId && finalSegments) {
        const chat = chatStore.chats.find(c => c.id === chatId)
        if (chat) {
          const targetMsg = chat.messages.find(m => m.turn_index === assistantTurnIndex && m.role === 'assistant')
          if (targetMsg) {
            targetMsg.content = JSON.stringify(finalSegments)
            if (planData) {
              targetMsg.plan_id = planData.id
              targetMsg.plan = planData.content
            } else {
              targetMsg.plan = null
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
      console.error('发送失败:', error)
      const errorContent = `**错误：** ${error.message}`
      const localMsg = chatStore.currentChatMessages.find(m => m.turn_index === assistantTurnIndex && m.role === 'assistant')
      if (localMsg) localMsg.content = errorContent
    } finally {
      abortController.value = null
      isLoading.value = false
      if (onStreamEnd.value && chatStore.activeChatId === chatId) {
        onStreamEnd.value(chatId, assistantTurnIndex)
      }
    }
  }

  // ---------- 对外方法 ----------
  async function sendMessage(uploadedFiles: UploadedFile[], scrollToBottom: () => void) {
    if (!currentInput.value.trim() || isLoading.value || !chatStore.activeChatId) return
    const content = currentInput.value.trim()
    currentInput.value = ''
    await sendMessageInternal(content, uploadedFiles, scrollToBottom, false)
  }

  async function sendPlanMessage(id: string, content: string, scrollToBottom?: () => void) {
    if (!content.trim() || isLoading.value || !chatStore.activeChatId) return
    await sendMessageInternal(content.trim(), [], scrollToBottom, true, id)
  }

  function stopGeneration() {
    if (abortController.value) {
      abortController.value.abort()
    } else {
      isLoading.value = false
      regeneratingMsg.value = null
    }
  }

  // 重新生成当前对话的最后一条回答
  async function regenerateFromCurrentHistory() {
    if (!chatStore.activeChatId || isLoading.value) return
    const currentModel = configStore.activeModel
    if (!currentModel) { 
      message.error('请先选择一个模型') 
      return 
    }

    const chatId = chatStore.activeChatId
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
      const prevMsg = allMessages[allMessages.length - 1]
      const isExecutingPlan = !!prevMsg?.plan_id

      const body = JSON.stringify({
        messages: await cleanMessages(allMessages),
        enable_tools: chatStore.enableProfile,
        llm_config: {
          type: currentModel.type,
          name: currentModel.name,
          model_id: currentModel.id,
          model_name: currentModel.modelName,
          base_url: currentModel.baseUrl,
          api_key: currentModel.apiKey,
          thinking: localStorage.getItem('thinking') === 'true' ? 'enabled' : 'disabled',
          reasoning_effort: (localStorage.getItem('thinkingMode') as 'high' | 'xhigh') || 'high'
        },
        profile_id: chatStore.enableProfile ? profileStore.activeProfileId : null,
        chat_id: chatStore.activeChatId,
        turn_index: assistantTurnIndex,
        plan_id: prevMsg?.plan_id,
        is_executing_plan: isExecutingPlan,
        params: strategyStore.getBackendParams(),
        collaboration: collabStore.payload
      })

      const response = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body, signal: controller.signal })
      const { finalSegments, planData } = await readStream(response, assistantTurnIndex)
      if (chatStore.activeChatId === chatId && finalSegments) {
        const chat = chatStore.chats.find(c => c.id === chatId)
        if (chat) {
          const targetMsg = chat.messages.find(m => m.turn_index === assistantTurnIndex && m.role === 'assistant')
          if (targetMsg) {
            targetMsg.content = JSON.stringify(finalSegments)
            if (planData) {
              targetMsg.plan_id = planData.id
              targetMsg.plan = planData.content
            } else {
              targetMsg.plan = null
            }
          }
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

  // 重新生成特定消息
  async function regenerateResponse(assistantMsg: Message, prevMsg: Message) {

    if (!chatStore.activeChatId || isLoading.value) return
    const currentModel = configStore.activeModel
    if (!currentModel) { 
      message.error('请先选择一个模型')
      return 
    }

    streamingContent.value = ''
    const chatId = chatStore.activeChatId
    regeneratingMsg.value = assistantMsg

    await chatStore.truncateAtTurn(assistantMsg.turn_index)

    isLoading.value = true
    if (abortController.value) abortController.value.abort()
    const controller = new AbortController()
    abortController.value = controller

    const newMsg: Message = {
      id: Date.now() + 1,
      role: 'assistant',
      content: '',
      turn_index: assistantMsg.turn_index,
    }
    chatStore.addMessageToLocal(newMsg)

    try {
      const allMessages = chatStore.getActiveMessages()
      allMessages.pop()

      const isExecutingPlan = !!prevMsg.plan_id
      const body = JSON.stringify({
        messages: await cleanMessages(allMessages),
        enable_tools: chatStore.enableProfile,
        llm_config: {
          type: currentModel.type,
          name: currentModel.name,
          model_id: currentModel.id,
          model_name: currentModel.modelName,
          base_url: currentModel.baseUrl,
          api_key: currentModel.apiKey,
          thinking: localStorage.getItem('thinking') === 'true' ? 'enabled' : 'disabled',
          reasoning_effort: (localStorage.getItem('thinkingMode') as 'high' | 'xhigh') || 'high'
        },
        profile_id: chatStore.enableProfile ? profileStore.activeProfileId : null,
        chat_id: chatStore.activeChatId,
        turn_index: assistantMsg.turn_index,
        plan_id: prevMsg.plan_id,
        is_executing_plan: isExecutingPlan,
        params: strategyStore.getBackendParams(),
        collaboration: collabStore.payload
      })

      const response = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body, signal: controller.signal })
      const { finalSegments, planData } = await readStream(response, assistantMsg.turn_index)

      if (chatStore.activeChatId === chatId && finalSegments) {
        const chat = chatStore.chats.find(c => c.id === chatId)
        if (chat) {
          const targetMsg = chat.messages.find(m => m.turn_index === assistantMsg.turn_index && m.role === 'assistant')
          if (targetMsg) {
            targetMsg.content = JSON.stringify(finalSegments)
            if (planData) {
              targetMsg.plan_id = planData.id
              targetMsg.plan = planData.content
            } else {
              targetMsg.plan = null
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

  // 构建单例结果
  const result = {
    currentInput,
    isLoading,
    streamingContent,
    regeneratingMsg,
    onStreamEnd,
    sendMessage,
    sendPlanMessage,
    regenerateResponse,
    regenerateFromCurrentHistory,
    stopGeneration,
  }

  singleton = result
  return result
}