"""Download the pinned official Apple Silicon model; never upload data."""
from pathlib import Path
from huggingface_hub import snapshot_download

if __name__=='__main__':
    snapshot_download('LiquidAI/LFM2.5-2.6B-MLX',
        revision='b41f2b65685e95418f1ac809bb022d4f79e1ab27',
        allow_patterns=['4bit/*','LICENSE','README.md'],
        local_dir=Path(__file__).resolve().parent/'models/LFM2.5-2.6B-MLX')
