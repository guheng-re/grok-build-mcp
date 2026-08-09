# Grok Build（构建代理）MCP（模型上下文协议）

该服务只提供 `run_grok` 工具。它会在指定 `cwd` 中启动 Grok（构建代理），并在同一工作目录中自动复用已有会话。

## 安装

当前环境已具备 Python（编程语言）与 MCP（模型上下文协议）依赖。其他环境可执行：

```powershell
python -m pip install -r requirements.txt
```

还需要通过 NPM（包管理器）安装 Grok Build（构建代理）命令行工具：

```powershell
npm install -g @xai-official/grok
grok --version
```

服务不会使用用户目录中的固定路径。Windows（微软操作系统）会运行 `npm prefix -g` 得到全局安装目录，并调用其中的 `grok.cmd`；macOS（苹果操作系统）与 Linux（开源操作系统）直接调用 `grok`。若命令行工具位于自定义位置，可通过 `GROK_COMMAND` 环境变量指定可执行文件的完整路径。

在 Codex（代码智能体）全局配置中将入口设置为 `grok_build_mcp.py` 后，重启 Codex（代码智能体）。

## Codex（代码智能体）配置

在 `~/.codex/config.toml` 中添加：

```toml
[mcp_servers.grok_build]
command = "python"
args = ["/absolute/path/to/grok_build_mcp.py"]
startup_timeout_sec = 30
tool_timeout_sec = 21600
enabled_tools = ["run_grok"]
default_tools_approval_mode = "auto"

[mcp_servers.grok_build.env]
# 仅当 Grok（构建代理）命令不在标准 NPM（包管理器）目录时设置。
GROK_COMMAND = "/custom/path/to/grok"
```

Windows（微软操作系统）示例中的 Python（编程语言）入口可写为 `D:\\Python\\python.exe`，脚本路径使用双反斜杠；若不设置 `GROK_COMMAND`，请保持 `npm` 可执行并完成上述全局安装。

## 工具

`run_grok` 仅接收以下必填参数：

- `prompt`：交给 Grok（构建代理）的完整任务。
- `cwd`：目标项目的绝对工作目录。

服务按规范化后的 `cwd` 自动保存和恢复 Grok（构建代理）会话。首次任务成功完成后才保存会话编号，避免中断任务留下无效映射。调用方不需要提供会话编号或恢复参数。

每次调用会阻塞至 Grok（构建代理）结束，并返回状态、退出码、最终 JSON（数据格式）结果及两个日志路径。日志保存在 `logs`，会话映射保存在 `state/sessions.json`。
