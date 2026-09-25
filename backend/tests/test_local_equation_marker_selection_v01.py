"""14D-4B4D2C: bounded equation-marker source selection.

Synthetic material only. No Ollama, SQLite, PDF, or saved Session.
"""

import pytest

from app.services.course_knowledge.local_course_source_selector_v01 import (
    select_course_source_ids_v01,
)


def sources():
    contents = {
        4: "Volume integration and intersection volume (7).",
        5: "Height LUT equations (10), (11), (12), (13), (14).",
        6: (
            "C. Height Approximation Methods\n"
            "Regression Method (15): piecewise height.\n"
            "Distance Method (16): overlap height."
        ),
    }

    return tuple(
        {
            "source_id": f"pdf-{page}",
            "content": content,
            "source_locator": (
                f"local-pdf://synthetic.pdf?pages={page}-{page}"
            ),
        }
        for page, content in contents.items()
    )


@pytest.mark.parametrize(
    "question, expected",
    [
        ("请写出式 (15) 的完整分段公式。", ("pdf-6",)),
        ("请写出式 (16) 的完整分段公式。", ("pdf-6",)),
        ("式 (15) 和 (16) 分别是什么方法？", ("pdf-6",)),
        ("请解释公式 (15)。", ("pdf-6",)),
        ("请解释方程 (16)。", ("pdf-6",)),
        ("请解释式 (99)。", ()),
    ],
)
def test_explicit_equation_marker_selects_expected_source(
    question, expected
):
    assert select_course_source_ids_v01(
        sources=sources(),
        current_question=question,
    ) == expected


def test_explicit_equation_overrides_stale_student_history():
    previous = type(
        "StudentMessage",
        (),
        {
            "role": "student",
            "text": "请解释公式 (7)。",
        },
    )()

    assert select_course_source_ids_v01(
        sources=sources(),
        current_question="请写出式 (16)。",
        history=(previous,),
    ) == ("pdf-6",)


def test_equation_selection_does_not_modify_original_sources():
    original = sources()

    assert select_course_source_ids_v01(
        sources=original,
        current_question="式 (15) 和 (16) 分别是什么方法？",
    ) == ("pdf-6",)

    assert original == sources()
