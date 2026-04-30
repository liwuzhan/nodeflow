import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from cloud.server.app import create_app
    from cloud.server.database import engine, Base
    from cloud.server.services.sse_broker import SSEBroker

    Base.metadata.create_all(bind=engine)
    app = create_app()
    app.state.sse = SSEBroker()
    with TestClient(app) as c:
        yield c
