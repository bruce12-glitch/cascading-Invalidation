"""Fail early on an unsupported notebook runtime and record its capabilities."""
from __future__ import annotations
import json
import os
from pathlib import Path
import platform
import shutil
import sys

if sys.version_info < (3, 10):
    raise SystemExit(f"Python 3.10+ required; found {sys.version.split()[0]}")
try:
    import numpy as np
except ImportError as error:
    raise SystemExit("NumPy is required. Run: python -m pip install -e .") from error

try:
    import torch
    gpu = {
        "torch": torch.__version__,
        "cuda_available": torch.cuda.is_available(),
        "cuda_version": torch.version.cuda,
        "device_count": torch.cuda.device_count(),
        "devices": [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())],
        "memory_bytes": [torch.cuda.get_device_properties(i).total_memory for i in range(torch.cuda.device_count())],
    }
except ImportError:
    gpu = {"torch": None, "cuda_available": False, "device_count": 0, "devices": [], "memory_bytes": []}

usage = shutil.disk_usage(Path.cwd())
report = {
    "python": sys.version,
    "platform": platform.platform(),
    "numpy": np.__version__,
    "cpu_count": os.cpu_count(),
    "memory_bytes": None,
    "disk_free_bytes": usage.free,
    "gpu": gpu,
    "runtime": "kaggle" if Path("/kaggle").exists() else "colab" if "COLAB_RELEASE_TAG" in os.environ else "other",
}
try:
    report["memory_bytes"] = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
except (ValueError, OSError, AttributeError):
    pass
Path("runtime_preflight.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
if usage.free < 2 * 1024**3:
    raise SystemExit("At least 2 GiB free disk is required for a full run and result archive")
