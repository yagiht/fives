"""
brain.py - connects the language model (Lesson 1) to the tools (Lesson 2).

The whole trick is one loop:
  1. send the conversation to the model
  2. if it asks for tools, run them and add the results to the conversation
  3. repeat until it answers in plain words
"""

import ollama

import config
from tools import TOOLS

# Look tools up by name: {"open_app": open_app, ...}
TOOLS_BY_NAME = {fn.__name__: fn for fn in TOOLS}


def new_conversation() -> list:
    """Start a fresh conversation that begins with FIVES's personality."""
    return [{"role": "system", "content": config.PERSONALITY}]


def run_tool(name: str, args: dict) -> str:
    """Run one tool the model asked for, and never crash FIVES doing it."""
    fn = TOOLS_BY_NAME.get(name)
    if fn is None:
        return f"There is no tool called {name}."
    try:
        return str(fn(**args))
    except Exception as error:
        return f"The tool {name} failed: {error}"


def think(messages: list, user_text: str, on_tool=None) -> str:
    """Handle one request. Adds everything to `messages` and returns the reply."""
    messages.append({"role": "user", "content": user_text})

    for _ in range(config.MAX_TOOL_ROUNDS):
        response = ollama.chat(
            model=config.MODEL,
            messages=messages,
            tools=TOOLS,
            think=config.THINK,
            options={"num_ctx": config.CONTEXT_TOKENS, "temperature": config.TEMPERATURE},
            keep_alive=config.KEEP_ALIVE,
        )
        messages.append(response.message)

        calls = response.message.tool_calls
        if not calls:                      # plain answer -> we're done
            return response.message.content

        for call in calls:                 # run every tool it asked for
            name = call.function.name
            args = call.function.arguments or {}
            result = run_tool(name, args)
            if on_tool:
                on_tool(name, args, result)
            messages.append({"role": "tool", "tool_name": name, "content": result})

    return "I hit my limit of tool calls for one request, so I stopped."
