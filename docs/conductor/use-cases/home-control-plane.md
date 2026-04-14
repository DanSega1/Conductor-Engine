# Use Case — Home AI Control Plane

**Reference implementation:** [DanSega1/home-ai-control-plane](https://github.com/DanSega1/home-ai-control-plane)

A policy-governed, multi-agent AI control plane running on a Raspberry Pi 5. Manages personal digital workflows, home-lab services, and smart-home integrations — with OPA-enforced approvals, budget limits, and a skill-based execution model.

This is the system that motivated Conductor Engine. It is the proving ground for engine features before they become core primitives.

---

## What the App Does

| Layer | What it does |
|---|---|
| **Supervisor** | Task state machine, OPA enforcement, approval gating, MongoDB persistence |
| **Planner** | Converts a natural-language goal into a structured execution plan via LiteLLM |
| **Skill Runner** | Executes each plan step: loads a SKILL.md, connects to an MCP server, runs an LLM tool-call loop |
| **Notion Sync** | Mirrors task state to a Notion Kanban board for human approval |
| **OPA** | Policy engine — enforces valid state transitions, per-task budget limits, and skill permissions |

A user says: *"Save this URL to my research bookmarks."* The system plans it, optionally gates it behind human approval, executes it via the Raindrop.io MCP skill, and records everything in MongoDB.

---

## How Engine Concepts Map to the App

| App concept | Engine concept | How they align |
|---|---|---|
| `Task` (MongoDB document) | `TaskRecord` | Same role — persisted task state with full history |
| `skills/registry.yaml` | `config/conductor.capabilities.yaml` | Same pattern — YAML-driven registry of execution units |
| `Skill` (SKILL.md + MCP server) | `Capability` (Python class) | Conceptually identical; execution backend differs (MCP vs. direct) |
| `Planner` microservice | `PlannerInterface` | The app's planner is an external `PlannerInterface` implementation over HTTP |
| `ExecutionPlan` / `ExecutionStep` | `PlanResponse` / `PlanStep` | Same structure — ordered steps with capability + input hint |
| `skill-runner` execution loop | `WorkflowOrchestrator` + `WorkerInterface` | The orchestrator coordinates; skill runner is the worker |
| OPA `authorize()` call | `PolicyEngine` interface (Phase 3) | App calls OPA directly; engine will expose a generic hook |
| Notion approval gate | Approval flow (Phase 3) | App's `AWAITING_APPROVAL` state maps to engine's planned suspension model |
| Motor + MongoDB | `TaskStore` Protocol | MongoDB is a backend implementation behind the same contract |
| `audit_trail: list[AuditEntry]` | `TaskRecord` history (planned) | Every transition will be recorded on the task record |

---

## Task State Machine

The app extends the engine with domain-specific planning states, but the approval and policy states now exist in the engine itself:

```
Engine today:     PENDING → AWAITING_APPROVAL → APPROVED → RUNNING → COMPLETED / FAILED
                      \            ↘ CANCELLED
                       ↘ POLICY_DENIED

App today:        PENDING → PLANNING → AWAITING_APPROVAL → APPROVED
                                      ↘ REJECTED          ↓
                                                    POLICY_DENIED
                                                          ↓
                                                      EXECUTING → COMPLETED / FAILED / CANCELLED
```

The additional engine states (`AWAITING_APPROVAL`, `APPROVED`, `POLICY_DENIED`, `CANCELLED`) landed during Phase 3.

---

## What the App Validates About Engine Design

### Architecture choices that are confirmed correct

- **`TaskStore` as a Protocol** — MongoDB drops behind it with no engine changes. The abstraction is right.
- **`CapabilityRegistry` + YAML loading** — the app's skill registry follows the identical pattern. Skills become capability plugins.
- **`PlannerInterface`** — the app's planner microservice is exactly a `PlannerInterface` over HTTP. The contract is right.
- **Supervisor as the single execution source of truth** — the app's supervisor is the same concept, just HTTP-exposed and async.
- **LLM is optional in the engine** — the app adds LiteLLM as a planner; the engine doesn't need to know about it.

### Gaps that the app exposes in the engine

| Gap | Priority | When |
|---|---|---|
| `TaskStatus` needs `AWAITING_APPROVAL`, `APPROVED`, `POLICY_DENIED`, `CANCELLED` | High | Landed in Phase 3 |
| `audit_trail: list[AuditEntry]` on `TaskRecord` — full transition history | High | Landed in Phase 3 |
| `PolicyEngine` interface — `authorize(action, context) → PolicyDecision` | High | Landed in Phase 3 |
| Approval flow — suspension model for `AWAITING_APPROVAL` state | Medium | Landed in Phase 3 |
| `MCPCapability` — wraps any MCP server as a Capability | Medium | Phase 3 seam landed in core; transport stays in `conductor-mcp` |
| MongoDB `TaskStore` adapter | Medium | Phase 3 optional extra (`conductor-engine[mongo]`) |
| Budget / cost tracking on `TaskRecord` | Low | Phase 5 |

---

## What Stays in the App vs. What Moves to the Engine

**Stays in the app (domain-specific):**
- LiteLLM planner (model routing, prompt construction)
- SKILL.md loader from GitHub/skillstore
- MCP SSE connection management
- Notion Kanban sync
- OPA Rego policy files (business rules)
- Budget thresholds and approval tier configuration
- Home-lab and smart-home integrations

**Moves to the engine over time:**
- `PolicyEngine` interface and `OPAPolicyEngine` as `conductor-opa`
- `MCPCapability` base class as `conductor-mcp`
- `ApprovalFlow` suspension/resume model
- Extended `TaskStatus` states
- `audit_trail` on `TaskRecord`
- MongoDB `TaskStore` as `conductor-engine[mongo]`

---

## Running the App

See the [home-ai-control-plane README](https://github.com/DanSega1/home-ai-control-plane) for full setup instructions.

The app runs as a 7-container Docker Compose stack on a single host:

```bash
git clone https://github.com/DanSega1/home-ai-control-plane
cd home-ai-control-plane
cp config/.env.supervisor.example config/.env.supervisor
# fill in OPA URL, MongoDB URI, LiteLLM key
docker compose up
```

The supervisor is available at `:8000`, planner at `:8001`, skill runner at `:8002`.
