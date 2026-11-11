# msg-optimizer

Hermes agent plugin：在用户消息进主 LLM 之前，用一个小模型（经
`auxiliary.msg_optimize` 路由，如 `agnes-2.5-flash`）把口语化 / 含指代 /
缺前提的输入**补全成更完整的指令**，主模型拿到的是"原话 + 优化参考"。

## 它做什么

- **指代消解**：把"那个 9200 装不上的事"补成"9200 PWA manifest 安装失败的问题"
- **错字订正**：正文笔误修为最可能原意；代码/路径/URL/数字/变量名一律不改
- **缺口标注**（`missing`）：识别"缺了会修偏方向"的关键前提（技术栈/环境/验收标准），
  不脑补、逐项写进 `missing`，注入框提示主模型可用 `clarify` 向用户追问
- **语言铁律**：优化版输出语言 = 输入语言，不翻译不混用
- **全程 fail-open**：小模型挂 / 超时 / schema 不符 → 原文照发，不阻塞主 turn

## 两个机制面（config `mode` 切换）

| mode | 机制 | 行为 |
|---|---|---|
| `augment`（默认） | `pre_llm_call` hook | 追加"优化参考/建议指令"到 user 消息尾，原话保留 |
| `replace` | `llm_request` middleware | 直接替换发出的 user 消息正文 |

`injection`（augment 下）：`soft` = 原话为准、优化版供参考；`aggressive` = 以优化版为准执行。

## 安装 / 启用

宿主插件来源（`plugins.py` 头部钉死）支持三种：本地目录 `~/.hermes/plugins/<name>/`、
项目内 `./.hermes/plugins/`（需 opt-in `HERMES_ENABLE_PROJECT_PLUGINS`）、
pip `hermes_agent.plugins` entry-point。**本仓走「本地目录」路线**——克隆到宿主
`plugins/` 目录即可，无需 pip、无需进 catalog：

```bash
git clone https://github.com/stennyc/msg-optimizer.git ~/.hermes/plugins/msg-optimizer
```

> **目录名必须 = 插件名 `msg-optimizer`**（宿主按 `plugin.yaml` 的 `name` 字段识别；
> 同名最省事，避免目录名/插件名错位）。多 profile 部署时克隆到对应 profile 的
> `plugins/` 目录。

仓是**纯插件代码**，不含 profile 运行时配置。克隆后每个要启用的 profile 需在自己的
`config.yaml` 加三段——**完整配方见 [CONFIG.md](./CONFIG.md)**（`plugins.enabled` /
`plugins.entries.msg-optimizer.settings` / `auxiliary.msg_optimize`）。改完
**重启该 profile 的 gateway**（常驻进程只在启动时加载代码 + config 快照；CLI/TUI
冷启动无需重启）。

### 让 agent 替你装（复制这段丢给任何有 terminal 的 Hermes agent）

```
任务：在 <HERMES_HOME> 部署 msg-optimizer 插件（小模型消息优化器）。请自己判断
本机 Hermes 的 gateway 入口（常驻服务 / hermes 子命令 / 系统服务）再执行，步骤：
 1. git clone https://github.com/stennyc/msg-optimizer.git <HERMES_HOME>/plugins/msg-optimizer
 2. 在目标 profile 的 config.yaml 加三处（照仓内 CONFIG.md）：
    - plugins.enabled 追加 "msg-optimizer"
    - plugins.entries.msg-optimizer.settings: {mode: augment, injection: soft}
    - auxiliary.msg_optimize: {provider, base_url, key_env, model}（配一个能跑的小模型端点）
 3. 重启该 profile 的 gateway（怎么重启你自行判断：systemd service / hermes gateway
    子命令 / 重启常驻进程，任选一种能确保它重新加载代码+config 的方式）。
 4. 验收：发一条 >=20 字模糊指代消息，grep 该 profile agent.log 两行指纹：
    - "Auxiliary msg_optimize: using ..."  <- 小模型路由对
    - "msg-optimizer augment context for turn ... (N->M chars, <injection>)"  <- 注入生效
    /opt 斜杠命令可回放最近一次决策。
 自检：重启后 grep 该 profile agent.log 应见 "msg-optimizer active in AUGMENT mode"；
      若见不到，说明 gateway 没重载成功，重做第 3 步（换个重启入口再试）。
约束：API key 只走 key_env（环境变量名），切勿写进 config 明文；克隆后不要提交
任何含 key 的文件。
```

### 进 catalog 后（未来）
`hermes plugins install msg-optimizer` 一键装（需 hermes-agent 上游 catalog PR
合并；现阶段用上面的 clone 方式，等价可用）。

## 验收

发一条 ≥ `min_len`（默认 20 字）的模糊指代消息，看该 profile `agent.log`：
- `Auxiliary msg_optimize: using custom (<model>)` ← 小模型路由正确
- `msg-optimizer augment context for turn ... (N→M chars, <injection>)` ← 注入实际发生

`/opt` 斜杠命令可回放最近一次决策（原文 / 优化版 / 原因 / 走了哪条路径）。

## 安全边界

- 注入落在**当前 turn user 消息尾部（volatile 区）**，不破坏主模型 provider 前缀缓存
- 用户输入经 `<<USER_DATA>>` 边界 + 安全铁律 隔离，视为纯数据，防提示注入
- API key 走 `key_env`（环境变量名），不落仓

## 版本

- `v1.0.0` — 首版（augment/replace + 错字订正 + missing 缺口标注 + 前缀缓存说明）

## License

MIT
