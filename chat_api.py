"""
Flask Blueprint: Streaming chat endpoint (SSE) + history.

Endpoints:
POST  /api/chat/stream       -> text/event-stream (SSE)
GET   /api/chat/history/<id> -> JSON list of messages (newest first)
"""

import json
import os
from typing import Generator

from flask import Blueprint, Response, request, jsonify

from pii import scrub_text
from chat_repository import (
    create_conversation,
    get_conversation,
    add_message,
    list_messages,
)

# --- add near top of file, under imports ---
import textwrap

def _build_system_from_context(client_meta: dict | None) -> str:
    """
    Build a strict system prompt from app context so answers are grounded.
    Expected keys inside client_meta:
      - resultExplanation: dict with { placeId, name, score, contributions: {metric: weight*value, ...}, raw: {metric:value,...} }
      - resultSetSummary: optional aggregates for the whole list (avg rating, price mix, etc.)
      - filters: optional current filters
    """
    base = [
        "You are the AroundMe explainer. Answer ONLY using the provided CONTEXT.",
        "If information is missing in CONTEXT, say what is missing instead of guessing.",
        "Prefer concise bullet points; include numbers (scores, distances, ratings) when present.",
    ]
    ctx_lines = []
    if client_meta and isinstance(client_meta, dict):
        if (rx := client_meta.get("resultExplanation")):
            ctx_lines.append("SELECTED_RESULT:")
            ctx_lines.append(json.dumps(rx, ensure_ascii=False))
        if (rs := client_meta.get("resultSetSummary")):
            ctx_lines.append("RESULT_SET_SUMMARY:")
            ctx_lines.append(json.dumps(rs, ensure_ascii=False))
        if (fl := client_meta.get("filters")):
            ctx_lines.append("FILTERS:")
            ctx_lines.append(json.dumps(fl, ensure_ascii=False))

    context_block = "\n".join(ctx_lines) if ctx_lines else "NO CONTEXT PROVIDED."
    return textwrap.dedent(f"""
    { ' '.join(base) }

    ===== CONTEXT START =====
    {context_block}
    ===== CONTEXT END =====

    RULES:
    - If asked "why is X ranked #1/#2/etc", explain using the 'contributions' and 'raw' fields from SELECTED_RESULT.
    - If filters conflict with the result, call that out.
    - If user asks for cheaper/closer/better-rated, suggest how score would change based on contributions.
    - Never invent data that is not in CONTEXT.
    """).strip()


# ---- OpenAI (python SDK v1.x) ----
try:
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None  # type: ignore

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY and OpenAI else None

chat_bp = Blueprint("chat_bp", __name__, url_prefix="/api/chat")


def _ensure_conversation(conversation_id: str | None) -> str:
    if conversation_id:
        if get_conversation(conversation_id):
            return conversation_id
    # create new if missing/invalid
    return create_conversation("New conversation")


def _sse_event(event_type: str, data: dict) -> bytes:
    """Format one SSE event."""
    payload = f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
    return payload.encode("utf-8")


def _stream_openai(system_prompt: str, user_text: str) -> Generator[str, None, None]:
    """Yield token deltas from OpenAI; falls back to echo if no key/client."""
    if not client:
        # Fallback: no API key—just echo a short helpful stub.
        for chunk in ["(No API key set) ", "You wrote: ", user_text[:200]]:
            yield chunk
        return

    stream = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        stream=True,
        temperature=0.3,
    )

    for part in stream:
        delta = (part.choices[0].delta.content or "")
        if delta:
            yield delta


@chat_bp.post("/stream")
def stream_chat() -> Response:
    """
    Body: { "conversationId"?: str, "message": str }
    Returns: text/event-stream
      events: start, delta, done, error
    """
    try:
        body = request.get_json(force=True, silent=False) or {}
        cid_in = body.get("conversationId")
        raw_text = (body.get("message") or "").strip()
        if not raw_text:
            return jsonify({"error": "Empty message"}), 400

        # Create or reuse conversation
        conversation_id = _ensure_conversation(cid_in)

        # PII scrub + persist user message
        user_text = scrub_text(raw_text)
        user_msg_id = add_message(conversation_id, "user", user_text)

                # Build a system prompt grounded in the app context (if provided)
        client_meta = body.get("clientMeta") or {}
        system_prompt = _build_system_from_context(client_meta)

        def generate() -> Generator[bytes, None, None]:
            # start
            yield _sse_event("start", {"conversationId": conversation_id, "userMsgId": user_msg_id})

            assistant_text_chunks: list[str] = []
            try:
                for delta in _stream_openai(system_prompt, user_text):
                    assistant_text_chunks.append(delta)
                    yield _sse_event("delta", {"delta": delta})

                final_text = "".join(assistant_text_chunks).strip()
                assistant_msg_id = add_message(conversation_id, "assistant", final_text or "(empty)")

                yield _sse_event("done", {"assistantMsgId": assistant_msg_id})
            except Exception as e:
                yield _sse_event("error", {"message": str(e)})

        return Response(
            generate(),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # for some proxies
            },
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@chat_bp.get("/history/<conversation_id>")
def get_history(conversation_id: str):
    before = request.args.get("before")
    before_ms = int(before) if (before and before.isdigit()) else None
    msgs = list_messages(conversation_id, limit=30, before_ms=before_ms)
    next_cursor = msgs[-1]["createdAt"] if msgs else None
    return jsonify({"messages": msgs, "nextCursor": next_cursor})
