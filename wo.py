import time
import uuid
from typing import AsyncGenerator
import logging
import collections
import json
import features
import defines
import rnet

logger = logging.getLogger(__name__)

CLIENTS: dict[str, rnet.Client] = {}
CLIENTS_POLL: int = -1

def create_client(key: str) -> rnet.Client:
    return rnet.Client(
        impersonate=rnet.Impersonate.SafariIos18_1_1,
        impersonate_os=rnet.ImpersonateOS.IOS,
        default_headers={
            "x-yp-access-token": key,
            "x-yp-client-id": "1001000035",
            "accept": "text/event-stream",
            "referer": "https://panservice.mail.wo.cn/h5/wocloud_ai/?modelType=1",
        },
    )

def setup():
    for key in defines.API_KEYS:
        if k := key.strip():
            CLIENTS[k] = create_client(k)

    if not CLIENTS:
        logger.info("No API keys available")
    else:
        logger.info(f"Using API keys: {len(CLIENTS)}")


def next_client() -> rnet.Client:
    if not CLIENTS:
        logger.error("No API keys available")
        return rnet.Client(impersonate=rnet.Impersonate.SafariIos18_1_1, impersonate_os=rnet.ImpersonateOS.IOS)

    global CLIENTS_POLL
    CLIENTS_POLL += 1
    clients = list(CLIENTS.values())
    return clients[CLIENTS_POLL % len(clients)]


async def format_messages(
    messages: list[dict], role_info: features.RoleInfo
) -> str:
    processed = collections.defaultdict(str)
    for i, msg in enumerate(messages):
        contents = []
        if isinstance(msg["content"], list):
            for cont in msg["content"]:
                if isinstance(cont, str):
                    contents.append(cont)
        else:
            contents.append(msg["content"])

        for cont in contents:
            if "<|removeRole|>" in cont:
                cont = cont.replace("<|removeRole|>\n", "").replace(
                    "<|removeRole|>", ""
                )
            else:
                role: str = msg.get("role", "")
                role = getattr(role_info, role.lower(), role_info.system)
                cont = f"\b{role}: {cont}"

            processed[i] += cont + "\n"
        
        processed[i] = processed[i].strip()
    
    processed = [processed[i] for i in sorted(processed.keys())]

    return "\n\n".join(processed)


async def send_message(
    messages: list[dict], api_key: str, model: str
) -> AsyncGenerator[dict, None]:
    client = (
        CLIENTS.get(api_key, create_client(api_key))
        if api_key
        else next_client()
    )

    assert client, f"Client not found for {api_key}"

    feat = features.process_features(messages)
    prompt = await format_messages(messages, feat.ROLE)
    request_id = f"chatcmpl-{uuid.uuid4()}"
    error_message = ""

    print(f"Prompt({len(prompt)}): \n{prompt}")
    print("---")
    print(f"Response({request_id}):")

    data = {
        "modelId": 1,
        "input": prompt,
        "history": [],
    }

    try:
        async with await client.post(defines.QUERY_URL, json=data) as response:
            assert isinstance(response, rnet.Response)
            assert response.status_code.is_success(), f"Unexpected status code: {response.status_code.as_int()}"

            is_reasoning = False
            async with response.stream() as streamer:
                assert isinstance(streamer, rnet.Streamer)
                async for chunk in streamer:
                    assert isinstance(chunk, bytes)

                    # 顺序：data:、{...}、\n\n
                    chunk = chunk.strip()
                    if chunk.startswith(b"data:"):
                        chunk = chunk.removeprefix(b"data:")
                    if not chunk:
                        continue

                    content = ""
                    data : dict[str, str | int | None] = json.loads(chunk)
                    if data["reasoningContent"]:
                        if not is_reasoning:
                            is_reasoning = True
                            content += "<thinking>\n"
                        content += data["reasoningContent"]
                    elif is_reasoning:
                            is_reasoning = False
                            content += "\n</thinking>\n"
                    if data["response"]:
                        content += data["response"]
                    
                    yield {
                        "id": request_id,
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": model,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {
                                    "content": content,
                                },
                            }
                        ],
                    }

                    print(content, end="")
    except (AssertionError, ConnectionError) as e:
        error_message = str(e)
        logger.error(f"Error: {e}", exc_info=True)

    # just a \n
    print("")

    if error_message:
        print(f"ERROR: {error_message}")
        yield {
            "id": request_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "content": f"ERROR: {error_message}",
                    },
                    "finish_reason": "error",
                }
            ],
        }
    else:
        yield {
            "id": request_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "content": "",
                    },
                    "finish_reason": "stop",
                }
            ],
        }


async def send_message_sync(
    messages: list[dict], api_key: str, model: str
) -> dict:
    content = ""
    error_message = ""
    async for message in send_message(messages, api_key, model):
        content += message["choices"][0]["delta"]["content"]
        if message["choices"][0].get("finish_reason", None) == "error":
            error_message = message["choices"][0]["delta"]["content"]

    if error_message:
        return {
            "id": message["id"],
            "object": "chat.completion",
            "created": message["created"],
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": error_message,
                    },
                    "finish_reason": "error",
                }
            ],
        }

    return {
        "id": message["id"],
        "object": "chat.completion",
        "created": message["created"],
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": None,
    }


setup()
