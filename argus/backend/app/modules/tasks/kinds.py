"""Registered background task kinds. The worker maps each kind to a handler."""

from __future__ import annotations

from enum import StrEnum


class TaskKind(StrEnum):
    SYSTEM_PING = "system.ping"
    LLM_WARMUP = "llm.warmup"
    JOB_EXTRACT = "job.extract"
    MATCH_JOB = "match.job"
    MATCH_ALL = "match.all"


# Kinds a user may enqueue directly from the API (others are created by services).
USER_ENQUEUEABLE = frozenset({TaskKind.SYSTEM_PING, TaskKind.LLM_WARMUP, TaskKind.MATCH_ALL})

NOTIFY_CHANNEL = "argus_tasks"
