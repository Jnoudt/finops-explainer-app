"""Azure Functions v2 API and scheduled cost analysis."""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import date
from typing import Any

import azure.functions as func

from src.config import Settings
from src.engine.anomaly_detector import build_run_summary, detect_anomalies
from src.engine.cost_ingestor import load_costs
from src.engine.narrator import generate_narrative
from src.engine.store import FinOpsStore
from src.observability import configure_json_logging, correlation_context
from src.schemas.finops import DashboardPayload

configure_json_logging()
logger = logging.getLogger(__name__)
app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)
settings = Settings.from_environment()
store = FinOpsStore(settings)

_CORRELATION_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_TRACEPARENT_PATTERN = re.compile(
    r"^[0-9a-f]{2}-([0-9a-f]{32})-[0-9a-f]{16}-[0-9a-f]{2}$",
    re.IGNORECASE,
)


@app.route(route="health", methods=["GET"])
def health(req: func.HttpRequest) -> func.HttpResponse:
    correlation_id, trace_id = _request_ids(req)
    with correlation_context(correlation_id, trace_id):
        return _json_response(
            {
                "status": "ok",
                "mode": settings.mode,
                "persistence_mode": settings.persistence_mode,
                "correlation_id": correlation_id,
            },
            correlation_id=correlation_id,
            trace_id=trace_id,
        )


@app.route(route="anomalies", methods=["GET"])
def anomalies(req: func.HttpRequest) -> func.HttpResponse:
    correlation_id, trace_id = _request_ids(req)
    with correlation_context(correlation_id, trace_id):
        try:
            limit = _parse_limit(req.params.get("limit"), default=100)
            service_name = req.params.get("service") or None
            severity = req.params.get("severity") or None
            if severity not in (None, "low", "medium", "high", "critical"):
                return _error_response(
                    400,
                    "severity must be low, medium, high, or critical.",
                    correlation_id,
                    trace_id,
                )
            result = store.list_anomalies(
                limit,
                service_name=service_name,
                severity=severity,
            )
            return _json_response(
                {"anomalies": result, "correlation_id": correlation_id},
                correlation_id=correlation_id,
                trace_id=trace_id,
            )
        except ValueError:
            return _error_response(
                400, "Invalid query parameters.", correlation_id, trace_id
            )
        except Exception as error:
            return _internal_error(
                "anomalies_query_failed", error, correlation_id, trace_id
            )


@app.route(route="runs", methods=["GET"])
def runs(req: func.HttpRequest) -> func.HttpResponse:
    correlation_id, trace_id = _request_ids(req)
    with correlation_context(correlation_id, trace_id):
        run_id = req.params.get("run_id")
        try:
            if run_id:
                document = store.get_run(run_id)
                if document is None:
                    return _error_response(
                        404, "Run not found.", correlation_id, trace_id
                    )
                body = {
                    "run_id": document["run_id"],
                    "created_at": document["created_at"],
                    **document["payload"],
                }
            else:
                limit = _parse_limit(req.params.get("limit"), default=50)
                body = {"runs": store.list_runs(limit)}
            body["correlation_id"] = correlation_id
            return _json_response(
                body, correlation_id=correlation_id, trace_id=trace_id
            )
        except ValueError:
            return _error_response(
                400, "Invalid query parameters.", correlation_id, trace_id
            )
        except Exception as error:
            return _internal_error("runs_query_failed", error, correlation_id, trace_id)


@app.route(route="analyze", methods=["POST"])
def analyze(req: func.HttpRequest) -> func.HttpResponse:
    correlation_id, trace_id = _request_ids(req)
    with correlation_context(correlation_id, trace_id):
        try:
            body = req.get_json()
            if not isinstance(body, dict):
                return _error_response(
                    400, "Request body must be a JSON object.", correlation_id, trace_id
                )
            unknown_fields = set(body).difference({"as_of"})
            if unknown_fields:
                return _error_response(
                    400,
                    "Request contains unsupported fields.",
                    correlation_id,
                    trace_id,
                )
            as_of_raw = body.get("as_of")
            as_of = date.fromisoformat(as_of_raw) if as_of_raw is not None else None
            run_id, payload = analyze_costs(
                correlation_id=correlation_id,
                as_of=as_of,
            )
            return _json_response(
                {"run_id": run_id, **payload.model_dump(mode="json")},
                correlation_id=correlation_id,
                trace_id=trace_id,
            )
        except (ValueError, TypeError):
            return _error_response(
                400, "Invalid analysis request.", correlation_id, trace_id
            )
        except Exception as error:
            return _internal_error("analysis_failed", error, correlation_id, trace_id)


@app.timer_trigger(
    schedule="0 0 */6 * * *",
    arg_name="timer",
    run_on_startup=False,
    use_monitor=True,
)
def scheduled_analysis(timer: func.TimerRequest) -> None:
    correlation_id = uuid.uuid4().hex
    with correlation_context(correlation_id):
        try:
            analyze_costs(correlation_id=correlation_id)
        except Exception as error:
            logger.error(
                "scheduled_analysis_failed",
                extra={
                    "correlation_id": correlation_id,
                    "error_type": type(error).__name__,
                },
            )
            raise RuntimeError(
                "Scheduled analysis failed; inspect sanitized application logs."
            ) from None


def analyze_costs(
    *,
    correlation_id: str,
    as_of: date | None = None,
) -> tuple[str, DashboardPayload]:
    points = load_costs(settings.mode, as_of=as_of, settings=settings)
    findings = detect_anomalies(points)
    summary = build_run_summary(points, findings, source_mode=settings.mode)
    narration = generate_narrative(
        findings,
        correlation_id=correlation_id,
        settings=settings,
    )
    payload = DashboardPayload(
        correlation_id=correlation_id,
        summary=summary,
        daily_costs=tuple(points),
        anomalies=tuple(findings),
        narrative=narration.narrative,
        fact_check=narration.fact_check,
    )
    run_id = uuid.uuid4().hex
    store.persist_run(run_id, payload)
    logger.info(
        "analysis_completed",
        extra={
            "correlation_id": correlation_id,
            "run_id": run_id,
            "point_count": summary.point_count,
            "anomaly_count": summary.anomaly_count,
        },
    )
    return run_id, payload


def _request_ids(req: func.HttpRequest) -> tuple[str, str]:
    supplied_correlation = req.headers.get("x-correlation-id", "")
    correlation_id = (
        supplied_correlation
        if _CORRELATION_PATTERN.fullmatch(supplied_correlation)
        else uuid.uuid4().hex
    )
    trace_match = _TRACEPARENT_PATTERN.fullmatch(req.headers.get("traceparent", ""))
    trace_id = trace_match.group(1).lower() if trace_match else "-"
    return correlation_id, trace_id


def _parse_limit(raw_value: str | None, *, default: int) -> int:
    if raw_value is None:
        return default
    try:
        limit = int(raw_value)
    except ValueError as error:
        raise ValueError("limit must be an integer.") from error
    if not 1 <= limit <= 500:
        raise ValueError("limit is outside the permitted range.")
    return limit


def _json_response(
    body: dict[str, Any],
    *,
    status_code: int = 200,
    correlation_id: str,
    trace_id: str,
) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(body, separators=(",", ":"), ensure_ascii=True),
        status_code=status_code,
        mimetype="application/json",
        headers={
            "x-correlation-id": correlation_id,
            "traceparent-id": trace_id,
        },
    )


def _error_response(
    status_code: int,
    message: str,
    correlation_id: str,
    trace_id: str,
) -> func.HttpResponse:
    return _json_response(
        {"error": message, "correlation_id": correlation_id},
        status_code=status_code,
        correlation_id=correlation_id,
        trace_id=trace_id,
    )


def _internal_error(
    event_name: str,
    error: Exception,
    correlation_id: str,
    trace_id: str,
) -> func.HttpResponse:
    logger.error(
        event_name,
        extra={
            "correlation_id": correlation_id,
            "error_type": type(error).__name__,
        },
    )
    return _error_response(
        500,
        "Request could not be completed.",
        correlation_id,
        trace_id,
    )
