"""Download dos modelos do Hugging Face Hub com progresso em bytes.

O `snapshot_download` só informa progresso por arquivo; aqui medimos o tamanho do cache
do repositório durante o download contra o total informado pela API do Hub.
"""

import threading
from collections.abc import Callable
from pathlib import Path

ProgressFn = Callable[[int, int], None]
"""(bytes baixados, bytes totais)."""


def repo_for(engine: str, model: str) -> str:
    if engine == "mlx-whisper":
        from rtfc.stt.mlx import MLX_REPOS

        return MLX_REPOS.get(model, model)
    from faster_whisper.utils import _MODELS

    return str(_MODELS.get(model, model))


def _dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file() and not f.is_symlink())


def is_cached(repo: str) -> bool:
    from huggingface_hub import snapshot_download

    try:
        snapshot_download(repo, local_files_only=True)
    except Exception:
        return False
    return True


def download(repo: str, on_progress: ProgressFn | None = None) -> str:
    """Baixa (ou confirma no cache) o repositório. Bloqueante. Devolve o caminho local."""
    from huggingface_hub import HfApi, snapshot_download
    from huggingface_hub.constants import HF_HUB_CACHE

    if is_cached(repo):
        return str(snapshot_download(repo, local_files_only=True))

    total = 0
    try:
        info = HfApi().model_info(repo, files_metadata=True)
        total = sum(s.size or 0 for s in info.siblings or [])
    except Exception:
        pass  # sem total o progresso fica indeterminado

    repo_cache = Path(HF_HUB_CACHE) / f"models--{repo.replace('/', '--')}"
    baseline = _dir_size(repo_cache)
    done = threading.Event()

    def poll() -> None:
        while not done.wait(0.5):
            if on_progress:
                on_progress(max(0, _dir_size(repo_cache) - baseline), total)

    poller = threading.Thread(target=poll, name="model-download-progress", daemon=True)
    poller.start()
    try:
        path = snapshot_download(repo)
    finally:
        done.set()
        poller.join()
    if on_progress:
        on_progress(total or _dir_size(repo_cache), total or _dir_size(repo_cache))
    return str(path)
