// src/utils/message.ts
import { ref } from 'vue'
import { type Message } from '@/stores/chat'
import type { UploadedFile } from '@/composables/useFileUpload'


export const localIP = ref('')
export const uploadDir = ref('')


/** 解析思考块和工具调用，输出 markstream-vue 自定义标签格式 */
/** 解析工具预览标记，输出 <toolpreview> 自定义标签 */
export function processMessageContent(text: string, isStreaming = false): string {
  if (!text) return ''
  let processedText = text
  // 1. 处理思考块
  processedText = processedText.replace(
    /<!--reasoning:start-->([\s\S]*?)<!--reasoning:end:(.*?)-->/g,
    (_, content, time) => {
      content = content.replace(/```mermaid(\s|$)/g, '```text$1')
      const safeContent = content.replace(/<\/reasoning>/g, '\u003c/reasoning>')
      return `\n\n<reasoning time="${time}">${safeContent}</reasoning>\n\n`
    }
  )
  if (isStreaming) {
    const startIdx = processedText.indexOf('<!--reasoning:start-->')
    if (startIdx !== -1 && !processedText.includes('<!--reasoning:end:')) {
      let afterStart = processedText.substring(startIdx + '<!--reasoning:start-->'.length)
      afterStart = afterStart.replace(/```mermaid(\s|$)/g, '```text$1')
      const safeContent = afterStart.replace(/<\/reasoning>/g, '\u003c/reasoning>')
      processedText = processedText.substring(0, startIdx) + `\n\n<reasoning loading="true">${safeContent}`
    }
  }
  // 2. 处理工具调用容器
  let match
  let lastIndex = 0
  let toolCallsResult = ''
  const toolCallsRegex = /<!--tool_calls:start-->([\s\S]*?)(?:<!--tool_calls:end-->|$)/g
  while ((match = toolCallsRegex.exec(processedText)) !== null) {
    const fullMatch = match[0]
    const innerContent = match[1]
    // 判断当前是否已经收到 tool_calls:end 标记
    const hasEnd = fullMatch.includes('<!--tool_calls:end-->')
    // 1. 解析内部的所有 tool_preview:start (获取 call_id 和 name)
    const startRegex = /<!--tool_preview:start:([^:]+):([\s\S]*?)-->/g
    let sMatch
    const toolsMap = new Map<string, { call_id: string; name: string; streaming: boolean; status: string }>()
    while ((sMatch = startRegex.exec(innerContent)) !== null) {
      const call_id = sMatch[1]
      let name = sMatch[2]
      if (!name) {
        name = '工具'
      } else if (name.startsWith('end:')) {
        name = name.replace(/^end:/, '')
      }
      if (!toolsMap.has(call_id)) {
        toolsMap.set(call_id, { call_id, name, streaming: true, status: 'calling' })
      }
    }
    // 无论是否收到 tool_calls:end，都解析 tool_preview:end
    // 因为在流式传输中，单个工具可能已经执行完毕（已收到 tool_preview:end），
    // 但整个 tool_calls 块的 end 标记可能还没到
    const endRegex = /<!--tool_preview:end:([^:]+?)-->/g
    let eMatch
    while ((eMatch = endRegex.exec(innerContent)) !== null) {
      const call_id = eMatch[1]
      if (toolsMap.has(call_id)) {
        const tool = toolsMap.get(call_id)!
        tool.streaming = false
        // 如果 status 仍为 'calling'，说明后端没发 error，默认标记为 success
        if (tool.status === 'calling') {
          tool.status = 'success'
        }
      }
    }
    // 解析 tool_status 标记（更新工具状态）
    const statusRegex = /<!--tool_status:([^:]+?):([^:]+?)-->/g
    let statusMatch
    while ((statusMatch = statusRegex.exec(innerContent)) !== null) {
      const call_id = statusMatch[1]
      const status = statusMatch[2] // 'success' 或 'error'
      if (toolsMap.has(call_id)) {
        toolsMap.get(call_id)!.status = status
        // 收到 status 标记说明工具已执行完毕，同步更新 streaming
        if (status === 'success' || status === 'error') {
          toolsMap.get(call_id)!.streaming = false
        }
      }
    }
    // 如果 hasEnd 为 true，将所有仍处于 streaming 状态的工具强制设为已完成
    if (hasEnd) {
      toolsMap.forEach((tool) => {
        if (tool.streaming) {
          tool.streaming = false
          if (tool.status === 'calling') {
            tool.status = 'success'
          }
        }
      })
    }
    const toolsData = Array.from(toolsMap.values())
    const loading = toolsData.some(t => t.streaming)
    const tagContent = JSON.stringify({
      tools: toolsData,
      count: toolsData.length,
      loading: loading
    })
    const replacement = `\n\n<toolcalls>${tagContent}</toolcalls>\n\n`
    toolCallsResult += processedText.substring(lastIndex, match.index) + replacement
    lastIndex = match.index + fullMatch.length
  }
  // 拼接剩余未匹配的文本
  if (lastIndex < processedText.length) {
    toolCallsResult += processedText.substring(lastIndex)
  }
  processedText = toolCallsResult
  // 保底清理：清理可能残留在外面的 tool_preview 和 tool_call 标记
  processedText = processedText.replace(/<!--tool_preview:(start|end):[^>]+-->/g, '')
  processedText = processedText.replace(/<!--tool_call:[^>]+-->/g, '')
  // 3. 处理 Token 用量
  processedText = processedText.replace(
    /<!--token_usage:(.*?)-->/g,
    (_, jsonStr) => {
      try {
        const data = JSON.parse(jsonStr)
        const tagContent = JSON.stringify({
          speed: data.speed || '0 token/s',
          completion_tokens: data.final_answer_usage?.completion_tokens ?? 0
        })
        return `\n\n<tokenusage>${tagContent}</tokenusage>\n\n`
      } catch {
        return ''
      }
    }
  )
  // 清理多余换行
  processedText = processedText.replace(/\n{3,}/g, '\n\n')
  return processedText.trim()
}

/** 将图片引用转为 base64 */
export async function urlToBase64(url: string): Promise<string> {
  const response = await fetch(url)
  const blob = await response.blob()
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onloadend = () => resolve(reader.result as string)
    reader.onerror = reject
    reader.readAsDataURL(blob)
  })
}

/** 统一 file_ref 为数组 */
export function normalizeFileRef(ref: any): UploadedFile[] {
  if (!ref) return []
  return Array.isArray(ref) ? ref : [ref]
}

/**
 * 将包含文件引用的消息列表转换为适合发送给模型的消息格式
 * - 图片文件：转换为 base64 并嵌入多模态 content 数组
 * - 非图片文件：在消息文本末尾附加工具调用提示
 */
export async function cleanMessages(msgs: Message[]): Promise<{ role: string; content: string | any[] }[]> {
  const promises = msgs.map(async (msg) => {
    const fileRefs = normalizeFileRef(msg.file_ref)

    // 分离图片和非图片文件
    const imageFiles = fileRefs.filter(f => f.type?.startsWith('image/'))
    const nonImageFiles = fileRefs.filter(f => !f.type?.startsWith('image/'))

    // 如果没有文件，直接返回原内容
    if (imageFiles.length === 0 && nonImageFiles.length === 0) {
      return { role: msg.role, content: msg.content }
    }

    // 获取本地 IP 地址
    const urlhost = window.location.host.replace(/\b(?:localhost|\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b/g, localIP.value)

    // --- 处理图片：构建多模态 content ---
    let contentForModel: string | any[]
    if (imageFiles.length > 0) {
      const contentArray: any[] = []

      // 1. 图片转 base64 并嵌入
      for (const img of imageFiles) {
        const base64 = await urlToBase64(img.url)
        contentArray.push({
          type: 'image_url',
          image_url: { url: base64 }
        })
      }

      // 2. 文本部分
      if (typeof msg.content === 'string' && msg.content.trim()) {
        contentArray.push({ type: 'text', text: msg.content.trim() })
      }

      // 3. 非图片文件提示（如果有）
      if (nonImageFiles.length > 0) {
        const fileTips = nonImageFiles.map(f => f.url.replace('/files/uploads', uploadDir.value)).join('\n')
        const mcp_fileTips = nonImageFiles.map(f => f.url.replace('/files/', `http://${urlhost}/files/`)).join('\n')
        contentArray.push({
          type: 'text',
          text: `\n\n 读取上传文件，若使用系统内置工具(system_)，路径为：\n ${fileTips} \n\n 否则使用url：${mcp_fileTips}`
        })
      }

      contentForModel = contentArray
    } else {
      // --- 纯文本 + 文档提示 ---
      let text = typeof msg.content === 'string' ? msg.content : ''
      if (nonImageFiles.length > 0) {
        const fileTips = nonImageFiles.map(f => f.url.replace('/files/uploads', uploadDir.value)).join('\n')
        const mcp_fileTips = nonImageFiles.map(f => f.url.replace('/files/', `http://${urlhost}/files/`)).join('\n')
        text += `\n\n 读取上传文件，若使用系统内置工具(system_)，路径为：\n ${fileTips} \n\n 否则使用url：${mcp_fileTips}`
      }
      contentForModel = text
    }

    return { role: msg.role, content: contentForModel }
  })

  return Promise.all(promises)
}