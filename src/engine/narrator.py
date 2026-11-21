"""Executive narratives constrained to deterministic anomaly findings."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from azure.core.exceptions import AzureError
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import APIError, AzureOpenAI

from src.config import Settings
from src.engine.fact_checker import check_narrative
from src.schemas.finops import AnomalyFinding, FactCheckVerdict, NarrativeOutput

logger = logging.getLogger(__name__)
AZURE_OPENAI_SCOPE = "https://cognitiveservices.azure.com/.default"


@dataclass(frozen=True)
class NarrationResult:
    narrative: NarrativeOutput
    fact_check: FactCheckVerdict


def generate_narrative(
    findings: list[AnomalyFinding],
    *,
    correlation_id: str,
    settings: Settings | None = None,
) -> NarrationResult:
    """Generate an optional Azure OpenAI narrative and fail closed to a template."""
    runtime = settings or Settings.from_environment()
    credential: DefaultAzureCredential | None = None
    client: AzureOpenAI | None = None
    deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "").strip()
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "").strip()

    if deployment and endpoint:
        try:
            credential = DefaultAzureCredential(
                managed_identity_client_id=runtime.managed_identity_client_id
            )
            token_provider = get_bearer_token_provider(credential, AZURE_OPENAI_SCOPE)
            client = AzureOpenAI(
                azure_endpoint=endpoint,
                azure_ad_token_provider=token_provider,
                api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21"),
                timeout=20.0,
                max_retries=0,
            )
            response = client.chat.completions.create(
                model=deployment,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Write a concise executive explanation using only the "
                            "provided verified anomaly records. Do not calculate, "
                            "infer, or introduce any numbers, percentages, dates, "
                            "or financial amounts. Explain likely operational "
                            "significance without asserting an unprovided cause."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            "Explain these verified anomaly records for an executive. "
                            "Use no numerical claims beyond those explicitly present "
                            "in the records:\n" + _format_findings(findings)
                        ),
                    },
                ],
                temperature=0,
                max_tokens=350,
            )
            content = response.choices[0].message.content
            if not content or not content.strip():
                logger.warning(
                    "narrative_provider_returned_empty_content",
                    extra={"correlation_id": correlation_id},
                )
                return _template_narrative(findings)
            narrative = _narrative(content.strip(), "azure_openai")
            verdict = check_narrative(narrative.text, findings)
            if verdict.accepted:
                return NarrationResult(narrative=narrative, fact_check=verdict)
            logger.warning(
                "narrative_fact_check_rejected",
                extra={
                    "correlation_id": correlation_id,
                    "unsupported_claim_count": len(verdict.unsupported_claims),
                },
            )
        except (APIError, AzureError, ValueError) as error:
            logger.warning(
                "narrative_provider_unavailable",
                extra={
                    "correlation_id": correlation_id,
                    "error_type": type(error).__name__,
                },
            )
        finally:
            if client is not None:
                client.close()
            if credential is not None:
                credential.close()

    return _template_narrative(findings)


def _template_narrative(findings: list[AnomalyFinding]) -> NarrationResult:
    if not findings:
        text = "No anomalies were detected in the analyzed cost data."
    else:
        sentences = [
            _finding_sentence(finding)
            for finding in sorted(
                findings, key=lambda item: (item.date, item.service_name)
            )[:3]
        ]
        text = " ".join(sentences)

    narrative = _narrative(text, "deterministic_template")
    verdict = check_narrative(narrative.text, findings)
    if not verdict.accepted:
        raise ValueError("Deterministic narrative failed numerical fact checking.")
    return NarrationResult(narrative=narrative, fact_check=verdict)


def _finding_sentence(finding: AnomalyFinding) -> str:
    amount = f"{finding.currency} {_money(finding.actual_cost)}"
    baseline = f"{finding.currency} {_money(finding.baseline_cost)}"
    direction = "above" if finding.direction == "increase" else "below"
    percentage = (
        f"{_money(finding.delta_percentage)}%"
        if finding.delta_percentage is not None
        else "an unquantified percentage"
    )
    date_text = finding.date.isoformat()
    return (
        f"{finding.service_name} on {date_text} was {amount}, "
        f"{percentage} {direction} its {baseline} baseline."
    )


def _money(value: Decimal | None) -> str:
    return "not available" if value is None else f"{value:,.2f}"


def _format_findings(findings: list[AnomalyFinding]) -> str:
    return (
        "\n".join(
            finding.model_dump_json()
            for finding in sorted(
                findings, key=lambda item: (item.date, item.service_name)
            )
        )
        or "No anomaly findings."
    )


def _narrative(text: str, provider: str) -> NarrativeOutput:
    return NarrativeOutput(
        text=text,
        generated_at=datetime.now(timezone.utc),
        provider=provider,
    )
