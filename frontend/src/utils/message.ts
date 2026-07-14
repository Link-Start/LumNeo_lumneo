// src/utils/message.ts
import { ref } from 'vue'
import { type Message } from '@/stores/chat'
import type { UploadedFile } from '@/composables/useFileUpload'

export const localIP = ref('')
export const uploadDir = ref('')

// ============================================================
// 第一部分：实时流式渲染（原封不动，保证流式预览标签正常）
// ============================================================
/** 解析思考块和工具调用，输出 markstream-vue 自定义标签格式 */
export function processMessageContent(text: string, isStreaming = false): string {
  if (!text) return ''
  let processedText = text
  // 1. 处理思考块
  processedText = processedText.replace(
    /<!--reasoning:start-->([\s\S]*?)<!--reasoning:end:(.*?)-->/g,
    (_, content, time) => {
      content = content.replace(/```mermaid(\s|$)/g, '```text$1')
      let safeContent = content.replace(/<\/reasoning>/g, '\u003c/reasoning>')
      if (safeContent.trimEnd().endsWith('```')) {
        safeContent = safeContent.trimEnd() + '\n'
      }
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
    const hasEnd = fullMatch.includes('<!--tool_calls:end-->')
    const startRegex = /<!--tool_preview:start:([^:]+):([\s\S]*?)-->/g
    let sMatch
    const toolsMap = new Map<string, { call_id: string; name: string; streaming: boolean; status: string }>()
    while ((sMatch = startRegex.exec(innerContent)) !== null) {
      const call_id = sMatch[1]
      let name = sMatch[2]
      if (!name) { name = '工具' } 
      else if (name.startsWith('end:')) { name = name.replace(/^end:/, '') }
      if (!toolsMap.has(call_id)) {
        toolsMap.set(call_id, { call_id, name, streaming: true, status: 'calling' })
      }
    }
    const endRegex = /<!--tool_preview:end:([^:]+?)-->/g
    let eMatch
    while ((eMatch = endRegex.exec(innerContent)) !== null) {
      const call_id = eMatch[1]
      if (toolsMap.has(call_id)) {
        const tool = toolsMap.get(call_id)!
        tool.streaming = false
        if (tool.status === 'calling') { tool.status = 'success' }
      }
    }
    const statusRegex = /<!--tool_status:([^:]+?):([^:]+?)-->/g
    let statusMatch
    while ((statusMatch = statusRegex.exec(innerContent)) !== null) {
      const call_id = statusMatch[1]
      const status = statusMatch[2]
      if (toolsMap.has(call_id)) {
        toolsMap.get(call_id)!.status = status
        if (status === 'success' || status === 'error') {
          toolsMap.get(call_id)!.streaming = false
        }
      }
    }
    if (hasEnd) {
      toolsMap.forEach((tool) => {
        if (tool.streaming) {
          tool.streaming = false
          if (tool.status === 'calling') { tool.status = 'success' }
        }
      })
    }
    const toolsData = Array.from(toolsMap.values())
    const loading = toolsData.some(t => t.streaming)
    const tagContent = JSON.stringify({ tools: toolsData, count: toolsData.length, loading: loading })
    const replacement = `\n\n<toolcalls>${tagContent}</toolcalls>\n\n`
    toolCallsResult += processedText.substring(lastIndex, match.index) + replacement
    lastIndex = match.index + fullMatch.length
  }
  if (lastIndex < processedText.length) {
    toolCallsResult += processedText.substring(lastIndex)
  }
  processedText = toolCallsResult
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
      } catch { return '' }
    }
  )
  processedText = processedText.replace(/\n{3,}/g, '\n\n')
  return processedText.trim()
}

// ============================================================
// 第二部分：历史记录渲染（新增，根据 JSON 数组转标签）
// ============================================================
/**
 * 渲染历史记录中的结构化 JSON 内容（替代流式正则，直接遍历数组）
 */
export function renderStructuredContent(content: string): string {
  try {
    const data = JSON.parse(content)
    if (!data.segments || !Array.isArray(data.segments)) {
      return content // 兼容旧数据，若不是新结构则原样返回
    }
    
    let html = ''
    for (const seg of data.segments) {
      if (seg.type === 'reasoning') {
        html += `\n\n<reasoning time="${seg.duration || 0}">${seg.content}</reasoning>\n\n`
      } else if (seg.type === 'tool_call') {
        // 构造轻量工具调用标签（只包含 ID 和状态，前端组件通过 ID 去请求真正的结果）
        const tagContent = JSON.stringify({
          tools: [{
            call_id: seg.id,
            name: seg.name,
            streaming: false,
            status: 'success'
          }],
          count: 1,
          loading: false
        })
        html += `\n\n<toolcalls>${tagContent}</toolcalls>\n\n`
      } else if (seg.type === 'text') {
        html += seg.content
      } else if (seg.type === 'token_usage') {
        const usage = seg.content
        const tagContent = JSON.stringify({
          speed: usage.speed || '0 token/s',
          completion_tokens: usage.final_answer_usage?.completion_tokens ?? 0
        })
        html += `\n\n<tokenusage>${tagContent}</tokenusage>\n\n`
      }
    }
    return html.trim()
  } catch (e) {
    return content // JSON 解析失败则返回原文本
  }
}

// ============================================================
// 第三部分：图像处理工具（保持不变）
// ============================================================
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

export function normalizeFileRef(ref: any): UploadedFile[] {
  if (!ref) return []
  return Array.isArray(ref) ? ref : [ref]
}

// 兼容旧数据的提取工具函数（仅在历史记录不是新 JSON 时兜底使用）
function extractFinalContent(text: string): string {
  let content = text
  content = content.replace(/<!--tool_data:[^:]+:[\s\S]*?-->/g, '')
  const parts = content.split('<!--tool_calls:end-->')
  if (parts.length > 1) { content = parts[parts.length - 1] }
  content = content.replace(/<!--reasoning:start-->([\s\S]*?)<!--reasoning:end:(.*?)-->/g, '')
  content = content.replace(/<!--token_usage:.*?-->/g, '')
  content = content.replace(/<!--tool_calls:start-->[\s\S]*?(?:<!--tool_calls:end-->|$)/g, '')
  content = content.replace(/<!--tool_preview:(start|end):[^>]+-->/g, '')
  content = content.replace(/<!--tool_status:[^>]+-->/g, '')
  return content.trim()
}

// ============================================================
// 第四部分：发送前上下文补全（彻底重构 cleanMessages）
// ============================================================

/**
 * 根据 call_id 列表从后端一次性获取完整的 arguments 和 result
 */
async function fetchToolDetails(callIds: string[]): Promise<Record<string, { arguments: any; result: any }>> {
  if (callIds.length === 0) return {}
  try {
    const resp = await fetch('/api/tool-calls/batch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ call_ids: callIds })
    })
    if (!resp.ok) return {}
    const data = await resp.json()
    // 假设后端返回结构为 { "call_xxx": { arguments: "...", result: "..." } }
    return data || {}
  } catch (e) {
    console.error('获取工具详情失败:', e)
    return {}
  }
}

/**
 * 将包含文件引用的消息列表转换为适合发送给模型的消息格式
 * - 图片文件：转为 base64
 * - 新结构 assistant：解析 JSON 并补全工具调用
 * - 兼容旧结构：按老方法提取纯文本
 */
export async function cleanMessages(msgs: Message[]): Promise<{ role: string; content: string | any[]; tool_calls?: any[]; tool_call_id?: string }[]> {
  const finalMessages: any[] = []

  for (const msg of msgs) {
    // --- 1. 处理用户消息（图像多模态） ---
    if (msg.role === 'user') {
      const fileRefs = normalizeFileRef(msg.file_ref)
      const imageFiles = fileRefs.filter(f => f.type?.startsWith('image/'))
      const nonImageFiles = fileRefs.filter(f => !f.type?.startsWith('image/'))
      const urlhost = window.location.host.replace(/\b(?:localhost|\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b/g, localIP.value)

      let contentForModel: string | any[]
      if (imageFiles.length > 0) {
        const contentArray: any[] = []
        for (const img of imageFiles) {
          const base64 = await urlToBase64(img.url)
          contentArray.push({ type: 'image_url', image_url: { url: base64 } })
        }
        if (typeof msg.content === 'string' && msg.content.trim()) {
          contentArray.push({ type: 'text', text: msg.content.trim() })
        }
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
        let text = typeof msg.content === 'string' ? msg.content : ''
        if (nonImageFiles.length > 0) {
          const fileTips = nonImageFiles.map(f => f.url.replace('/files/uploads', uploadDir.value)).join('\n')
          const mcp_fileTips = nonImageFiles.map(f => f.url.replace('/files/', `http://${urlhost}/files/`)).join('\n')
          text += `\n\n 读取上传文件，若使用系统内置工具(system_)，路径为：\n ${fileTips} \n\n 否则使用url：${mcp_fileTips}`
        }
        contentForModel = text
      }
      finalMessages.push({ role: 'user', content: contentForModel })
      continue
    }

    // --- 2. 处理助手消息 ---
    if (msg.role === 'assistant') {
      // 尝试检测是否为新的结构化 JSON 格式
      let segments: any[] = []
      let isStructured = false
      try {
        const parsed = JSON.parse(typeof msg.content === 'string' ? msg.content : '{}')
        if (parsed.segments && Array.isArray(parsed.segments)) {
          segments = parsed.segments
          isStructured = true
        }
      } catch (e) { /* 不是新格式，走下面的兜底逻辑 */ }

      // 2.1 旧格式兜底
      if (!isStructured) {
        const text = typeof msg.content === 'string' ? extractFinalContent(msg.content) : ''
        finalMessages.push({ role: 'assistant', content: text })
        continue
      }

      // 2.2 新格式展开
      // 提取纯文本片段
      const textSegments = segments.filter((s: any) => s.type === 'text')
      const fullText = textSegments.map((s: any) => s.content).join('')

      // 提取工具调用片段
      const toolSegments = segments.filter((s: any) => s.type === 'tool_call')

      // 如果没有工具调用，直接作为文本发送
      if (toolSegments.length === 0) {
        finalMessages.push({ role: 'assistant', content: fullText || null })
        continue
      }

      // 收集所有 call_id，去数据库补全真正的参数和结果
      const callIds = toolSegments.map((s: any) => s.id)
      const toolDetails = await fetchToolDetails(callIds)

      // 步骤 A：标准 OpenAI 必须的第一条 assistant 消息（带上参数）
      finalMessages.push({
        role: 'assistant',
        content: null, // 标准协议规定：有 tool_calls 时，content 可以为 null
        tool_calls: toolSegments.map((s: any) => ({
          id: s.id,
          type: 'function',
          function: {
            name: s.name,
            arguments: toolDetails[s.id]?.arguments || '{}'
          }
        }))
      })

      // 步骤 B：紧跟其后的所有 role: tool 结果消息
      for (const s of toolSegments) {
        finalMessages.push({
          role: 'tool',
          tool_call_id: s.id,
          content: toolDetails[s.id]?.result || ''
        })
      }

      // 步骤 C：如果有最终文本回复，追加最终 assistant 消息
      if (fullText.trim()) {
        finalMessages.push({
          role: 'assistant',
          content: fullText
        })
      }
    }
  }

  return finalMessages
}