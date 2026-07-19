// src/stores/chat.ts
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useProfileStore } from './profiles'

export interface Message {
  id: number
  role: 'user' | 'assistant' | 'system'
  content: any
  file_ref?: any
  profile?: any
  turn_index: number
}

export interface Chat {
  id: string
  title: string
  messages: Message[]
}

export const useChatStore = defineStore('chat', () => {
  const chats = ref<Chat[]>([])
  const activeChatId = ref<string>('')
  const enableProfile = ref(localStorage.getItem('enableProfile') === 'true')
  const profileStore = useProfileStore()

  // 从后端加载对话列表
  async function loadChats() {
    try {
      const res = await fetch('/api/chats/')
      const data = await res.json()
      chats.value = data.map((c: any) => ({ id: c.id, title: c.title, messages: [] }))
    } catch (e) {
      console.error('加载对话列表失败', e)
    }
  }

  // 创建新对话
  async function addChat() {
    const res = await fetch('/api/chats/', { method: 'POST' })
    const newChat = await res.json()
    newChat.messages = []
    chats.value.unshift(newChat)
    activeChatId.value = newChat.id
    return newChat.id
  }

  // 重命名对话
  async function renameChat(chatId: string, newTitle: string) {
    const chat = chats.value.find(c => c.id === chatId)
    if (!chat) return
    chat.title = newTitle
    await fetch(`/api/chats/${chatId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: newTitle })
    }).catch(e => console.warn('重命名失败', e))
  }

  // 删除对话
  async function deleteChat(chatId: string) {
    await fetch(`/api/chats/${chatId}`, { method: 'DELETE' })
    chats.value = chats.value.filter(c => c.id !== chatId)
    if (activeChatId.value === chatId && chats.value.length > 0) {
      activeChatId.value = chats.value[0].id
    } else if (chats.value.length === 0) {
      await addChat()
    }
  }

  // 加载某个对话的历史消息
  async function loadMessages(chatId: string) {
    if (!chats.value.length) {
      await loadChats()
    }
    const chat = chats.value.find(c => c.id === chatId)
    if (!chat) return
    const res = await fetch(`/api/chats/${chatId}/messages`)
    const msgs = await res.json()
    // 后端返回的 assistant.content 已经是完整的 JSON 字符串，直接存储
    chat.messages = msgs    
  }

  // 当前对话的消息（过滤 system）
  const currentChatMessages = computed(() => {
    const chat = chats.value.find(c => c.id === activeChatId.value)
    return chat ? chat.messages.filter(m => m.role !== 'system') : []
  })

  // 获取完整消息
  function getActiveMessages(): Message[] {
    const chat = chats.value.find(c => c.id === activeChatId.value)
    return chat ? [...chat.messages] : []
  }

  // 【新增】自动计算当前对话的下一轮次
  function getNextTurnIndex(): number {
    const chat = chats.value.find(c => c.id === activeChatId.value)
    if (!chat || chat.messages.length === 0) return 1
    // 取当前对话最大的 turn_index 加 1
    const maxTurn = Math.max(...chat.messages.map(m => m.turn_index), 0)
    return maxTurn + 1
  }

  // ---------- 立即添加到本地（不等待后端） ----------
  async function addMessageToLocal(msg: Omit<Message, 'turn_index' | 'id'>) {
    const chat = chats.value.find(c => c.id === activeChatId.value)
    
    if (!chat) return
    const newMsg: Message = {
      ...msg,
      id: Date.now(),
      profile: {
        id: profileStore.activeProfile?.id,
        name: profileStore.activeProfile?.name,
        avatar: profileStore.activeProfile?.avatar
      },
      turn_index: getNextTurnIndex() // 自动注入轮次
    }
    chat.messages.push(newMsg)
    
    // 自动更新标题（取第一条用户消息）
    if (msg.role === 'user' && chat.messages.filter(m => m.role === 'user').length === 1) {
      const contentText = typeof msg.content === 'string' ? msg.content : ''
      chat.title = contentText.substring(0, 15) + (contentText.length > 15 ? '...' : '')
      fetch(`/api/chats/${chat.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: chat.title })
      }).catch(() => {})
    }
  }
  // 更新消息id
  function updateMessageId(turnIndex: number, newId: number) {
    const chat = chats.value.find(c => c.id === activeChatId.value)
    if (!chat) return
    const msg = chat.messages.find(m => m.turn_index === turnIndex && m.role === 'assistant')
    if (msg) {
      msg.id = newId
    }
}

  // ---------- 异步保存到后端 ----------
  async function saveMessageToBackend(msg: Message) {
    if (!activeChatId.value) return
    // 参数中不再包含 tool_calls 和 tool_call_id
    const res = await fetch(`/api/chats/${activeChatId.value}/messages`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ 
        role: msg.role, 
        content: msg.content,
        file_ref: Array.isArray(msg.file_ref) 
          ? msg.file_ref.map(f => ({ filename: f.filename, type: f.type, url: f.url })) 
          : msg.file_ref 
            ? { filename: msg.file_ref.filename, type: msg.file_ref.type, url: msg.file_ref.url }
            : null,
        turn_index: msg.turn_index
      })
    })
    const data = await res.json()
    if (data.id != null) {
      msg.id = data.id
    }
  }

  // ---------- 截断编辑：重新生成 / 重试 ----------
  async function truncateAtTurn(turnIndex: number) {
    const chat = chats.value.find(c => c.id === activeChatId.value)
    if (!chat) return

    // 1. 调用后端截断接口 (按 turn_index 删除该轮次及之后所有消息)
    await fetch(`/api/chats/${activeChatId.value}/messages/${turnIndex}`, {
      method: 'DELETE'
    }).catch(e => console.warn('截断失败', e))

    // 2. 更新本地状态：移除该轮次及后续所有消息
    chat.messages = chat.messages.filter(m => m.turn_index < turnIndex)
  }

  // ---------- 精确更新某一条消息（修改文本/内容，不触发截断） ----------
  async function editMessage(messageId: number, newContent: any) {
    const chat = chats.value.find(c => c.id === activeChatId.value)
    if (!chat) return
    const msg = chat.messages.find(m => m.id === messageId)
    if (msg) {
      msg.content = newContent
      await fetch(`/api/chats/${activeChatId.value}/messages/${messageId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: newContent })
      }).catch(e => console.warn('更新消息失败', e))
    }
  }

  // ---------- 删除消息（重构为截断逻辑） ----------
  async function deleteMessage(messageId: number) {
    const chat = chats.value.find(c => c.id === activeChatId.value)
    if (!chat) return
    const msg = chat.messages.find(m => m.id === messageId)
    if (!msg) return
    // 找到这一条的轮次后，直接调用截断删除
    await truncateAtTurn(msg.turn_index)
  }

  return {
    chats,
    activeChatId,
    enableProfile,
    currentChatMessages,
    loadChats,
    addChat,
    renameChat,
    deleteChat,
    loadMessages,
    getActiveMessages,
    getNextTurnIndex,
    addMessageToLocal,
    saveMessageToBackend,
    updateMessageId,
    editMessage,
    deleteMessage,
    truncateAtTurn
  }
})