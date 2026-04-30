import sys
import os
from pathlib import Path

# Ensure project root is on PYTHONPATH (for 'cloud.server.*' imports)
_project_root = Path(__file__).resolve().parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    # Remove stale DB file for clean test isolation
    db_path = Path(__file__).resolve().parent.parent / "farm.db"
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(db_path) + suffix)
        p.unlink(missing_ok=True)

    from cloud.server.app import create_app
    from cloud.server.database import engine, Base
    from cloud.server.services.sse_broker import SSEBroker

    # Dispose any stale connections before creating fresh tables
    engine.dispose()
    Base.metadata.create_all(bind=engine)

    app = create_app()
    app.state.sse = SSEBroker()
    with TestClient(app) as c:
        yield c
