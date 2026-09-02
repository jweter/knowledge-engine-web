from types import SimpleNamespace

from fastapi.testclient import TestClient

from knowledge_engine_web import main
from knowledge_engine_web.ai_orchestration import AICapability


def _configure_available_research(tmp_path, monkeypatch):
    monkeypatch.setenv("KE_WEB_DATABASE_URL", f"sqlite:///{tmp_path / 'ask.sqlite3'}")
    monkeypatch.setenv("KE_WEB_ASYNC_RESEARCH_ENABLED", "true")
    monkeypatch.setattr(
        main,
        "evaluate_ai_capability",
        lambda settings: AICapability(available=True),
    )
    monkeypatch.setattr(main, "answer_retrieval", lambda *args, **kwargs: [])


def test_plain_ask_starts_bounded_research_by_default(tmp_path, monkeypatch):
    _configure_available_research(tmp_path, monkeypatch)
    calls = []

    def submit(settings, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(question=kwargs["question"])

    monkeypatch.setattr(main, "submit_research_job", submit)
    response = TestClient(main.app).get("/ask", params={"q": "a fresh unseen question"})

    assert response.status_code == 200
    assert len(calls) == 1
    assert calls[0]["question"] == "a fresh unseen question"
    assert "Research is on by default." in response.text
    assert "Research session running" in response.text
    assert "Fast indexed search only" in response.text


def test_quick_mode_explicitly_skips_broader_research(tmp_path, monkeypatch):
    _configure_available_research(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(
        main, "submit_research_job", lambda settings, **kwargs: calls.append(kwargs)
    )
    response = TestClient(main.app).get(
        "/ask", params={"q": "a fresh unseen question", "quick": "1"}
    )

    assert response.status_code == 200
    assert calls == []
    assert "Research session running" not in response.text
    assert 'name="quick" value="1" checked' in response.text


def test_legacy_explicit_synthesize_false_remains_retrieval_only(tmp_path, monkeypatch):
    _configure_available_research(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(
        main, "submit_research_job", lambda settings, **kwargs: calls.append(kwargs)
    )
    response = TestClient(main.app).get(
        "/ask", params={"q": "a fresh unseen question", "synthesize": "false"}
    )

    assert response.status_code == 200
    assert calls == []
    assert "Research session running" not in response.text


def test_plain_ask_falls_back_honestly_when_research_is_unavailable(tmp_path, monkeypatch):
    monkeypatch.setenv("KE_WEB_DATABASE_URL", f"sqlite:///{tmp_path / 'ask.sqlite3'}")
    monkeypatch.setattr(
        main,
        "evaluate_ai_capability",
        lambda settings: AICapability(
            available=False,
            reason_code="model_not_configured",
            visitor_message="unavailable",
        ),
    )
    monkeypatch.setattr(main, "answer_retrieval", lambda *args, **kwargs: [])
    response = TestClient(main.app).get("/ask", params={"q": "a fresh unseen question"})

    assert response.status_code == 200
    assert "Broader Research is unavailable on this deployment" in response.text
    assert "Indexed retrieval results are shown below" in response.text
