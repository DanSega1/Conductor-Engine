# Conductor Engine — Architecture Diagrams

Six diagrams covering the full system across all phases. Each diagram focuses on a different layer or concern.

---

## Diagram 1 — Phase Progression

How each phase builds on the previous one and what unlocks each transition.

```mermaid
flowchart LR
    P1["Phase 1 Core Runtime ✅ complete"]
    P2["Phase 2 Workflow Layer ✅ complete"]
    P3["Phase 3 Production Hardening"]
    P4["Phase 4 Control Plane + TUI"]
    P5["Phase 5 Autonomous Operation"]
    P6["Phase 6 Guild Layer"]
    P7["Phase 7 Remote Deployment"]

    P1 -->|"adds orchestration above supervisor"| P2
    P2 -->|"harden & make async + observable"| P3
    P3 -->|"versioned API + events feed operator clients"| P4
    P3 -->|"stable event model enables self-enforcement"| P5
    P5 -->|"failures become shared knowledge"| P6
    P5 -->|"OPA + audit enables safe remote ops"| P7
    P6 -->|"guild store exposed over remote API"| P7
```

---

## Diagram 2 — Execution Layer per Phase

What gets added to the execution stack at each phase. The supervisor is the fixed centre — everything else is added above or below it.

```mermaid
flowchart TD
    subgraph P1["Phase 1 — Core Runtime ✅"]
        CLI["cond CLI"] --> SUP["TaskSupervisor"]
        SUP --> GUARD["Guardrails (input validation)"]
        GUARD --> REG["Capability Registry"]
        REG --> CAP["Capability (echo / filesystem / http / memory)"]
        CAP --> STORE["TaskStore (JSON / MemoryTaskStore)"]
        SUP --> QUEUE["InMemoryTaskQueue"]
    end

    subgraph P2["Phase 2 — Workflow Layer ✅"]
        WF_CLI["cond workflow run"] --> ORCH["WorkflowOrchestrator"]
        ORCH --> PLAN["Planner (LinearPlanner)"]
        ORCH --> WORK["Worker (PassthroughWorker)"]
        ORCH --> VAL["Validator (PassthroughValidator)"]
        WORK --> SUP
    end

    subgraph P3["Phase 3 — Production Hardening"]
        ASYNC["Async Supervisor + Orchestrator"]
        LOG["Structured Logging"]
        HEALTH["Health / Metrics HTTP"]
        PGSTORE["Pluggable Stores (Postgres / SQLite / Redis)"]
        PARALLEL["Parallel Steps + Timeouts + Rate Limits"]
        APPROVAL["Approval Flows"]
        ASYNC --> PARALLEL
        LOG --> HEALTH
    end

    P2 -->|"supervisor stays unchanged"| P3
```

---

## Diagram 3 — Data Flow Inside a Workflow

Step-by-step sequence of a `cond workflow run` call from user input to terminal output.

```mermaid
sequenceDiagram
    actor User
    participant CLI as cond workflow run
    participant ORCH as WorkflowOrchestrator
    participant PLAN as Planner
    participant WORK as Worker
    participant SUP as TaskSupervisor
    participant CAP as Capability
    participant STORE as TaskStore

    User->>CLI: workflow.yaml
    CLI->>ORCH: run(WorkflowGoal)
    ORCH->>PLAN: plan(goal, PlannerContext)
    PLAN-->>ORCH: PlanResponse(steps)

    loop for each PlanStep
        ORCH->>WORK: work(step_name, WorkerContext)
        WORK-->>ORCH: WorkerResponse(TaskSubmission)
        ORCH->>SUP: run_submission(submission)
        SUP->>CAP: validate_input → execute
        CAP-->>SUP: CapabilityResult
        SUP->>STORE: save(TaskRecord)
        SUP-->>ORCH: TaskRecord
        alt TaskRecord.status == FAILED
            ORCH-->>CLI: WorkflowResult(FAILED) ← fail-fast
        end
    end

    ORCH->>PLAN: validate(goal, ValidatorContext)
    PLAN-->>ORCH: ValidationResponse
    ORCH-->>CLI: WorkflowResult(COMPLETED / PARTIAL)
    CLI-->>User: rich panel output
```

---

## Diagram 4 — Storage Layer Evolution

How the storage layer evolves across phases. The `TaskStore` Protocol never changes — only the implementations are swapped.

```mermaid
flowchart LR
    subgraph P1["Phase 1 ✅"]
        MEM["MemoryTaskStore (dict in RAM)"]
        JSON["LocalTaskStore (JSON file)"]
        DEQUE["InMemoryTaskQueue (deque)"]
    end

    subgraph P3["Phase 3"]
        PG["PostgresTaskStore"]
        SQLITE["SQLiteTaskStore"]
        REDIS_S["RedisTaskStore"]
        REDIS_Q["RedisQueue (persistent FIFO)"]
    end

    subgraph CONTRACT["TaskStore Protocol (never changes)"]
        PROTO["save / get / list"]
    end

    MEM & JSON & PG & SQLITE & REDIS_S --> CONTRACT
    DEQUE -->|replaced by| REDIS_Q
```

---

## Diagram 5 — Security and Policy Layer

How the operator, policy, and trust model evolves from Phase 4 through Phase 7.

```mermaid
flowchart TD
    subgraph P4["Phase 4 — Control Plane + TUI"]
        API["Versioned control-plane API"]
        STREAM["Structured event stream + snapshots"]
        CLIENTS["CLI / TUI / SDK clients"]
    end

    subgraph P5["Phase 5 — Autonomous Operation"]
        OPA["OPA Policy Engine (before capability exec)"]
        AUDIT["Audit Trail (allow / deny / retry / escalate)"]
        SANDBOX["Sandboxed Execution (filesystem + network constrained)"]
        BRET["Behavioral Retry (context-aware, not blind)"]
    end

    subgraph P6["Phase 6 — Guild Layer"]
        GUILD["Guild Store (failure fingerprint → resolution hint)"]
        PEER["Peer Suggestions (check guild before attempt)"]
        ROLE["Role-Scoped Knowledge (Worker A learns from Worker B)"]
    end

    subgraph P7["Phase 7 — Remote Deployment"]
        AUTH["Auth + Authorization (OPA governs caller rights)"]
        MT["Multi-Tenant (isolated registries + stores)"]
        RUNNERS["Remote runners / CI targets"]
        DEPLOY["Deploy targets Docker / systemd / K8s"]
    end

    API --> STREAM
    STREAM --> CLIENTS
    OPA --> AUDIT
    BRET --> GUILD
    GUILD --> PEER
    PEER --> OPA
    API --> AUTH
    AUTH --> MT
    AUTH --> RUNNERS
```

---

## Diagram 6 — Component Refinement Across Phases

Which components are carried forward unchanged, which are extended, and which are replaced.

```mermaid
flowchart TD
    P1_SUP["Supervisor Phase 1"]
    P2_SUP["Supervisor Phase 2 — unchanged"]
    P3_SUP["Async Supervisor Phase 3"]
    P7_SUP["Protected Remote Supervisor Phase 7"]

    P2_ORCH["Orchestrator Phase 2 (sync, sequential)"]
    P3_ORCH["Orchestrator Phase 3 (async, parallel steps)"]

    P1_STORE["TaskStore Phase 1 (JSON / Memory)"]
    P3_STORE["TaskStore Phase 3 (Postgres / Redis)"]

    P2_GUARD["Guardrails Phase 1 (Pydantic)"]
    P5_GUARD["Policy Engine Phase 5 (OPA + audit)"]

    P1_SUP -->|"no changes"| P2_SUP
    P2_SUP -->|"add async"| P3_SUP
    P3_SUP -->|"harden remote control plane"| P7_SUP

    P2_ORCH -->|"add parallelism + timeouts"| P3_ORCH

    P1_STORE -->|"swap impl same Protocol"| P3_STORE

    P2_GUARD -->|"add OPA evaluation before exec"| P5_GUARD
```
