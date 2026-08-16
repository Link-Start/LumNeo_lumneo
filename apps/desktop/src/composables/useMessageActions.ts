// src/composables/useMessageActions.ts
import { ref } from 'vue'
import { useChatStore, type Message } from '@/stores/chat'

/**
 * 清洗内容：只提取 JSON 中的纯文本片段（过滤思考、工具调用等）
 */
function cleanReasoning(content: string) {
  try {
    const parsed = JSON.parse(content)
    if (Array.isArray(parsed)) {
      // 提取所有 type: 'text' 的内容，用换行拼接
      return parsed
        .filter((item: any) => item.type === 'text')
        .map((item: any) => item.content)
        .join('\n\n')
        .trim()
    }
  } catch (e) {
    // 如果解析失败，说明是纯文本（例如 user 消息），直接返回原内容
    return content
  }
  return content
}

export function useMessageActions() {
  const chatStore = useChatStore()

  const showEditModal = ref(false)
  const editingMsg = ref<Message | null>(null)
  const editContent = ref('')
  const copySvgName = ref('copy')

  // ---------- 复制消息 ----------
  async function copyContent(msg: Message) {
    const textToCopy = cleanReasoning(msg.content)
    let copySuccess = false

    // 1. 优先使用现代 Clipboard API
    if (navigator.clipboard && window.isSecureContext) {
      try {
        await navigator.clipboard.writeText(textToCopy)
        copySuccess = true
      } catch (err) {
        console.warn('Clipboard API 失败:', err)
      }
    }

    // 2. 降级方案：传统 execCommand
    if (!copySuccess) {
      const textarea = document.createElement('textarea')
      textarea.value = textToCopy
      textarea.style.position = 'fixed'
      textarea.style.top = '-9999px'
      textarea.style.left = '-9999px'
      textarea.style.opacity = '0'
      document.body.appendChild(textarea)
      textarea.select()
      textarea.setSelectionRange(0, 99999)
      try {
        copySuccess = document.execCommand('copy')
      } catch (err) {
        console.warn('execCommand 复制失败:', err)
      }
      document.body.removeChild(textarea)
    }

    copySvgName.value = 'succ'
    setTimeout(() => {
      copySvgName.value = 'copy'
    }, 1000)
  }

  // ---------- 开启编辑弹窗 ----------
  function startEditMessage(msg: Message) {
    editingMsg.value = msg

    if (msg.role === 'assistant') {
      // 直接解析 JSON 数组，提取 text 片段
      let textToEdit = ''
      try {
        const parsed = JSON.parse(msg.content)
        if (Array.isArray(parsed)) {
          const textItems = parsed
            .filter((item: any) => item.type === 'text')
            .map((item: any) => item.content)
          textToEdit = textItems.join('\n\n')
        }
      } catch (e) {
        // 极端情况：若 JSON 错误，留空
        textToEdit = ''
      }
      editContent.value = textToEdit
    } else {
      // user 消息直接取文本
      editContent.value = msg.content
    }

    showEditModal.value = true
  }

  // ---------- 保存编辑 ----------
  async function saveEdit(regenerateCallback?: () => Promise<void>) {
    if (!editingMsg.value) return
    const msg = editingMsg.value
    const newText = editContent.value.trim()

    // 如果内容没有实质变化，直接关闭
    if (newText === cleanReasoning(msg.content)) {
      showEditModal.value = false
      return
    }

    let finalContent = newText

    // 处理助手消息的更新：精准替换 segments 中的 text 片段
    if (msg.role === 'assistant') {
      try {
        const parsed = JSON.parse(msg.content)
        if (Array.isArray(parsed)) {
          // 将原 segments 中所有 type: 'text' 的内容替换为 newText
          const newSegments = parsed.map((item: any) => {
            if (item.type === 'text') {
              return { ...item, content: newText }
            }
            return item
          })
          finalContent = JSON.stringify(newSegments)
        } else {
          // 如果不是数组，直接作为纯文本
          finalContent = newText
        }
      } catch (e) {
        // 解析失败，当作纯文本处理
        finalContent = newText
      }
    }

    // 更新本地 Store 并同步后端
    msg.content = finalContent
    await chatStore.editMessage(msg.id!, finalContent)
    showEditModal.value = false

    // 如果编辑的是用户消息，截断后续对话并重新生成
    if (msg.role === 'user') {
      const msgs = chatStore.currentChatMessages
      const idx = msgs.findIndex((m) => m.id === msg.id)
      if (idx !== -1 && idx < msgs.length - 1) {
        const nextMsg = msgs[idx + 1]
        await chatStore.deleteMessage(nextMsg.id!)
      }
      if (regenerateCallback) {
        await regenerateCallback()
      }
    }
  }

  // ---------- 重命名对话 ----------
  const renamingChatId = ref<string | null>(null)
  const renameText = ref('')

  function startRename(chat: { id: string; title: string }) {
    renamingChatId.value = chat.id
    renameText.value = chat.title
  }

  async function confirmRename(chatId: string) {
    if (!renameText.value.trim()) return
    await chatStore.renameChat(chatId, renameText.value.trim())
    renamingChatId.value = null
  }

  return {
    showEditModal,
    editingMsg,
    editContent,
    copySvgName,
    copyContent,
    startEditMessage,
    saveEdit,
    renamingChatId,
    renameText,
    startRename,
    confirmRename,
  }
}