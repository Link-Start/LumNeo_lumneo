/**
 * 判断一个路径是否代表本地文件
 * 支持：
 * - file:///C:/path/file.txt
 * - C:\path\file.txt 或 D:/path/file.txt
 * - /home/user/file.pdf (Linux/macOS 绝对路径)
 */
export function isLocalFilePath(path: string): boolean {
  if (path.startsWith('file://')) return true
  if (/^[a-zA-Z]:[\\/]/.test(path)) return true // Windows 盘符
  return false
}


export function isRunningInPyWebView(): boolean {
  // 优先检查 pywebview 对象（最准确）
  if (typeof window !== 'undefined' && (window as any).pywebview) {
    return true
  }
  // 后备检查 UA（某些旧版本可能没有 pywebview 全局对象）
  return /pywebview/i.test(navigator.userAgent)
}

// 复制文本到粘贴板
export const copyToClipboard = (text: string) => {

    if (!navigator.clipboard) {
        // 如果浏览器不支持 Clipboard API，则退回到旧的 execCommand 方法
        var tempInput = document.createElement('input')
        document.body.appendChild(tempInput)
        tempInput.value = text
        tempInput.select()
        document.execCommand('copy')
        document.body.removeChild(tempInput)
        return
    }

    // 使用现代的 Clipboard API
    navigator.clipboard.writeText(text).catch(err => {
        console.error('Could not copy text: ', err)
    })
}