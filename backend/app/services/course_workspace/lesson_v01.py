"""Topic lesson: an explanation and a worked example grounded in the topic's sources.

The lesson is generated once and cached. It is labelled generated_unverified:
citing a source does not make the explanation mathematically correct.
"""

from __future__ import annotations

from app.services.course_workspace.llm_json_v01 import CourseGenerationErrorV01

LESSON_SOURCE_CHARS_V01 = 6000

LESSON_SCHEMA_V01 = {
    "type": "object",
    "properties": {
        "explanation": {"type": "string"},
        "worked_example": {"type": "string"},
        "source_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["explanation", "worked_example", "source_ids"],
}

LESSON_SYSTEM_V01 = (
    "You are a university professor teaching one topic of a course to a student. "
    "Write in English, in Markdown. Use only the supplied course excerpts. "
    'Return JSON of the form {"explanation": ..., "worked_example": ..., '
    '"source_ids": ["S1"]}: "explanation" is a clear explanation of the topic in '
    "150-350 words, building from what the student needs first; "
    '"worked_example" is one step-by-step worked example taken from or closely '
    "based on the excerpts. "
    "Write math in LaTeX between $...$ or $$...$$ and escape every backslash in "
    "JSON as \\\\. List the excerpt IDs (S1, S2, ...) you used in 'source_ids'. "
    "If the excerpts do not support the topic, say so in the explanation."
)


def generate_lesson_v01(model, topic: dict, sources: list[dict]) -> dict:
    aliases = {f"S{index}": source["ref"] for index, source in enumerate(sources, 1)}
    excerpts = "\n\n".join(
        f"[S{index}] {source['locator_label']}:\n"
        f"{source['content'][:LESSON_SOURCE_CHARS_V01]}"
        for index, source in enumerate(sources, 1)
    )
    concepts = ", ".join(topic.get("key_concepts") or []) or "(none listed)"
    result = model.generate(
        system=LESSON_SYSTEM_V01,
        user=(
            f"Topic: {topic['title']}\nSummary: {topic['summary']}\n"
            f"Key concepts: {concepts}\n\nCourse excerpts:\n\n{excerpts}"
        ),
        schema=LESSON_SCHEMA_V01,
        max_tokens=2500,
    )
    if type(result) is not dict:
        raise CourseGenerationErrorV01("Lesson is not an object.")
    explanation = next((result[k] for k in ("explanation", "lesson", "content")
                        if type(result.get(k)) is str), None)
    example = next((result[k] for k in ("worked_example", "example")
                    if type(result.get(k)) is str), "")
    if type(explanation) is not str or len(explanation.strip()) < 40:
        raise CourseGenerationErrorV01("Lesson explanation is missing.")
    if type(example) is not str:
        example = ""
    cited = []
    for alias in next((result[k] for k in ("source_ids", "sources", "source_excerpts")
                       if type(result.get(k)) is list), []):
        ref = aliases.get(alias.strip()) if type(alias) is str else None
        if ref and ref not in cited:
            cited.append(ref)
    return {
        "explanation_markdown": explanation.strip()[:8000],
        "worked_example_markdown": example.strip()[:8000],
        "source_refs": cited or [source["ref"] for source in sources],
        "citation_status": "model_cited" if cited else "topic_sources_assumed",
        "status": "generated_unverified",
        "model": getattr(model, "model", "unknown"),
    }
