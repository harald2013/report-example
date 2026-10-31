import tomllib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from temporalio.client import WorkflowExecutionStatus
from temporalio.service import RPCError, RPCStatusCode

from reports.api import create_app
from reports.config import Settings


@pytest.fixture
def dependencies():
    store = SimpleNamespace(
        ready=AsyncMock(),
        get=AsyncMock(return_value=None),
        latest=AsyncMock(return_value=[]),
    )
    temporal = SimpleNamespace(
        start_workflow=AsyncMock(),
        get_workflow_handle=Mock(),
        service_client=SimpleNamespace(check_health=AsyncMock(return_value=True)),
    )
    return store, temporal


@pytest.fixture
def client(dependencies):
    store, temporal = dependencies
    settings = Settings("postgresql://unused", api_token="test-token")
    with TestClient(create_app(settings, store, temporal)) as client:
        client.headers["Authorization"] = "Bearer test-token"
        yield client


def test_acceptance_starts_durable_workflow(client, dependencies):
    store, temporal = dependencies
    response = client.post("/reports", json={"values": [10, 20, 30]})
    assert response.status_code == 202
    report_id = response.json()["id"]
    args, kwargs = temporal.start_workflow.call_args
    assert args[1].values == [10, 20, 30]
    assert args[1].report_id == report_id
    assert kwargs["id"] == f"report-{report_id}"
    store.get.assert_not_called()


@pytest.mark.parametrize(
    "body",
    [
        {"values": []},
        {"values": [1e13]},
        {"values": [1] * 1001},
        {"values": [1], "delay_seconds": -1},
        {"values": [1], "delay_seconds": 301},
        {"values": ["NaN"]},
    ],
)
def test_invalid_reports_do_not_start_workflows(client, dependencies, body):
    assert client.post("/reports", json=body).status_code == 422
    dependencies[1].start_workflow.assert_not_called()


def test_authentication_and_public_health(client):
    client.headers.pop("Authorization")
    assert client.post("/reports", json={"values": [1]}).status_code == 401
    assert client.get("/health").status_code == 200


def test_public_version_reports_project_metadata(client):
    client.headers.pop("Authorization")
    pyproject = Path(__file__).parent.parent / "pyproject.toml"
    project = tomllib.loads(pyproject.read_text())["project"]
    response = client.get("/version")
    assert response.status_code == 200
    assert response.json() == {"name": project["name"], "version": project["version"]}


def test_nonfinite_json_returns_validation_error_without_echo(client):
    response = client.post("/reports", content='{"values": [NaN]}')
    assert response.status_code == 422
    assert "NaN" not in response.text


def test_unavailable_temporal_never_returns_acceptance(client, dependencies):
    dependencies[1].start_workflow.side_effect = ConnectionError("secret endpoint")
    response = client.post("/reports", json={"values": [1]})
    assert response.status_code == 503
    assert "secret" not in response.text


def test_missing_report(client, dependencies):
    dependencies[1].get_workflow_handle.return_value.describe = AsyncMock(
        side_effect=RPCError("not found", RPCStatusCode.NOT_FOUND, b"")
    )
    assert client.get(f"/reports/{uuid4()}").status_code == 404


def test_failed_workflow_is_not_hidden_by_processing_row(client, dependencies):
    dependencies[0].get.return_value = {"status": "processing"}
    dependencies[1].get_workflow_handle.return_value.describe = AsyncMock(
        return_value=SimpleNamespace(status=WorkflowExecutionStatus.FAILED)
    )
    response = client.get(f"/reports/{uuid4()}")
    assert response.json()["status"] == "failed"


def test_completed_results_remain_available_without_temporal(client, dependencies):
    dependencies[0].get.return_value = {"status": "completed", "result": {"sum": 60}}
    response = client.get(f"/reports/{uuid4()}")
    assert response.json()["result"]["sum"] == 60
    dependencies[1].get_workflow_handle.assert_not_called()


def test_list_returns_latest_reports_first(client, dependencies):
    newest = {"id": str(uuid4()), "status": "completed", "result": {"sum": 3}}
    older = {"id": str(uuid4()), "status": "completed", "result": {"sum": 60}}
    dependencies[0].latest.return_value = [newest, older]
    response = client.get("/reports", params={"limit": 2})
    assert response.status_code == 200
    assert response.json() == {"items": [newest, older]}
    dependencies[0].latest.assert_awaited_once_with(2)
    dependencies[1].get_workflow_handle.assert_not_called()


def test_list_uses_default_limit(client, dependencies):
    response = client.get("/reports")
    assert response.status_code == 200
    assert response.json() == {"items": []}
    dependencies[0].latest.assert_awaited_once_with(20)


@pytest.mark.parametrize("limit", ["0", "101", "-1", "abc"])
def test_list_rejects_invalid_limit(client, dependencies, limit):
    assert client.get("/reports", params={"limit": limit}).status_code == 422
    dependencies[0].latest.assert_not_called()


def test_list_requires_token(client, dependencies):
    client.headers.pop("Authorization")
    assert client.get("/reports").status_code == 401
    client.headers["Authorization"] = "Bearer wrong-token"
    assert client.get("/reports").status_code == 401
    dependencies[0].latest.assert_not_called()


def test_list_reports_unavailable_database(client, dependencies):
    dependencies[0].latest.side_effect = ConnectionError("password")
    response = client.get("/reports")
    assert response.status_code == 503
    assert "password" not in response.text


def test_readiness_detects_database_failure(client, dependencies):
    dependencies[0].ready.side_effect = ConnectionError("password")
    assert client.get("/ready").status_code == 503
    assert client.get("/health").status_code == 200


def test_readiness_detects_temporal_failure(client, dependencies):
    dependencies[1].service_client.check_health.return_value = False
    assert client.get("/ready").status_code == 503


def test_public_ui_never_embeds_token_or_queries_dependencies(client, dependencies):
    client.headers.pop("Authorization")
    page = client.get("/ui/")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "<h1>Report example" in page.text
    assert "test-token" not in page.text
    assert client.get("/ui/app.js").status_code == 200
    assert client.get("/ui/style.css").status_code == 200
    dependencies[0].ready.assert_not_called()
    dependencies[0].get.assert_not_called()
    dependencies[0].latest.assert_not_called()
    dependencies[1].start_workflow.assert_not_called()
    dependencies[1].service_client.check_health.assert_not_called()
    assert client.get("/").status_code == 401
