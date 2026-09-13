import sys
import os
from pathlib import Path

# Ensure project root is on PYTHONPATH (for 'cloud.server.*' imports)
_project_root = Path(__file__).resolve().parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest
from fastapi.testclient import TestClient


_test_db_path = Path(f"/tmp/nodeflow-cloud-tests-{os.getpid()}.db")
os.environ["NF_CLOUD_DATABASE_URL"] = f"sqlite:///{_test_db_path}"


@pytest.fixture
def client():
    from cloud.server.app import create_app
    from cloud.server.database import engine, Base
    from cloud.server.services.sse_broker import SSEBroker

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    app = create_app()
    app.state.sse = SSEBroker()
    with TestClient(app) as c:
        yield c


def pytest_sessionfinish(session, exitstatus):
    from cloud.server.database import engine

    engine.dispose()
    for suffix in ("", "-wal", "-shm"):
        Path(str(_test_db_path) + suffix).unlink(missing_ok=True)
