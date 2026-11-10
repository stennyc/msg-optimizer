"""msg-optimizer — rewrite prompt + JSON schema for the small-model optimizer pass."""

from __future__ import annotations

# System prompt for the small model. Deliberately strict: it must NOT invent
# requirements the user did not state, and it must preserve code/paths/URLs.
OPTIMIZER_SYSTEM = """你是 prompt 补全器。把用户的简短/口语化输入，改写为主模型更容易执行的完整指令。

改写规则：
- 保留用户原意，绝不添加用户没提的需求、约束或假设
- 补全：任务目标、关键约束、预期输出形式；把指代词（"它"、"那个"、"上面那个"）替换为具体所指（用提供的对话上下文消解）
- 代码、文件路径、URL、数字、变量名 原样保留，不转写
- 不改变用户输入的语言
- 若输入语义已经完整、无歧义、指代清晰（通常 >40 字且自洽），changed=false，optimized 原文返回
- 若输入是纯寒暄/确认（"好的"、"继续"、"可以"），changed=false，原文返回

输出严格 JSON：
{
  "optimized": "改写后的完整指令（changed=false 时为原文）",
  "reason": "一句话说明改了什么（changed=false 时为 '原样保留'）",
  "changed": true
}"""

OPTIMIZER_SCHEMA = {
    "type": "object",
    "properties": {
        "optimized": {
            "type": "string",
            "description": "改写后（或原文）的用户指令全文",
        },
        "reason": {
            "type": "string",
            "description": "一句话说明改了什么",
        },
        "changed": {
            "type": "boolean",
            "description": "是否实际改写了（语义完整则 false）",
        },
    },
    "required": ["optimized", "changed"],
}


def build_optimizer_user_input(user_text: str, recent_history: list[str]) -> str:
    """Assemble the user-side payload: recent turns (for anaphora resolution) + current input."""
    parts = []
    if recent_history:
        parts.append("最近对话上下文（仅供消解指代，不要复述进结果）：\n"
                     + "\n".join(f"- {line}" for line in recent_history[-4:]))
    parts.append(f"当前用户输入：\n{user_text}")
    return "\n\n".join(parts)
