# URPP V0 Evaluation Plan

## Baselines

### A — Generic LLM

```text
Question -> LLM
```

### B — Course RAG

```text
Question + Course RAG -> LLM
```

### C — URPP Lite

```text
Question + Course Context + Student State -> LLM
```

### D — Full URPP

```text
Course Model
+ Learning Objective
+ Student Evidence
+ Pedagogical Policy
-> Teaching Action
```

## Metrics

- course grounding
- student-model accuracy
- confidence calibration
- state-sensitive adaptivity
- persistence across sessions
- learning gain
- transfer performance
- unsupported-inference rate
