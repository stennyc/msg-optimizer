# 启用 msg-optimizer：各 profile 需要的 config 配置

本仓是**纯插件代码**，不含 profile 级运行时配置。克隆到 `~/.hermes/plugins/msg-optimizer`
（或经宿主插件机制指向本仓）后，**每个要启用的 profile** 还需在自己的
`config.yaml` 加三段（缺一即该 profile 不生效）：

## 1. 启用插件开关
```yaml
plugins:
  enabled:
    - msg-optimizer
```

## 2. 插件行为档位（`plugins.entries.msg-optimizer.settings`）
```yaml
plugins:
  entries:
    msg-optimizer:
      settings:
        mode: augment        # off | augment | replace（默认 augment）
        injection: soft      # augment only: soft(原话为准) | aggressive(以优化版为准)
        platforms: []        # 空=全平台；否则只列出的 surface（如 [cli, desktop]）
        min_len: 20          # 规则前置门控：低于此长度不调小模型
```

## 3. 小模型路由槽（`auxiliary.msg_optimize`）
```yaml
auxiliary:
  msg_optimize:
    provider: custom                  # 或 "auto" 继承主模型
    base_url: https://<你的端点>/v1
    key_env: <存 API key 的环境变量名>  # 走 env，不落明文
    model: <你的小模型名>
```

## 生效方式
- 改 config 后**重启一次该 profile 的 gateway**（常驻进程只在启动时加载一次代码 + config 快照）。
- CLI/TUI 每次冷启动自然读到新值，无需重启。

## 验收
- 发一条 ≥`min_len` 字的模糊指代消息，看该 profile 的 `agent.log`：
  - `Auxiliary msg_optimize: using custom (<model>)`  ← 小模型路由正确
  - `msg-optimizer augment context for turn ... (N→M chars, <injection>)`  ← 注入实际发生
- `/opt` 斜杠命令可回放最近一次决策（原文 / 优化版 / 原因 / 走了哪条路径）。

## 行为特性
- 小模型只补"表达"（指代消解、错字订正、结构补全、缺口标注 `missing`），
  **不脑补用户没说的需求**；识别到"缺了会修偏方向的关键前提"时写进 `missing`，
  注入框提示主模型可用 `clarify` 向用户追问。
- 全程 fail-open：小模型挂 / 超时 / schema 不符 → 原文照发，不阻塞主 turn。
- 注入落在**当前 turn user 消息尾部（volatile 区）**，不破坏主模型 provider 前缀缓存。
