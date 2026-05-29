# Co-Captain Git-Agent — Human Liaison to the Fleet

**The human operator's representative inside the SuperInstance fleet. Receives instructions, dispatches work, monitors progress, gates everything through human approval.**

## What This Gives You

- **Human-first state machine** — STANDBY → BRIEFED → DISPATCHING → MONITORING → REPORTING cycle
- **Intent translation** — converts natural-language instructions into fleet protocol messages
- **Task dispatching** — routes work to appropriate git-agents with priority levels
- **Fleet management** — tracks available agents, capabilities, and current assignments
- **Human gating** — nothing executes without explicit human approval
- **Progress reporting** — real-time status updates back to the human operator

## Quick Start

```bash
pip install co-captain-git-agent
```

```python
from co_captain import CoCaptain
from human_interface import HumanInterface, HumanContext

# Create a co-captain with human context
captain = CoCaptain(human=HumanContext(name="operator", role="admin"))

# Brief the co-captain with an instruction
captain.brief("Audit all fleet READMEs and push world-class rewrites")

# The co-captain translates this into fleet tasks
# STANDBY → BRIEFED → DISPATCHING → MONITORING → REPORTING

# Check status
report = captain.report()
print(f"Tasks dispatched: {report.tasks_dispatched}")
print(f"Tasks completed: {report.tasks_completed}")
print(f"Pending approval: {report.pending_approval}")
```

## API Reference

### `CoCaptain(human, fleet_manager=None)`
State machine that mediates between humans and the fleet.

| Method | Description |
|--------|-------------|
| `brief(instruction)` | Translate instruction into fleet tasks |
| `dispatch()` | Send approved tasks to fleet agents |
| `monitor()` | Check progress on dispatched tasks |
| `report()` | Generate status report for human |
| `approve(task_id)` | Gate a task for execution |
| `reject(task_id, reason)` | Block a task with explanation |

### `HumanInterface` / `HumanContext`
Captures operator identity, preferences, and approval state.

### `Dispatcher`
Routes fleet messages with `TaskPriority` (LOW, NORMAL, HIGH, URGENT).

### `FleetManager`
Tracks fleet composition, agent capabilities, and current assignments.

## How It Fits

The human-facing interface of the [SuperInstance fleet](https://github.com/SuperInstance). The Co-Captain is *not* a worker agent — it's the human's proxy.

- **[captain](https://github.com/SuperInstance/captain)** — Fleet commanding vessel (receives dispatched work)
- **[cocapn-com](https://github.com/SuperInstance/cocapn-com)** — Message routing
- **[cicd-agent](https://github.com/SuperInstance/cicd-agent)** — CI/CD pipeline (executes dispatched tasks)
- **[agent-forge](https://github.com/SuperInstance/agent-forge)** — Universal git-agent framework

## Testing

```bash
pytest tests/
```

## Installation

```bash
pip install co-captain-git-agent
```

Python 3.10+. MIT license.

## Documentation

📚 [OpenConstruct Docs](https://github.com/SuperInstance/openconstruct-docs)
