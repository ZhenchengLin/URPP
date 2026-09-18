# URPP Prompt Contracts

Planned prompt families:

```text
course_analysis_v*.md
objective_extraction_v*.md
evidence_extraction_v*.md
teaching_planner_v*.md
teacher_response_v*.md
assessment_generator_v*.md
advisor_v*.md
```

Rules:

1. Prefer schema-constrained output.
2. Prompt versions belong in evaluation logs.
3. Validate LLM output.
4. LLM output never directly overwrites Student State.
