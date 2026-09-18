# URPP V0 Architecture

```text
REAL UNIVERSITY COURSE
        |
        v
Course Model
        |
        v
Learning Objectives
        |
        +------------------------------+
        |                              |
        v                              v
Required Student State          Current Student State
                                       |
                                  Evidence History
        |                              |
        +---------------+--------------+
                        v
                   Learning Gap
                        |
                        v
                Pedagogical Policy
                        |
                        v
                 Teaching Action
                        |
                        v
                     Student
                        |
                        v
              Formative Assessment
                        |
                        v
                  Evidence Event
                        |
                        v
                  Student Model
                        |
                        v
                 Next Best Action
```

## Rules

- Evidence history is the source of truth.
- Student state is derived from evidence.
- Unknown is a valid state.
- LLMs do not directly modify Student State.
- Learning Objectives require provenance.
- Teaching decisions must eventually be auditable.
