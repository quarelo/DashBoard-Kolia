import os
import subprocess
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "install-model.sh"


def run_installer(tmp_path, *, installed: str, answers: str):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "OLLAMA_MODEL=qwen-env:1b\nEMBEDDING_MODEL=embed-env\nKEEP=value\n",
        encoding="utf-8",
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(
        "#!/bin/sh\n"
        "for arg in \"$@\"; do last=$arg; done\n"
        "if [ \"$last\" = list ]; then printf '%s\\n' \"$FAKE_INSTALLED\"; exit 0; fi\n"
        "printf '%s\\n' \"$*\" >> \"$FAKE_DOCKER_LOG\"\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    log_file = tmp_path / "docker.log"
    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{bin_dir}:{environment['PATH']}",
            "ENV_FILE": str(env_file),
            "FAKE_INSTALLED": installed,
            "FAKE_DOCKER_LOG": str(log_file),
        }
    )
    result = subprocess.run(
        [str(SCRIPT)],
        input=answers,
        text=True,
        capture_output=True,
        env=environment,
        check=False,
    )
    log = log_file.read_text(encoding="utf-8") if log_file.exists() else ""
    return result, env_file.read_text(encoding="utf-8"), log


def test_installed_env_models_do_not_trigger_pull(tmp_path):
    result, env_content, docker_log = run_installer(
        tmp_path,
        installed="qwen-env:1b latest\nembed-env:latest latest",
        answers="",
    )

    assert result.returncode == 0
    assert "já está instalado" in result.stdout
    assert "pull" not in docker_log
    assert "OLLAMA_MODEL=qwen-env:1b" in env_content


def test_missing_env_models_can_be_downloaded(tmp_path):
    result, _env_content, docker_log = run_installer(
        tmp_path, installed="", answers="1\n1\n"
    )

    assert result.returncode == 0
    assert "ollama pull qwen-env:1b" in docker_log
    assert "ollama pull embed-env" in docker_log


def test_missing_model_can_replace_only_requested_env_key(tmp_path):
    result, env_content, _docker_log = run_installer(
        tmp_path,
        installed="embed-env latest",
        answers="2\nqwen-new:3b\n1\n",
    )

    assert result.returncode == 0
    assert "OLLAMA_MODEL=qwen-new:3b" in env_content
    assert "EMBEDDING_MODEL=embed-env" in env_content
    assert "KEEP=value" in env_content
