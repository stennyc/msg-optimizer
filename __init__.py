"""msg-optimizer plugin — small-LLM rewrite of the user's live input before the main model sees it.

Mechanism: ``llm_request`` middleware (behavior-changing, official plugin surface).
Per user turn, on the FIRST provider call (``api_call_count == 1``), the current
user message is sent through a small model (auxiliary task ``msg_optimize``) and,
if the small model judged it worth changing, the provider request's user message
is replaced with the optimized text. Tool-loop follow-up calls of the same turn
are never re-rewritten (turn_id dedup + api_call_count gate).

Fail-open everywhere: optimizer error / timeout / schema miss / short message →
the original request passes through untouched. The main turn is never blocked or
aborted by this plugin.

Config (config.yaml):
  auxiliary.msg_optimize:            # the small model
    provider: custom                # or "auto" to inherit main
    base_url: https://.../v1
    api_key: ...
    model: qwen2.5:3b
    timeout: 15
  plugins.entries.msg-optimizer.settings:
    min_len: 20                     # skip optimization below this length
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any, Optional

logger = logging.getLogger(__name__)

# --- per-process turn dedup ---------------------------------------------------
_TURN_LOCK = threading.Lock()
_SEEN_TURNS: set[str] = set()
_CACHE: dict[str, str] = {}          # turn_id -> optimized text (for /opt replay)
_MAX_CACHE = 512


def _turn_first_call(turn_id: str) -> bool:
    """True exactly once per turn_id (thread-safe)."""
    with _TURN_LOCK:
        if turn_id in _SEEN_TURNS:
            return False
        _SEEN_TURNS.add(turn_id)
        if len(_SEEN_TURNS) > _MAX_CACHE:
            for _ in range(_MAX_CACHE // 4):
                _SEEN_TURNS.pop()
        return True


def _cache_put(turn_id: str, original: str, optimized: str, reason: str) -> None:
    with _TURN_LOCK:
        _CACHE[turn_id] = json.dumps(
            {"original": original, "optimized": optimized, "reason": reason},
            ensure_ascii=False)
        if len(_CACHE) > _MAX_CACHE:
            for _ in range(_MAX_CACHE // 4):
                _CACHE.pop(next(iter(_CACHE)), None)


_OPTIMIZE_SYSTEM = """你是 prompt 补全器。把用户的简短/口语化输入，改写成模型更容易执行的完整指令。
规则：
- 保留用户原意，不添加用户没提的需求
- 补全：任务目标、关键约束、预期输出形式、必要的上下文指代（把"它"换成具体所指）
- 不改变语言；代码/路径/URL/数字 原样保留
- 输入 <20 字且语义完整 → 原样返回
只输出 JSON，不要解释。"""

_OPTIMIZE_SCHEMA = {
    "type": "object",
    "properties": {
        "optimized": {"type": "string", "description": "改写后的完整指令"},
        "reason": {"type": "string", "description": "一句话说明改了什么", "maxLength": 120},
        "changed": {"type": "boolean", "description": "是否实际改写了"},
    },
    "required": ["optimized", "changed"],
}


def _last_user_message(messages: Any) -> Optional[int]:
    """Index of the last user-role message (the live input), or None."""
    if not isinstance(messages, list):
        return None
    for i in range(len(messages) - 1, -1, -1):
        m = messages[i]
        if isinstance(m, dict) and m.get("role") == "user":
            return i
    return None


def _msg_text(content: Any) -> Optional[str]:
    """Plain-text content of a message (str or block list), None if not text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [b.get("text", "") for b in content
                 if isinstance(b, dict) and b.get("type") == "text" and b.get("text")]
        return "\n".join(parts) if parts else None
    return None


def _recent_context(messages: Any, up_to_idx: int, limit: int = 3) -> str:
    """Last few turns for anaphora resolution (the biggest quality lever)."""
    lines: list[str] = []
    for m in messages[max(0, up_to_idx - limit * 2 - 1):up_to_idx]:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        text = _msg_text(m.get("content"))
        if role in ("user", "assistant") and text:
            lines.append(f"{role}: {text[:300]}")
    return "\n".join(lines[-limit * 2:])


def register(ctx):
    """Wire the middleware + aux task + /opt verification command."""
    # Small-model slot: routed via auxiliary.msg_optimize in config.yaml.
    ctx.register_auxiliary_task(
        "msg_optimize",
        display_name="Message Optimizer (small model)",
        description="Rewrite terse user input into a complete, unambiguous instruction",
    )

    def _optimize_request(**kwargs: Any) -> Optional[dict[str, Any]]:
        # Gate 1: only the first provider call of a turn rewrites; tool-loop
        # follow-ups (api_call_count > 1) carry tool results, not fresh input.
        if kwargs.get("api_call_count", 0) != 1:
            return None
        turn_id = str(kwargs.get("turn_id") or "")
        if not turn_id:
            return None
        if not _turn_first_call(turn_id):
            return None  # already handled this turn

        request = kwargs.get("request")
        if not isinstance(request, dict):
            return None
        messages = request.get("messages")
        idx = _last_user_message(messages)
        if idx is None:
            return None
        original = _msg_text(messages[idx].get("content"))
        if original is None:
            return None  # multimodal / structured content — don't touch

        min_len = int(ctx.get_config("min_len", default=20) or 20)
        if len(original.strip()) < min_len:
            return None  # too short to need optimizing; skip the small call

        ctx_text = _recent_context(messages, idx)
        user_payload = (
            f"对话上下文（仅供消解指代，不要复述）：\n{ctx_text}\n\n"
            f"当前用户输入：\n{original}"
        ) if ctx_text else f"当前用户输入：\n{original}"

        # Gate 2: optimizer call — any exception = fail-open, original passes.
        try:
            result = ctx.llm.complete_structured(
                instructions=_OPTIMIZE_SYSTEM,
                input=[{"type": "text", "text": user_payload}],
                json_schema=_OPTIMIZE_SCHEMA,
                json_mode=True,
                task="msg_optimize",
                temperature=0.1,
                max_tokens=512,
                purpose="msg-optimizer",
            )
        except Exception as exc:
            logger.warning("msg-optimizer fail-open (turn %s): %s", turn_id, exc)
            return None

        parsed = result.parsed
        if not isinstance(parsed, dict) or not parsed.get("changed"):
            return None  # small model judged input already complete
        optimized = str(parsed.get("optimized") or "").strip()
        if not optimized or optimized == original:
            return None

        new_messages = list(messages)
        new_messages[idx] = {**messages[idx], "content": optimized}
        new_request = {**request, "messages": new_messages}
        _cache_put(turn_id, original, optimized, str(parsed.get("reason", "")))
        logger.info("msg-optimizer rewrote user input for turn %s (%d→%d chars)",
                    turn_id, len(original), len(optimized))
        return {"request": new_request,
                "source": "msg-optimizer",
                "reason": "optimized user input via msg_optimize"}

    ctx.register_middleware("llm_request", _optimize_request)
    ctx.register_command("opt", _opt_command,
                         description="Show the last msg-optimizer rewrite (original vs optimized)")
    logger.info("msg-optimizer plugin registered (aux task: msg_optimize)")


def _opt_command(raw_args: str) -> str:
    with _TURN_LOCK:
        if not _CACHE:
            return "msg-optimizer: no rewrite recorded this process yet."
        last = next(reversed(_CACHE))
        return f"last turn: {last}\n{json.dumps(json.loads(_CACHE[last]), ensure_ascii=False, indent=2)}"
