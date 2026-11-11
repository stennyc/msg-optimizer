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

仓是**纯插件代码**，不含 profile 运行时配置。克隆到宿主 `plugins/` 目录（或软链）后，
每个要启用的 profile 需在自己的 `config.yaml` 加三段——**完整配方见 [CONFIG.md](./CONFIG.md)**。

```bash
git clone https://github.com/stennyc/msg-optimizer ~/.hermes/plugins/msg-optimizer
```

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
