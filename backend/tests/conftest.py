'''
Test fixtures for the cantina backend.

Critical ordering: we point CANTINA_DATA_DIR at a throwaway directory BEFORE
importing the app, because config.py resolves DATA_DIR (and every module's
.bin path) at import time. Doing this here in conftest.py guarantees it runs
before any test module imports `api`, so tests never touch the real data files.
'''

import os
import sys
import tempfile

# 1. Redirect all persistence to a temp dir (before importing the app).
_TMP_DATA_DIR = tempfile.mkdtemp(prefix="cantina-tests-")
os.environ["CANTINA_DATA_DIR"] = _TMP_DATA_DIR

# 2. Make backend/src importable (it isn't a package, so add it to the path).
_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
sys.path.insert(0, _SRC)

import pytest
from fastapi.testclient import TestClient

import db  # noqa: E402
import api  # noqa: E402  (must come after the env + path setup above)


@pytest.fixture(autouse=True)
def clean_data_dir() :
    '''Wipe the temp data dir before each test so cases are independent.
    Deleting the sqlite db file (and its WAL sidecars) plus resetting db's
    init flag means the next access rebuilds an empty schema from scratch.'''
    for name in os.listdir(_TMP_DATA_DIR) :
        os.remove(os.path.join(_TMP_DATA_DIR, name))
    db.reset()
    yield


@pytest.fixture
def client() :
    return TestClient(api.app)
