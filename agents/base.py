"""
Shared utilities used by all agents.
"""
import json
import re
import time


def run_agent_loop(client, model, system_prompt, user_prompt, tools, tool_executor, max_iterations=10):
    """
    The agentic loop every agent uses.
    Claude calls tools until it has enough info, then gives a final answer.
    Returns Claude's final text response.
    """
    messages = [{"role": "user", "content": user_prompt}]

    for _ in range(max_iterations):
        response = None
        for attempt in range(3):
            try:
                response = client.messages.create(
                    model=model,
                    max_tokens=2048,
                    system=system_prompt,
                    tools=tools,
                    messages=messages,
                )
                break
            except Exception as e:
                err = str(e).lower()
                if any(k in err for k in ("connection", "timeout", "network", "502", "503", "529")):
                    if attempt < 2:
                        time.sleep(2 ** attempt)
                        continue
                raise

        # Claude is done — extract final text
        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    return block.text
            return ""

        # Claude wants to call tools
        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    print(f"    [tool] {block.name}({json.dumps(block.input)[:80]}...)" if len(json.dumps(block.input)) > 80 else f"    [tool] {block.name}({block.input})")
                    result = tool_executor(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": str(result),
                    })
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

    return ""


def extract_json(text: str) -> dict:
    """Pull the first JSON object out of Claude's response text."""
    # Try ```json ... ``` block first
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Try bare { ... }
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return {}
