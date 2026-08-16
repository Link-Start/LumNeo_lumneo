@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

cd /d "%~dp0"


:: ============================================================
::  LumNeo V2 打包脚本（适配 V2 架构）
:: ============================================================


:: ---------- 可配置项 ----------
set "APP_NAME=LumNeo"
set "ENTRY=main.py"
set "SRC_DIR=src"
set "FRONTEND_DIR=frontend"
set "DEFAULT_VERSION=2.0.0"


:: ---------- 步骤1：构建前端（可选） ----------
set "BUILD_FRONTEND=0"
if exist "%FRONTEND_DIR%" (
    if exist "%FRONTEND_DIR%\package.json" (
        echo.
        choice /c YN /n /t 5 /d Y /m "是否构建前端（%FRONTEND_DIR%）？[Y/N] (5秒后默认Y): "
        if errorlevel 2 (
            echo 跳过前端构建
        ) else (
            echo 正在构建前端...
            cd "%FRONTEND_DIR%"
            call npm run build
            if errorlevel 1 (
                echo 前端构建失败
                pause
                exit /b %errorlevel%
            )
            cd "%~dp0"
            set "BUILD_FRONTEND=1"
        )
    ) else (
        echo [提示] 目录 "%FRONTEND_DIR%" 不是前端工程（缺少 package.json），跳过前端。
    )
) else (
    echo [提示] 未找到前端目录 "%FRONTEND_DIR%"，将仅打包后端（无桌面 GUI 前端）。
    echo         如需打包前端，请将前端放到该目录，或设置 FRONTEND_DIR 变量指向你的前端工程。
)


:: ---------- 步骤2：删除上次打包产生的 dist 文件夹 ----------
echo 正在清理旧的打包输出目录...

taskkill /f /im %APP_NAME%.exe >nul 2>&1

if exist "dist" (
    set "RETRY_COUNT=0"
:retry_delete
    rmdir /s /q dist >nul 2>&1
    if exist "dist" (
        set /a RETRY_COUNT+=1
        if !RETRY_COUNT! lss 3 (
            echo [提示] dist 目录正被占用，等待 2 秒后尝试第 !RETRY_COUNT! 次重试...
            timeout /t 2 /nobreak >nul
            goto :retry_delete
        ) else (
            echo ====================================================
            echo 错误：删除 dist 目录严重失败！
            echo 请检查：
            echo 1. 是否在资源管理器中打开了 dist 文件夹或里面的文件？
            echo 2. VS Code / PyCharm 等编辑器是否正在建立索引？
            echo 3. 请手动打开任务管理器，关闭所有名为 %APP_NAME%.exe 的进程。
            echo ====================================================
            pause
            exit /b 1
        )
    )
    echo 已成功删除旧的 dist 目录
) else (
    echo dist 目录不存在，无需删除
)


:: ---------- 步骤3：拼装 PyInstaller 参数并打包 ----------
echo 正在打包 Python 应用...

set "PYI_ARGS=--onedir --noconsole --copy-metadata fastmcp --paths=%SRC_DIR%"


:: 动态装载的工具模块（importlib，必须逐个显式声明）
set "PYI_ARGS=%PYI_ARGS% --hidden-import=lumneo.infrastructure.external.weather"
set "PYI_ARGS=%PYI_ARGS% --hidden-import=lumneo.runtime.tools.system.skills"
set "PYI_ARGS=%PYI_ARGS% --hidden-import=lumneo.runtime.tools.system.executor"
set "PYI_ARGS=%PYI_ARGS% --hidden-import=lumneo.runtime.tools.system.reader"
set "PYI_ARGS=%PYI_ARGS% --hidden-import=lumneo.runtime.tools.system.writer"
set "PYI_ARGS=%PYI_ARGS% --hidden-import=lumneo.runtime.tools.system.delete"
set "PYI_ARGS=%PYI_ARGS% --hidden-import=lumneo.runtime.tools.system.creator"
set "PYI_ARGS=%PYI_ARGS% --hidden-import=lumneo.runtime.tools.system.lister"
:: pywebview 在 start_gui() 内局部 import，静态分析抓不到，需显式声明
set "PYI_ARGS=%PYI_ARGS% --hidden-import=webview"


:: 图标：仅在前端目录存在时添加
if exist "%FRONTEND_DIR%\public\favicon.ico" (
    set "PYI_ARGS=!PYI_ARGS! --icon=%FRONTEND_DIR%\public\favicon.ico"
)


:: 配置文件（均相对仓库根）
:: 注意：mcp_config.json 不打包，运行时从 data_dir 读取，由部署时放置。
set "PYI_ARGS=%PYI_ARGS% --add-data=app_config.yaml;."
set "PYI_ARGS=%PYI_ARGS% --add-data=tools_config.yaml;."
set "PYI_ARGS=%PYI_ARGS% --add-data=system_prompt.md;."


:: 前端构建产物（仅当存在时）
if exist "%FRONTEND_DIR%\dist" (
    set "PYI_ARGS=%PYI_ARGS% --add-data=%FRONTEND_DIR%\dist;html"
)


:: 名称 + 入口
set "PYI_ARGS=%PYI_ARGS% --name=%APP_NAME% %ENTRY%"


pyinstaller %PYI_ARGS%
if errorlevel 1 (
    echo PyInstaller 打包失败
    pause
    exit /b %errorlevel%
)

echo 打包完成，输出目录：dist\%APP_NAME%\


:: ---------- 步骤4：生成 ZIP 压缩包 ----------
echo 正在生成 ZIP 压缩包...

set "VERSION=%DEFAULT_VERSION%"
if exist "%FRONTEND_DIR%\.env" (
    for /f "tokens=2 delims==" %%a in ('findstr /i "VITE_APP_VERSION" "%FRONTEND_DIR%\.env"') do (
        set "VERSION=%%a"
        set "VERSION=!VERSION: =!"
        set "VERSION=!VERSION:"=!"
        set "VERSION=!VERSION:'=!"
    )
)
if "%VERSION%"=="" (
    set "VERSION=%DEFAULT_VERSION%"
)
echo 版本:%VERSION%

set "ZIP_NAME=%APP_NAME%-%VERSION%.zip"
set "SOURCE_DIR=dist\%APP_NAME%"
set "DEST_ZIP=dist\%ZIP_NAME%"

echo 原文件:%SOURCE_DIR%
echo 目标文件:%DEST_ZIP%

powershell -Command "& { Compress-Archive -Path '%SOURCE_DIR%' -DestinationPath '%DEST_ZIP%' -Force }"
if errorlevel 1 (
    echo 生成压缩包失败
    pause
    exit /b %errorlevel%
)

echo 压缩包已生成：%DEST_ZIP%

pause
