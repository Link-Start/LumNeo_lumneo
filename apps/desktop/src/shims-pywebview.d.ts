// src/shims-pywebview.d.ts
export {} // 确保它被视为模块

declare global {
  interface Window {
    pywebview: {
      api: {
        select_folder: () => Promise<string | null>
        open_with_default_app: (filePath: string) => Promise<{ success: boolean; error?: string }>
        download_file: (url: string, name: string) => Promise<{ success: boolean; path?: string; error?: string }>
        // 可以在这里加入你未来可能会用到的其他 pywebview 方法
      }
    }
  }
}