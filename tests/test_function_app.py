import json

from unittest.mock import MagicMock

import function_app


def test_analyze_endpoint_creates_a_run_that_can_be_read() -> None:
    request = MagicMock()
    request.headers = {"x-correlation-id": "phase3-test"}
    request.get_json.return_value = {}

    response = function_app.analyze(request)
    body = json.loads(response.get_body())

    assert response.status_code == 200
    assert body["correlation_id"] == "phase3-test"
    stored = function_app.store.get_run(body["run_id"])
    assert stored is not None
    assert stored["payload"]["fact_check"]["accepted"]


def test_invalid_analyze_body_is_rejected_without_internal_details() -> None:
    request = MagicMock()
    request.headers = {}
    request.get_json.return_value = {"unknown": "value"}

    response = function_app.analyze(request)
    body = json.loads(response.get_body())

    assert response.status_code == 400
    assert body["error"] == "Request contains unsupported fields."
    assert "unknown" not in response.get_body().decode()


def test_runs_and_anomalies_routes_return_analysis_records() -> None:
    analyze_request = MagicMock()
    analyze_request.headers = {}
    analyze_request.get_json.return_value = {}
    analyzed = function_app.analyze(analyze_request)
    run_id = json.loads(analyzed.get_body())["run_id"]

    runs_request = MagicMock()
    runs_request.headers = {}
    runs_request.params = {"limit": "10"}
    runs_response = function_app.runs(runs_request)
    runs_body = json.loads(runs_response.get_body())

    anomalies_request = MagicMock()
    anomalies_request.headers = {}
    anomalies_request.params = {"limit": "10", "severity": "critical"}
    anomalies_response = function_app.anomalies(anomalies_request)
    anomalies_body = json.loads(anomalies_response.get_body())

    assert runs_response.status_code == 200
    assert any(item["run_id"] == run_id for item in runs_body["runs"])
    assert anomalies_response.status_code == 200
    assert anomalies_body["anomalies"]
    assert all(item["severity"] == "critical" for item in anomalies_body["anomalies"])


def test_health_endpoint_exposes_mode_not_resource_secrets() -> None:
    request = MagicMock()
    request.headers = {
        "traceparent": "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01"
    }

    response = function_app.health(request)
    body = json.loads(response.get_body())

    assert response.status_code == 200
    assert body["mode"] == "demo"
    assert body["persistence_mode"] == "memory"
    assert response.headers["traceparent-id"] == "0123456789abcdef0123456789abcdef"


def test_http_routes_require_function_keys() -> None:
    http_functions = [
        json.loads(function.get_function_json())
        for function in function_app.app.get_functions()
        if json.loads(function.get_function_json())["bindings"][0]["type"]
        == "httpTrigger"
    ]

    assert len(http_functions) == 4
    assert all(
        function["bindings"][0]["authLevel"] == "FUNCTION"
        for function in http_functions
    )
