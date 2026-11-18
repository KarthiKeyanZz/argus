# 11 — Agents & tool use

## From model to agent

A plain LLM call is a function: text in → text out. An **agent** puts an LLM inside a loop where
it can **choose actions** (call tools), observe results, and continue until a goal is reached:

```
goal ──► LLM decides: "call tool X with args Y"
            │
            ▼
        program executes tool X  ──► result
            │
            ▼
        LLM sees result, decides next step ... until "done"
```

### Tool calling

Models trained for tool use (Gemma 4 lists `tools` as a capability) receive a list of tool
definitions (name, description, JSON Schema for arguments) and can respond with a structured
call such as:

```json
{"tool": "search_jobs", "arguments": {"query": "junior python", "location": "Chennai"}}
```

The **program** — never the model — executes the tool and feeds back the result.

---

## Patterns

| Pattern | Description |
|---|---|
| **Single call** | One prompt, one structured answer. Predictable, cheap. **Most of ARGUS.** |
| **Pipeline / workflow** | Fixed sequence of steps written in code; LLM used inside some steps. **ARGUS's design.** |
| **ReAct agent** | LLM alternates *reasoning* and *acting*, choosing tools freely. Flexible but less predictable. |
| **Planner–executor** | One model call plans steps, code (or another model) executes them. |
| **Multi-agent** | Several specialised LLM roles cooperating. Rarely needed; harder to debug. |

---

## Why ARGUS is a *workflow*, not a free-roaming agent

| Concern | Free agent | ARGUS workflow |
|---|---|---|
| Predictability | Can take unexpected paths | Every step is fixed code |
| Safety | A hostile web page can steer it (prompt injection → tool misuse) | LLM has **no tools**; it only returns data |
| Debuggability | Hard to reproduce | Each step logged + audited |
| Cost / latency | Many LLM calls per task | One call per step |
| Guardrails | Must be enforced by prompts (weak) | Enforced in code (strong) |

The rule from the project brief: *"Tool permissions and user approvals must be enforced in
application code, not merely requested through an LLM prompt."*

---

## Where agent-like behaviour will appear (M6 apply runner)

Filling application forms has some agent flavour: inspect a form, decide what goes in each
field, react to unexpected pages. ARGUS will keep it **bounded**:

```
code (Playwright) reads the form fields ──► LLM maps each field → one of {profile fact id,
                                            approved answer id, NEEDS_INPUT}   (constrained choice)
code validates every mapping ──► code fills fields ──► code detects CAPTCHA / OTP / errors
                                                      └──► pause + notify, never "work around"
```

The LLM advises, code decides and acts, and policies (caps, hard filters, the global pause) are
checked in code before every action.

---

## Key takeaways

1. Agent = LLM in a loop choosing tools; the program executes them.
2. More autonomy means more flexibility and more risk.
3. Prefer fixed workflows with LLM steps; enforce permissions in code.
4. Constrain the model's choices (ids from a list) instead of free-form actions.

## In ARGUS

- No tools are ever given to the model: `app/modules/llm/service.py` (pure functions)
- Task queue / workflow steps: `app/worker/handlers.py`
- Global kill switch: `POST /api/v1/system/pause`
