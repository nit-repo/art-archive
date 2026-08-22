"""
Shared NVIDIA NIM client used by both AI stages.

Reasoning models on this endpoint default to thinking ON and emit their
chain-of-thought into the response body. A 45-second reel brief needs
formatting discipline, not multi-step deduction, so thinking is disabled
explicitly here — the first live run spent an entire 8192-token budget
reasoning and never reached the entry.
"""

import os
import re

from openai import OpenAI

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
NVIDIA_MODEL = os.environ.get("NVIDIA_MODEL", "nvidia/nemotron-3.5-lightning-30b-a3b")

# Opt back in with ENABLE_THINKING=true if you want to test whether it
# improves citation accuracy — budget roughly 3x the tokens if you do.
ENABLE_THINKING = os.environ.get("ENABLE_THINKING", "false").strip().lower() in {"1", "true", "yes"}


def thinking_extra_body() -> dict:
    return {"chat_template_kwargs": {"enable_thinking": ENABLE_THINKING}}


def strip_reasoning(text: str) -> str:
    """
    Remove chain-of-thought that reasoning models emit inside the content field.

    Handles both explicit <think>...</think> delimiters and the unfenced
    "Here's a thinking process:" preamble, by cutting everything before the
    first Markdown H1 when one is present.
    """
    if not text:
        return ""

    cleaned = re.sub(r"<(think|thinking|reasoning)>.*?</\1>", "", text, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"<(think|thinking|reasoning)>.*\Z", "", cleaned, flags=re.DOTALL | re.IGNORECASE)

    match = re.search(r"^# .+", cleaned, flags=re.MULTILINE)
    if match:
        cleaned = cleaned[match.start():]

    return cleaned.strip()


def _extract(choice) -> tuple[str, str, bool]:
    """Returns (content, finish_reason, saw_reasoning)."""
    message = choice.message
    content = getattr(message, "content", None) or ""
    # Some NIM builds return reasoning in a sibling field rather than inline.
    reasoning = getattr(message, "reasoning_content", None) or ""
    return content, (choice.finish_reason or ""), bool(reasoning)


def complete(system_prompt: str, user_content: str, max_tokens: int, temperature: float) -> dict:
    """
    Call the model, retrying once with a doubled budget if it runs out of
    tokens. Returns a dict with content, finish_reason, tokens_used and
    whether reasoning was observed.
    """
    client = OpenAI(base_url=NVIDIA_BASE_URL, api_key=os.environ["NVIDIA_API_KEY"])

    budget = max_tokens
    last = None

    for attempt in (1, 2):
        kwargs = dict(
            model=NVIDIA_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=temperature,
            top_p=0.95,
            max_tokens=budget,
            stream=False,
        )

        try:
            completion = client.chat.completions.create(**kwargs, extra_body=thinking_extra_body())
        except Exception as exc:  # noqa: BLE001 — endpoint may reject the passthrough
            if "chat_template_kwargs" not in str(exc) and "enable_thinking" not in str(exc):
                raise
            print("  Note: endpoint rejected the thinking toggle; retrying without it.")
            completion = client.chat.completions.create(**kwargs)

        content, finish_reason, saw_reasoning = _extract(completion.choices[0])
        last = {
            "content": content,
            "finish_reason": finish_reason,
            "saw_reasoning": saw_reasoning,
            "budget": budget,
        }

        if finish_reason != "length":
            return last

        if attempt == 1:
            budget = max_tokens * 2
            print(
                f"  Hit the {max_tokens}-token limit"
                f"{' while reasoning' if saw_reasoning else ''}; retrying once at {budget}."
            )

    return last
