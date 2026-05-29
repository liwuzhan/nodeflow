---
name: nodeflow-cli-debug
description: Use when working in the NodeFlow repository and asked to inspect, debug, validate, or control the runtime, simulator, buffers, tasks, logs, dataflow health, or edge-side API tooling through the NodeFlow CLI.
metadata:
  short-description: Debug NodeFlow with its CLI
---

# NodeFlow CLI Debug

Use this skill inside `/Users/liwuzhan/Desktop/nodeflow` when diagnosing NodeFlow runtime behavior, simulator integration, buffer data, task dispatch, logs, or whether the CLI is suitable for edge-side API/debug tooling.

## Entry

Run commands from the repo root:

```bash
./nodeflow-cli <command> [subcommand] [options]
```

Prefer `--json` for every command that supports it. Both placements are valid:

```bash
./nodeflow-cli runtime status --json
./nodeflow-cli --json runtime status
```

Treat `stdout` as the machine-readable channel and `stderr` as logs/diagnostics.

## Exit Codes

- `0`: query/control succeeded, or a read command returned a normal empty state.
- `1`: command failed, target missing, timeout, or control action could not be sent.
- `2`: health check ran and found an unhealthy dataflow.

Do not classify `runtime status -> not_running`, empty `buffer list`, or empty `logs` as CLI failures by themselves.

## Standard Diagnosis

1. Check runtime:
   ```bash
   ./nodeflow-cli runtime status --json
   ```
2. Inspect buffers:
   ```bash
   ./nodeflow-cli buffer list --json
   ```
3. Check dataflow health:
   ```bash
   ./nodeflow-cli health flow --config examples/planning_simulation.yaml --json
   ```
   If JSON includes `runtime_running: false` and `reason: runtime_not_running`, treat missing buffers as an idle runtime/dataflow state first, not as graph corruption.
4. Take a one-shot monitor sample:
   ```bash
   ./nodeflow-cli monitor --config examples/planning_simulation.yaml --iterations 1 --json
   ```
5. Pull relevant logs:
   ```bash
   ./nodeflow-cli logs --node <node_id> --json --count 100
   ```
6. Inspect suspect data:
   ```bash
   ./nodeflow-cli buffer inspect <node_id.port_name> --json
   ```
7. Check node contracts:
   ```bash
   ./nodeflow-cli node info <package> --json
   ```

## Runtime Control

Use runtime control only when the user wants to run or validate the system:

```bash
./nodeflow-cli runtime start examples/planning_simulation.yaml --background --json
./nodeflow-cli runtime start-dataflow --json
./nodeflow-cli runtime stop-dataflow --json
./nodeflow-cli runtime restart-dataflow --json
./nodeflow-cli runtime stop --json
```

`start-dataflow`, `stop-dataflow`, and `restart-dataflow` require a running runtime. If runtime is not running, they should return `status: not_running` and exit `1`.

## Simulator

Refresh field:

```bash
./nodeflow-cli simulator refresh --json
```

If no simulator is listening on `localhost:5555`, expect `status: timeout` and exit `1` within about two seconds. That means the CLI behaved correctly.

## Task Debugging

```bash
./nodeflow-cli task list --json
./nodeflow-cli task show <task_id> --json
./nodeflow-cli task run <task.yaml> --json
./nodeflow-cli task cancel <task_id> --json
```

`task run` must not be considered dispatched unless JSON status is `dispatched`. `control_unavailable` means runtime is missing or the control buffer has no live receiver.

## Cleanup

After starting runtime or simulator-related processes, verify cleanup before finishing:

```bash
./nodeflow-cli runtime status --json || true
lsof -nP -iTCP:5555 -sTCP:LISTEN || true
lsof -nP -iTCP:8080 -sTCP:LISTEN || true
ps -ef | rg 'runtime.main|simulator/server.py|nodeflow-cli simulator refresh' || true
```

If runtime was started during the task:

```bash
./nodeflow-cli runtime stop --json
```

## References

For detailed command semantics, read only as needed:

- `/Users/liwuzhan/Desktop/nodeflow/tools/cli/doc/AI_CLI_USAGE_GUIDE.md`
- `/Users/liwuzhan/Desktop/nodeflow/tools/cli/doc/LM_DEBUG_REFERENCE.md`
