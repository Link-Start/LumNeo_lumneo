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
  plan?: any
  plan_id?: string
  model?: any
  model_id?: string
  turn_index: number
  modelSwitchReason?: string
}

export interface Chat {
  id: string
  title: string
  messages: Message[]
  type?: 'chat' | 'life'  // 新增：对话类型
}

export const useChatStore = defineStore('chat', () => {
  const chats = ref<Chat[]>([])
  const activeChatId = ref<string>('')
  const enableProfile = ref(localStorage.getItem('enableProfile') === 'true')
  const profileStore = useProfileStore()

  // ========== 新增：双模式状态 ==========
  const mode = ref<'chat' | 'life'>('chat')

  function setMode(newMode: 'chat' | 'life') {
    mode.value = newMode
    activeChatId.value = ''
    localStorage.setItem('lumneo_mode', newMode)
  }

  // 初始化恢复模式
  const savedMode = localStorage.getItem('lumneo_mode') as 'chat' | 'life' | null
  if (savedMode) mode.value = savedMode

  // 按当前模式过滤的对话列表（侧边栏只显示同类型）
  const currentModeChats = computed(() =>
    chats.value.filter(c => (c.type || 'chat') === mode.value)
  )

  async function loadChats() {
    try {
      const res = await fetch('/api/chats/')
      const data = await res.json()
      chats.value = data.map((c: any) => ({
        id: c.id,
        title: c.title,
        messages: [],
        type: c.type || 'chat'
      }))
    } catch (e) {
      console.error('加载对话列表失败', e)
    }
  }

  // 创建新对话（支持指定类型，默认跟随当前模式）
  async function addChat(chatType?: 'chat' | 'life') {
    const type = chatType || mode.value
    if (type === 'life') {
      const existing = chats.value.find(c => c.type === 'life')
      if (existing) return existing.id
    }
    const res = await fetch('/api/chats/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type })
    })
    const newChat = await res.json()
    newChat.messages = []
    newChat.type = type
    chats.value.unshift(newChat)
    activeChatId.value = newChat.id
    return newChat.id
  }

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

  async function deleteChat(chatId: string) {
    await fetch(`/api/chats/${chatId}`, { method: 'DELETE' })
    chats.value = chats.value.filter(c => c.id !== chatId)
    if (activeChatId.value === chatId && chats.value.length > 0) {
      activeChatId.value = chats.value[0].id
    } else if (chats.value.length === 0) {
      await addChat()
    }
  }

  async function loadMessages(chatId: string) {
    if (!chats.value.length) {
      await loadChats()
    }
    const chat = chats.value.find(c => c.id === chatId)
    if (!chat) return
    const res = await fetch(`/api/chats/${chatId}/messages`)
    const msgs = await res.json()
    chat.messages = msgs
  }

  const currentChatMessages = computed(() => {
    const chat = chats.value.find(c => c.id === activeChatId.value)
    return chat ? chat.messages.filter(m => m.role !== 'system') : []
  })

  function getActiveMessages(): Message[] {
    const chat = chats.value.find(c => c.id === activeChatId.value)
    return chat ? [...chat.messages] : []
  }

  function getNextTurnIndex(): number {
    const chat = chats.value.find(c => c.id === activeChatId.value)
    if (!chat || chat.messages.length === 0) return 1
    const maxTurn = Math.max(...chat.messages.map(m => m.turn_index), 0)
    return maxTurn + 1
  }

  async function addMessageToLocal(msg: Omit<Message, 'turn_index' | 'id'>): Promise<Message | undefined> {
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
      model: msg.model,
      turn_index: getNextTurnIndex()
    }
    chat.messages.push(newMsg)

    if (msg.role === 'user' && chat.messages.filter(m => m.role === 'user').length === 1) {
      const contentText = typeof msg.content === 'string' ? msg.content : ''
      chat.title = contentText.substring(0, 15) + (contentText.length > 15 ? '...' : '')
      fetch(`/api/chats/${chat.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: chat.title })
      }).catch(() => {})
    }
    return newMsg
  }

  function updateMessageId(turnIndex: number, newId: number) {
    const chat = chats.value.find(c => c.id === activeChatId.value)
    if (!chat) return
    const msg = chat.messages.find(m => m.turn_index === turnIndex && m.role === 'assistant')
    if (msg) {
      msg.id = newId
    }
  }

  async function saveMessageToBackend(msg: Message) {
    if (!activeChatId.value) return
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
        profile_id: profileStore.activeProfile?.id,
        plan_id: msg.plan_id,
        model_id: msg.model_id || localStorage.getItem('llm_active_model_id'),
        turn_index: msg.turn_index
      })
    })
    const data = await res.json()
    if (data.id != null) {
      msg.id = data.id
    }
  }

  async function truncateAtTurn(turnIndex: number) {
    const chat = chats.value.find(c => c.id === activeChatId.value)
    if (!chat) return
    await fetch(`/api/chats/${activeChatId.value}/messages/${turnIndex}`, {
      method: 'DELETE'
    }).catch(e => console.warn('截断失败', e))
    chat.messages = chat.messages.filter(m => m.turn_index < turnIndex)
  }

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

  async function deleteMessage(messageId: number) {
    const chat = chats.value.find(c => c.id === activeChatId.value)
    if (!chat) return
    const msg = chat.messages.find(m => m.id === messageId)
    if (!msg) return
    await truncateAtTurn(msg.turn_index)
  }

  return {
    chats,
    activeChatId,
    enableProfile,
    mode,
    currentModeChats,
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
    truncateAtTurn,
    setMode,
  }
})