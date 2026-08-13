# LumNeo — AI Engineering OS

![Vue 3](https://img.shields.io/badge/vue%203-%2335495e.svg?style=flat&logo=vuedotjs&logoColor=%234FC08D)
![Vite](https://img.shields.io/badge/vite-%23646CFF.svg?style=flat&logo=vite&logoColor=white)
![TypeScript](https://img.shields.io/badge/typescript-%23007ACC.svg?style=flat&logo=typescript&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.12-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat&logo=fastapi&logoColor=white)
![MCP](https://img.shields.io/badge/MCP-8B5CF6?style=flat)
![PyWebView](https://img.shields.io/badge/PyWebView-2c3e50?style=flat)
![License](https://img.shields.io/github/license/lumneo/LumNeo)
![Stars](https://img.shields.io/github/stars/lumneo/LumNeo?style=social)

> **Build AI that builds hardware.**  
> **让 AI 不只是聊天，而是真正参与工程创造。**

它从 AI Agent Runtime 开始，
逐步向 Memory OS 和 Hardware OS 演进，
探索一种具有持续记忆、身份与成长能力的 **Digital Life（数字生命）**。

LumNeo 不是又一个 AI 聊天客户端，而是在探索一种新的 AI 工作方式：


- AI 可以使用真实工具
- AI 可以执行复杂工作流
- AI 可以理解项目上下文
- AI 可以持续积累经验
- AI 可以连接现实世界设备

当前版本专注于打造：

> **一个开放、可扩展、本地优先的 AI Agent Runtime。**

未来 LumNeo 将逐步演化：

```
 Agent Runtime
      ↓
   Memory OS
      ↓
 Digital Life
      ↓
  Hardware OS
```


其中：

- Agent Runtime 让 AI 能够行动
- Memory OS 让 AI 能够记忆和积累经验
- Digital Life 探索具有持续身份、经验和成长能力的 AI 形态
- Hardware OS 让 AI 能够连接真实世界

让 AI 从一次性的助手，成长为长期协作的工程伙伴。

---

# ✨ 为什么选择 LumNeo？

## 🔌 MCP 原生架构：让 AI 连接真实世界

LumNeo 基于 Model Context Protocol（MCP）构建。

通过 MCP Server，AI Agent 可以扩展各种能力：

- 文件操作
- 数据查询
- 外部 API
- 本地工具
- 硬件设备

无需修改核心代码，即可接入新的能力。

当前版本已经支持：

- stdio
- SSE
- streamable-http

三种 MCP 传输方式。


---

## 🧩 Skill 系统：让 AI 拥有专业能力

LumNeo 支持可扩展 Skill 技能体系。

你可以将：

- Python 脚本
- 自动化流程
- 工具集合
- 专业知识

封装为 Skill。

然后：

```
拖入 Skill
      ↓
绑定 Agent
      ↓
立即使用
```

让不同 Agent 拥有不同专业能力。


---

## 👥 多角色 Agent：不同任务，不同专家

LumNeo 支持创建多个专属 Agent：

例如：

```
代码审查 Agent

硬件调试 Agent

文档编写 Agent

研究分析 Agent
```

每个角色可以拥有：

- 独立 Prompt
- 独立工具
- 独立 MCP 服务
- 独立 Skill 组合


---

## 📄 项目文件理解

LumNeo 可以直接处理你的项目文件：

支持：

- 文档解析
- 图片理解
- 文件修改
- 内容生成

AI 不再只是回答问题，而是参与实际工作。


---

## 🧠 本地优先 + 云端模型自由选择

LumNeo 支持多种模型来源：

### 本地模型

例如：

- Ollama
- LM Studio

优势：

- 数据留在本机
- 隐私更安全
- 可离线运行


### 云端模型

例如：

- OpenAI
- DeepSeek
- 其他兼容 OpenAI API 的模型

根据任务自由选择。


---

# 🔧 面向硬件开发的探索

LumNeo 的起点来自一个真实需求：

> 找不到一个既能和 AI 对话，又能直接操作硬件工具链的桌面环境。

因此 LumNeo 从第一天开始设计：

AI + 工具 + 硬件能力。

通过 MCP，LumNeo 可以连接：

- 串口
- USB
- 调试工具
- 固件烧录工具
- 自定义硬件服务


当前版本已经支持通过 MCP Server 接入硬件能力。

未来将进一步发展：

- Hardware Context
- Device Memory
- Firmware Workflow
- Hardware Debug Assistant


---

# 🗺️ 项目愿景与路线

LumNeo 的长期目标：

> 构建面向工程领域的 AI 原生操作系统，并探索具备长期记忆、持续成长能力的数字生命。

LumNeo 的演进路线：

| 阶段 | 版本 | 目标 | 状态 |
|---|---|---|---|
| Phase 1 | v1.x | Agent Runtime，让 AI 能够行动 | ✅ 当前 |
| Phase 2 | v2.x | Memory OS，让 AI 能够记忆项目经验 | 🚧 规划 |
| Phase 2+ | Digital Life | 让 AI 形成持续身份、经验积累和长期协作能力 | 🌱 探索 |
| Phase 3 | v3.x | Hardware OS，让 AI 连接真实设备 | 🔜 规划 |

---

# Phase 1 — Agent Runtime

当前版本：

✅ MCP 支持  
✅ Skill 系统  
✅ 多角色 Agent  
✅ 文件操作  
✅ 工具调用  
✅ 危险工具确认  
✅ 蓝图模式  
✅ 本地模型支持  
✅ 云端模型支持  
✅ 本地云端协作  
✅ 桌面应用体验  


---

# Phase 2 — Memory OS（未来）

目标：

让 AI 不再每次从零开始，并逐渐形成持续的数字生命基础。

包括：

- 项目上下文记忆
- 工程经验积累
- 历史问题追踪
- 决策记录
- 用户偏好理解
- 长期协作能力
- 记忆治理与演化


---

# Phase 3 — Hardware OS（未来）

目标：让 AI 参与真实硬件开发流程。

包括：

- 官方硬件接入模板
- 串口调试
- 固件管理
- 编译烧录
- 设备状态理解
- 硬件开发辅助


---

# 🏗️ 架构

```
                  LumNeo

                    |
                    |

              AI Agent Layer

                    |
                    |

        -------------------------

                MCP Runtime
                Skill System
                Tool Engine

        -------------------------

                    |

          Project Context Layer

                    |

                 Memory OS

                    |

            Digital Life Layer

                    |

             Hardware Runtime

                    |

        Physical World Interface

```


---

# 🧱 技术栈

| 层级 | 技术 |
|-|-|
| 桌面容器 | PyWebView |
| 前端 | Vue 3 + TypeScript + Vite |
| UI | Naive UI |
| 后端 | FastAPI |
| 数据 | SQLite |
| 模型接口 | OpenAI Compatible API |
| 工具协议 | MCP SDK |
| Markdown | marked + highlight.js + Mermaid |
| 打包 | PyInstaller |


---

# 📂 项目结构

```text
LumNeo/
├── app_config.yaml         # 应用配置文件
├── build.bat               # Windows 构建脚本
├── main.py                 # 应用入口（启动 FastAPI + PyWebView）
├── mcp_config.json         # MCP 服务器配置文件 (运行时自动创建)
├── requirements.txt        # Python 依赖清单
├── system_prompt.md        # 系统内置角色 Prompt 模板
├── tools_config.yaml       # 本地工具配置文件
├── backend/
│   ├── database.py         # SQLite 初始化与会话管理
│   ├── mcp_client.py       # MCP 客户端管理器（多角色工具隔离）
│   ├── routes/
│   │   ├── chat.py         # 聊天接口（流式输出、工具调用）
│   │   └── chats.py        # 对话 CRUD 接口
│   ├── services/
│   |   ├── llm_service.py  # 大模型调用服务（含工具循环与角色上下文）
│   |   └── tools.py        # 本地工具动态导入定义与执行引擎
│   └── system_tools/
|       ├── __init__.py     # 系统内置工具定义
|       └── ...             # 其他通用基础工具
├── frontend/               # Vue 3 前端
│   ├── src/
│   │   ├── components/     # ChatWindow / SettingsDrawer / Introduction
│   │   ├── stores/         # chat.ts / config.ts / profiles.ts
│   │   ├── assets/         # global.css / 主题变量
│   │   └── main.ts
│   └── package.json
```

---

# 🚀 快速开始


## 环境要求

```
Python >= 3.12

Node.js >= 18

```


## 安装后端

```bash
# 使用 conda 创建虚拟环境
conda create -n lumneo python=3.12
conda activate lumneo
pip install -r requirements.txt

# 或者使用自带的`venv`创建虚拟环境
python -m venv lumneo
lumneo\Scripts\activate # Windows
source lumneo/bin/activate  # macOS/Linux
pip install -r requirements.txt
```


## 安装前端

```bash
cd frontend

npm install
```

### 开发模式下启动应用
建议打开两个终端窗口分别运行前后端：

```bash
# 终端 1：启动前端开发服务
cd frontend && npm run dev

# 终端 2：启动后端服务
conda activate lumneo
python main.py

# 提示：如果需要启动 GUI 界面，可以使用 python main.py --gui
```

### 4. 构建可执行文件
目前支持 Windows 一键构建，其他系统请参考 PyInstaller 文档自行配置：
```bash
# Windows
build.bat
```

---

## ️⚙️ 配置 MCP 服务器

编辑根目录 `mcp_config.json` 即可为角色接入外部工具：

```json
{
  "mcpServers": {
    "assistant": {
      "command": "bash",
      "args": ["-lc", "/path/to/start.sh"]
    },
    "remote-tool": {
      "url": "http://127.0.0.1:8000/mcp"
    },
    "hardware-serial": {
      "command": "python",
      "args": ["-m", "hardware_mcp", "--port", "COM3"]
    }
  }
}
```
> 💡 **开发与打包环境的区别**：
> *   **开发模式下**：直接修改项目根目录的 `mcp_config.json` 即可生效。
> *   **打包运行 (.exe) 时**：为了符合系统规范，配置文件会自动生成并存储在系统的程序数据目录下。如果你使用的是打包后的版本，请前往以下路径修改配置：
>     *   Windows: `C:\ProgramData\.LumNeo\mcp_config.json`


>  **提示**：LumNeo 支持 `stdio`、`sse`、`streamable-http` 三种传输方式。你可以在角色设置中为不同角色绑定不同的 MCP 服务组合，打造专属工作流。

---

# 💡 给硬件开发者

如果你正在开发：

- AIoT
- 嵌入式设备
- MCU 项目
- 自动化工具

LumNeo 可以作为：

> AI 控制台 + 工具编排层

通过 MCP 将硬件能力暴露给 AI。

当前版本已经可以连接自定义硬件 MCP Server。

---

# 🤝 参与贡献

欢迎：

- Issue
- Pull Request
- Skill 分享
- MCP Server 分享
- 硬件工具扩展


特别欢迎：

- 嵌入式开发者
- AI Agent 开发者
- 自动化工具开发者


一起探索：

> AI 原生工程工作方式。


---

# 📄 License

LumNeo 使用 Apache License 2.0 开源。


Copyright © 2026 LumNeo


---

# 🌱 Vision

LumNeo 起源于一个简单想法：

> 如果 AI 不只是聊天，而是真的理解我的项目、记住我的经验，并帮助我创造真实世界的东西，会发生什么？

LumNeo 正在探索：

一种具备长期记忆、持续学习和工程协作能力的数字生命形态。


**LumNeo — Building the AI-native engineering workspace.**
