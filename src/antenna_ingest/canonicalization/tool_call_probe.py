from __future__ import annotations

from antenna_ingest.nuextract.client import build_openai_compatible_client
from antenna_ingest.nuextract.settings import load_nuextract_settings


def probe_native_tool_calling() -> None:
    settings = load_nuextract_settings()
    client = build_openai_compatible_client(
        base_url=settings.skynet_base_url,
        api_key=settings.skynet_api_key.get_secret_value(),
        timeout_seconds=settings.canonicalizer_timeout_seconds,
    )
    response = client.chat.completions.create(
        model=settings.canonicalizer_model,
        messages=[
            {
                "role": "user",
                "content": (
                    'Call the get_test_value tool with the query "native tool '
                    'calling test". Do not answer directly.'
                ),
            }
        ],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "get_test_value",
                    "description": "Return a test value for a diagnostic query.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                        },
                        "required": ["query"],
                        "additionalProperties": False,
                    },
                },
            }
        ],
        tool_choice="auto",
    )

    choice = response.choices[0]
    tool_calls = choice.message.tool_calls
    native_tool_call_returned = bool(tool_calls)

    print(f"Model: {settings.canonicalizer_model}")
    print(f"Finish reason: {choice.finish_reason}")
    print(f"Native tool call returned: {native_tool_call_returned}")
    if tool_calls:
        tool_call = tool_calls[0]
        print(f"Tool name: {tool_call.function.name}")
        print(f"Tool arguments: {tool_call.function.arguments}")
    else:
        print(choice.message)


if __name__ == "__main__":
    probe_native_tool_calling()
