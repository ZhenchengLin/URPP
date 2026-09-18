# Design 01B — State Update Engine

Status: NEXT

We need to define:

```text
EvidenceEvent[]
      ↓
State Update Engine
      ↓
ObjectiveState
```

## Questions

- How much should one independent success change state?
- How should assisted success be weighted?
- How should failure affect state?
- How should repeated failure affect state?
- How should conflicting evidence combine?
- When should state remain Unknown?
- What evidence is required for Competent?
- What evidence is required for Strong?
- How should transfer evidence be weighted?
- How should recency affect evidence?
- How should confidence accumulate?
- When should a misconception become Active?
- When should it become Improving?
- When should it become Resolved?
- How should student disputes affect confidence?
