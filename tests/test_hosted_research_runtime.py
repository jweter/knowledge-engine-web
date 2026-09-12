from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_full_research_blueprint_is_operator_gated_and_complete() -> None:
    blueprint = (ROOT / "render.research.yaml").read_text(encoding="utf-8")

    # This paid deployment stays separate from the default alpha Blueprint.
    assert "intentionally NOT the default render.yaml" in blueprint

    # Web gets real durable state and the already-verified CPU model.
    assert "mountPath: /var/data" in blueprint
    assert "KE_WEB_LLM_MODEL" in blueprint
    assert "qwen2.5:1.5b" in blueprint
    assert "KE_WEB_SESSION_STORAGE_MODE" in blueprint
    assert "KE_WEB_ASYNC_RESEARCH_ENABLED" in blueprint

    # Hosted inference is a private service, never a public model endpoint.
    assert "type: pserv" in blueprint
    assert "name: knowledge-engine-ollama" in blueprint
    assert "dockerfilePath: ./Dockerfile.ollama" in blueprint
    assert "plan: 1c-2g" in blueprint
    assert "property: hostport" in blueprint


def test_private_ollama_image_is_version_pinned() -> None:
    dockerfile = (ROOT / "Dockerfile.ollama").read_text(encoding="utf-8")

    assert "FROM ollama/ollama:0.34.0" in dockerfile
    assert "ollama/ollama:latest" not in dockerfile


def test_start_scripts_preserve_model_and_private_host_wiring() -> None:
    web_start = (ROOT / "scripts/start-alpha.sh").read_text(encoding="utf-8")
    ollama_start = (ROOT / "scripts/start-ollama.sh").read_text(encoding="utf-8")

    assert "KE_WEB_OLLAMA_HOSTPORT" in web_start
    assert 'KE_WEB_OLLAMA_HOST="http://$KE_WEB_OLLAMA_HOSTPORT"' in web_start

    assert 'listen_host="${OLLAMA_HOST:-0.0.0.0:11434}"' in ollama_start
    assert 'OLLAMA_HOST="$listen_host" ollama serve &' in ollama_start
    assert '*:*) listen_port="${listen_host##*:}" ;;' in ollama_start
    assert '*) listen_port="11434" ;;' in ollama_start
    assert "OLLAMA_CLIENT_HOST:-http://127.0.0.1:$listen_port" in ollama_start
    assert 'OLLAMA_MODELS="${OLLAMA_MODELS:-/var/data/models}"' in ollama_start
    assert 'ollama show "$model"' in ollama_start
    assert 'ollama pull "$model"' in ollama_start
