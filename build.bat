@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

cd /d "%~dp0"


:: 使用 choice 命令
echo.
choice /c YN /n /t 5 /d Y /m "是否需要构建前端？[Y/N] (5秒后默认Y): "
if errorlevel 2 (
    echo 你选择了：跳过前端构建
    goto :skip_build
)
echo 你选择了：构建前端

:: 步骤1：构建前端

echo 正在构建前端...


cd frontend
call npm run build
if errorlevel 1 (
    echo 前端构建失败
    pause
    exit /b %errorlevel%
)
cd ..

:skip_build

:: 步骤2：删除上次打包产生的dist文件夹

echo 正在清理旧的打包输出目录...

taskkill /f /im LumNeo.exe >nul 2>&1

if exist "dist" (
    :: 【优化2】引入重试循环，应对编辑器或系统资源管理器的短暂锁定
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
            :: 三次重试都失败后才真正报错
            echo ====================================================
            echo 错误：删除 dist 目录严重失败！
            echo 请检查：
            echo 1. 是否在资源管理器中打开了 dist 文件夹或里面的文件？
            echo 2. VS Code / PyCharm 等编辑器是否正在建立索引？
            echo 3. 请手动打开任务管理器，关闭所有名为 LumNeo.exe 的进程。
            echo ====================================================
            pause
            exit /b 1
        )
    )
    echo 已成功删除旧的 dist 目录
) else (
    echo dist 目录不存在，无需删除
)

:: 步骤3：打包 Python 应用
echo 正在打包Python应用...

pyinstaller --onedir ^
    --noconsole ^
    --copy-metadata fastmcp ^
    --hidden-import backend.system_tools ^
    --icon="frontend/public/favicon.ico" ^
    --add-data="frontend/dist;html" ^
    --add-data="tools_config.yaml;." ^
    --add-data="system_prompt.md;." ^
    --add-data="app_config.yaml;." ^
    --name="LumNeo" ^
    main.py

if errorlevel 1 (
    echo PyInstaller 打包失败
    pause
    exit /b %errorlevel%
)

echo 打包完成，输出目录：dist\LumNeo\

:: 步骤4：生成 ZIP 压缩包

echo 正在生成ZIP压缩包...

set VERSION=
for /f "tokens=2 delims==" %%a in ('findstr /i "VITE_APP_VERSION" "frontend\.env"') do (
    set VERSION=%%a
    :: 去除可能的空格和引号
    set VERSION=!VERSION: =!
    set VERSION=!VERSION:"=!
    set VERSION=!VERSION:'=!
)
if "!VERSION!"=="" (
    echo 错误：无法从 frontend/.env 中读取 VITE_APP_VERSION 值
    pause
    exit /b 1
)

echo 版本:!VERSION!

set ZIP_NAME=LumNeo-!VERSION!.zip
set SOURCE_DIR=dist\LumNeo
set DEST_ZIP=dist\!ZIP_NAME!

echo 原文件:!SOURCE_DIR!
echo 目标文件:!DEST_ZIP!

powershell -Command "& { Compress-Archive -Path '!SOURCE_DIR!' -DestinationPath '!DEST_ZIP!' -Force }"
if errorlevel 1 (
    echo 生成压缩包失败
    pause
    exit /b %errorlevel%
)

echo 压缩包已生成：!DEST_ZIP!

pause