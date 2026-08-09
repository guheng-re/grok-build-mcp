# Grok Build（构建代理）MCP（模型上下文协议）

该服务只提供 `run_grok` 工具。它会在指定 `cwd` 中启动 Grok（构建代理），并在同一工作目录中自动复用已有会话。

## 安装

当前环境已具备 Python（编程语言）与 MCP（模型上下文协议）依赖。其他环境可执行：

```powershell
python -m pip install -r requirements.txt
```

在 Codex（代码智能体）全局配置中将入口设置为 `grok_build_mcp.py` 后，重启 Codex（代码智能体）。

## 工具

`run_grok` 仅接收以下必填参数：

- `prompt`：交给 Grok（构建代理）的完整任务。
- `cwd`：目标项目的绝对工作目录。

服务按规范化后的 `cwd` 自动保存和恢复 Grok（构建代理）会话。首次任务成功完成后才保存会话编号，避免中断任务留下无效映射。调用方不需要提供会话编号或恢复参数。

每次调用会阻塞至 Grok（构建代理）结束，并返回状态、退出码、最终 JSON（数据格式）结果及两个日志路径。日志保存在 `logs`，会话映射保存在 `state/sessions.json`。
