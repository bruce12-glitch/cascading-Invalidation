"""Result files carry provenance; NaN and JSON duplicate keys are forbidden."""
import gzip
import hashlib
import json
from pathlib import Path
import platform
import sys
from .model import strict_json


def write_json(path,value):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n')


def read_json(path):return strict_json(Path(path).read_text())


def read_jsonl(path):
    opener=gzip.open if str(path).endswith('.gz') else open
    with opener(path,'rt') as f:
        for line in f:
            if line.strip():yield strict_json(line)


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def environment():
    import numpy as np
    import sqlite3
    return {'python':sys.version,'platform':platform.platform(),'machine':platform.machine(),
            'processor':platform.processor(),'numpy':np.__version__,'sqlite':sqlite3.sqlite_version,
            'clock':'time.perf_counter_ns (wall clock; not hardware performance counters)'}
