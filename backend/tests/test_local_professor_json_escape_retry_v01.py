"""14D-4B4D1: bounded invalid JSON backslash escape correction (synthetic only)."""
import json

import pytest

from app.llm.local_ollama_professor_gateway_v01 import (
    LocalOllamaProfessorGatewayV01,
    LocalProfessorGenerationErrorV01,
)
from app.services.course_knowledge.local_learning_workspace_v01 import (
    LocalLearningWorkspaceV01,
)

SOURCE = 'synthetic-ct-source'
PAYLOAD = {
    'contract_version': 'structured-professor-v0.1',
    'instructions': 'Synthetic source-grounded teaching task.',
    'objective': {'course_id': 'synthetic-course', 'objective_id': 'synthetic-obj',
                  'description': 'Explain a synthetic projection.'},
    'teaching_action': 'conceptual_review',
    'student_request_kind': 'request_explanation',
    'sources': [{'source_id': SOURCE, 'source_revision': 'synthetic-v1',
                 'source_locator': 'synthetic:ct',
                 'content': 'A projection is a line integral.'}],
}


def reply(raw, *, done=True, done_reason='stop'):
    return {'done': done, 'done_reason': done_reason,
            'message': {'role': 'assistant', 'content': raw}}


def valid(source_id=SOURCE):
    return json.dumps({'content': r'Equation: $\Delta x = 1$.',
                       'source_ids': [source_id], 'answer_status': 'course_grounded'})


def invalid_escape(source_id=SOURCE):
    # One literal backslash before Delta inside the JSON content string.
    # Do NOT repair raw model output with .replace() in the actual gateway.
    return ('{"content":"Equation: $' + chr(92) + 'Delta x = 1$.",'
            '"source_ids":' + json.dumps([source_id]) + ',"answer_status":"course_grounded"}')


def gateway_for(responses):
    calls=[]
    pending=iter(responses)
    def transport(request):
        calls.append(request)
        return next(pending)
    return LocalOllamaProfessorGatewayV01(transport=transport), calls


def generate(gateway):
    return gateway.generate_structured(prompt_name=gateway.PROMPT_NAME, payload=PAYLOAD)


def test_valid_json_latex_preserved_without_retry():
    gw, calls = gateway_for([reply(valid())])
    assert generate(gw)['content'] == r'Equation: $\Delta x = 1$.'
    assert len(calls) == 1


def test_invalid_escape_gets_one_corrective_request_same_course_scope():
    gw, calls = gateway_for([reply(invalid_escape()), reply(valid())])
    result = generate(gw)
    assert result['content'] == r'Equation: $\Delta x = 1$.'
    assert result['source_ids'] == [SOURCE]
    assert len(calls) == 2
    assert calls[0]['messages'][1] == calls[1]['messages'][1]
    assert calls[0]['format'] == calls[1]['format']
    assert calls[0]['options'] == calls[1]['options']
    assert 'JSON ESCAPE CORRECTION (ONE RETRY)' in calls[1]['messages'][0]['content']
    assert 'JSON ESCAPE CORRECTION (ONE RETRY)' not in calls[0]['messages'][0]['content']


def test_repeated_invalid_escape_rejected_without_third_request():
    gw, calls = gateway_for([reply(invalid_escape()), reply(invalid_escape())])
    with pytest.raises(LocalProfessorGenerationErrorV01, match='Invalid JSON'):
        generate(gw)
    assert len(calls) == 2


@pytest.mark.parametrize('bad', [
    'not-json',
    '{"content":"x","content":"duplicate","source_ids":[]}',
    '{"content":NaN,"source_ids":[]}',
])
def test_other_invalid_json_fail_closed_without_retry(bad):
    gw, calls = gateway_for([reply(bad), reply(valid())])
    with pytest.raises(LocalProfessorGenerationErrorV01):
        generate(gw)
    assert len(calls) == 1


def test_incomplete_model_response_not_retried():
    gw, calls = gateway_for([reply(invalid_escape(), done_reason='length'), reply(valid())])
    with pytest.raises(LocalProfessorGenerationErrorV01, match='did not complete normally'):
        generate(gw)
    assert len(calls) == 1


def test_corrective_transport_error_does_not_trigger_more_requests():
    calls=[]
    def transport(request):
        calls.append(request)
        if len(calls)==1:
            return reply(invalid_escape())
        raise LocalProfessorGenerationErrorV01('Synthetic transport failure.')
    gw=LocalOllamaProfessorGatewayV01(transport=transport)
    with pytest.raises(LocalProfessorGenerationErrorV01, match='Synthetic transport failure'):
        generate(gw)
    assert len(calls)==2


def setup_workspace(tmp_path, responses):
    pending=iter(responses)
    calls=[]
    def transport(request):
        calls.append(request)
        return next(pending)
    gw=LocalOllamaProfessorGatewayV01(transport=transport)
    ws=LocalLearningWorkspaceV01(data_root=tmp_path/'private', gateway_factory=lambda:gw)
    session=ws.import_document(
        filename='synthetic.md',
        content=b'# CT\nA projection is a line integral.\n',
        objective_description='Explain CT projection.',
        allow_local_teaching=True,
    ).snapshot
    return ws, session, calls


def ask(ws, session):
    return ws.explain(pack_sha256=session.pack_sha256, session_id=session.session_id,
                      question='Explain CT projection', expected_message_count=0)


def test_exhausted_retry_does_not_save_any_student_or_professor_message(tmp_path):
    ws, session, calls=setup_workspace(
        tmp_path, [reply(invalid_escape()), reply(invalid_escape())]
    )
    with pytest.raises(LocalProfessorGenerationErrorV01, match='Invalid JSON'):
        ask(ws, session)
    assert len(calls)==2
    assert ws.resume(pack_sha256=session.pack_sha256, session_id=session.session_id).messages == ()


def test_recovered_json_still_must_pass_adapter_source_validation(tmp_path):
    ws, session, calls=setup_workspace(
        tmp_path, [reply(invalid_escape()), reply(valid(source_id='fabricated-id'))]
    )
    with pytest.raises(ValueError, match='outside Course Knowledge'):
        ask(ws, session)
    assert len(calls)==2
    assert ws.resume(pack_sha256=session.pack_sha256, session_id=session.session_id).messages == ()
