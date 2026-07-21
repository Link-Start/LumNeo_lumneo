// src/utils/message.ts
import { ref } from 'vue'
import { type Message } from '@/stores/chat'
import type { UploadedFile } from '@/composables/useFileUpload'

export const localIP = ref('')
export const uploadDir = ref('')

// ============================================================
// 第一部分：实时流式渲染
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

// 检查缓冲区是否全是 tool_call（用于决定是否直接输出 toolcalls）
function isAllToolCalls(items: any[]): boolean {
  return items.length > 0 && items.every(seg => seg.type === 'tool_call')
}

// ============================================================
// 第二部分：历史记录渲染（根据 JSON 数组转标签）
// ============================================================
/**
 * 解析后端返回的结构化 JSON 数组，并转换为 markstream-vue 自定义标签字符串
 * @param input - 后端返回的 JSON 字符串或已解析的数组 (例如: [{"type": "reasoning", ...}, {"type": "text", ...}])
 * @returns 渲染好的 HTML 标签字符串
 */
export function renderStructuredContent(input: string | any[]): string {
  let segments: any[] = []

  // 1. 解析输入
  if (typeof input === 'string') {
    try {
      const parsed = JSON.parse(input)
      if (Array.isArray(parsed)) {
        segments = parsed
      } else {
        return input
      }
    } catch (e) {
      return input
    }
  } else if (Array.isArray(input)) {
    segments = input
  } else {
    return String(input || '')
  }

  // 2. 用于暂存连续的 reasoning / tool_call
  const thinkingItems: any[] = []

  // 3. 将暂存的一组思考项输出为一个标签
  const flushThinkingGroup = (): string => {
    if (thinkingItems.length === 0) return ''

    // 只有一个项时，保持原有独立标签输出，不额外包裹
    if (thinkingItems.length === 1) {
      const seg = thinkingItems[0]
      thinkingItems.length = 0
      if (seg.type === 'reasoning') {
        return `\n\n<reasoning time="${seg.duration || 0}">${seg.content}</reasoning>\n\n`
      } else if (seg.type === 'tool_call') {
        // 单个工具调用也用 toolcalls 标签展示
        const tagContent = JSON.stringify({
          tools: [{
            call_id: seg.content?.id,
            name: seg.content?.name || '工具',
            streaming: false,
            status: seg.content?.status || 'success',
            error_message: seg.content?.error_message || null
          }],
          count: 1,
          loading: false
        })
        return `\n\n<toolcalls>${tagContent}</toolcalls>\n\n`
      }
      return ''
    }

    // 全是 tool_call → 合并成一个 toolcalls 标签
    if (isAllToolCalls(thinkingItems)) {
      const allTools = thinkingItems.map(seg => ({
        call_id: seg.content?.id,
        name: seg.content?.name || '工具',
        streaming: false,
        status: seg.content?.status || 'success',
        error_message: seg.content?.error_message || null
      }))

      const tagContent = JSON.stringify({
        tools: allTools,
        count: allTools.length,
        loading: false
      })
      thinkingItems.length = 0
      return `\n\n<toolcalls>${tagContent}</toolcalls>\n\n`
    }

    // 多个项：合并为统一结构，便于 thinking-group 组件渲染
    const mergedNodes: any[] = []
    let tempTools: any[] = []

    // 将连续的 tool_call 合并成一个 toolcalls 节点，reasoning 单独保留
    const pushToolCalls = () => {
      if (tempTools.length > 0) {
        mergedNodes.push({
          type: 'toolcalls',
          tools: tempTools,
          count: tempTools.length,
          loading: false
        })
        tempTools = []
      }
    }

    for (const seg of thinkingItems) {
      if (seg.type === 'reasoning') {
        pushToolCalls() // 先输出积累的工具调用
        mergedNodes.push({
          type: 'reasoning',
          time: seg.duration || 0,
          content: seg.content
        })
      } else if (seg.type === 'tool_call') {
        tempTools.push({
          call_id: seg.content?.id,
          name: seg.content?.name || '工具',
          streaming: false,
          status: seg.content?.status || 'success',
          error_message: seg.content?.error_message || null
        })
      }
    }
    pushToolCalls() // 尾部剩余的工具调用

    const jsonStr = JSON.stringify(mergedNodes)
    const encoded = btoa(unescape(encodeURIComponent(jsonStr)))
    thinkingItems.length = 0
    return `\n\n<thinking-group items='${encoded}'></thinking-group>\n\n`
  }

  // 4. 遍历所有片段，构建结果字符串
  let resultHtml = ''
  for (const seg of segments) {
    const { type } = seg

    if (type === 'reasoning' || type === 'tool_call') {
      // 收集到连续思考链
      thinkingItems.push(seg)
    } else {
      // 先输出之前积攒的思考链
      resultHtml += flushThinkingGroup()

      // 再处理当前非思考片段
      if (type === 'text') {
        resultHtml += seg.content
      } else if (type === 'token_usage') {
        const tokenTagContent = JSON.stringify({
          speed: seg.content.speed || '0 token/s',
          completion_tokens: seg.content.final_answer_usage?.completion_tokens ?? 0
        })
        resultHtml += `\n\n<tokenusage>${tokenTagContent}</tokenusage>\n\n`
      } else {
        resultHtml += seg.content || ''
      }
    }
  }

  // 处理末尾可能遗留的思考链
  resultHtml += flushThinkingGroup()

  // 清理多余换行
  return resultHtml.replace(/\n{3,}/g, '\n\n').trim()
}

// ============================================================
// 第三部分：图像处理工具
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
// 第四部分：发送前上下文补全
// ============================================================

// 内存缓存（页面不刷新时永久有效）
const toolCallCache = new Map<string, { arguments: any; result: any }>()
// 并发请求控制：防止同一时间多个 `cleanMessages` 重复请求同一个缺失的 call_id
const pendingFetchPromises = new Map<string, Promise<any>>()

/**
 * 根据 call_id 列表从后端一次性获取完整的 arguments 和 result
 */
async function fetchToolDetails(callIds: string[]): Promise<Record<string, { arguments: any; result: any }>> {
  if (callIds.length === 0) return {}

  // 1. 剔除已经在缓存中的 ID，只获取缺失的
  const missingIds = callIds.filter(id => !toolCallCache.has(id))
  
  // 2. 构建最终返回结果（缓存中已有的直接拿）
  const finalResult: Record<string, { arguments: any; result: any }> = {}
  for (const id of callIds) {
    if (toolCallCache.has(id)) {
      finalResult[id] = toolCallCache.get(id)!
    }
  }

  // 3. 如果全部命中缓存，无需请求后端，直接返回
  if (missingIds.length === 0) {
    return finalResult
  }

  // 4. 并发去重：生成一个唯一 key（用缺失的 ID 排序后拼接），防止短时间内重复触发
  const requestKey = missingIds.sort().join(',')
  
  // 如果当前正在请求这批数据，直接复用同一个 Promise，等待它完成
  if (pendingFetchPromises.has(requestKey)) {
    await pendingFetchPromises.get(requestKey)
    // 等待完成后，重新从缓存中拿这批数据
    for (const id of missingIds) {
      if (toolCallCache.has(id)) {
        finalResult[id] = toolCallCache.get(id)!
      }
    }
    return finalResult
  }

  // 5. 发起真正的网络请求（并在 Promise 中自动管理缓存）
  const fetchPromise = (async () => {
    try {
      const resp = await fetch('/api/tool-calls/batch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ call_ids: missingIds })
      })
      const data = await resp.json()
      
      // 将后端返回的数据写入缓存
      // 兼容后端返回数组或对象
      if (Array.isArray(data)) {
        for (const item of data) {
          const idKey = item.call_id || item.id || item.callId
          if (idKey) {
            toolCallCache.set(idKey, { arguments: item.arguments, result: item.result })
            finalResult[idKey] = toolCallCache.get(idKey)!
          }
        }
      } else if (typeof data === 'object') {
        for (const [key, val] of Object.entries(data)) {
          toolCallCache.set(key, val as any)
          finalResult[key] = val as any
        }
      }
    } catch (e) {
      console.error('获取工具详情失败', e)
    } finally {
      // 无论成功或失败，都从 pending 映射中移除请求标记
      pendingFetchPromises.delete(requestKey)
    }
  })()

  // 将当前请求存入 pending 映射中
  pendingFetchPromises.set(requestKey, fetchPromise)
  
  // 等待请求完成（或者如果已经失败，跑出了异常，上层可以捕获）
  await fetchPromise

  return finalResult
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
        if (Array.isArray(parsed) && parsed.length > 0 && parsed[0].type) {
          segments = parsed
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
      const callIds = toolSegments.map((s: any) => s.content?.id).filter(Boolean)
      let toolDetails: Record<string, { arguments: any; result: any }> = {}

      try {
        if (callIds.length > 0) {
          toolDetails = await fetchToolDetails(callIds)
        }
      } catch (e) {
        console.warn('获取工具详情失败，降级为仅发文本', e)
        finalMessages.push({ role: 'assistant', content: fullText || null })
        continue
      }

      // 步骤 A：标准 OpenAI 必须的第一条 assistant 消息（带上参数）
      finalMessages.push({
        role: 'assistant',
        content: '', // 标准协议规定：有 tool_calls 时，content 可以为 null
        tool_calls: toolSegments.map((s: any) => ({
          id: s.content.id,
          type: 'function',
          function: {
            name: s.content.name,
            arguments: (() => {
              const raw = toolDetails[s.content.id]?.arguments
              return raw ? (typeof raw === 'string' ? raw : JSON.stringify(raw)) : '{}'
            })()
          }
        }))
      })

      // 步骤 B：紧跟其后的所有 role: tool 结果消息
      for (const s of toolSegments) {
        const resultRaw = toolDetails[s.content.id]?.result
        const resultContent = resultRaw ? (typeof resultRaw === 'string' ? resultRaw : JSON.stringify(resultRaw)) : ''
        finalMessages.push({
          role: 'tool',
          tool_call_id: s.content.id,
          content: resultContent
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