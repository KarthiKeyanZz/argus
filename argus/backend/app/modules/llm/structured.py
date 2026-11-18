"""Helpers for structured (schema-constrained) LLM output."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


def llm_schema(model: type[BaseModel]) -> dict[str, Any]:
    """JSON Schema for constrained decoding with EVERY property required.

    Pydantic marks fields that have defaults as optional, and a grammar built from an
    optional property lets the model simply leave it out - a real resume parse silently
    dropped `education` and `experience` this way. Making everything required forces
    the model to emit each key; nullable types still allow `null` when a fact is absent.
    Runs in O(size of schema).
    """
    schema = model.model_json_schema()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            props = node.get("properties")
            if isinstance(props, dict):
                node["required"] = list(props)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(schema)
    return schema
