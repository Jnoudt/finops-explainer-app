"""Validate all numeric figures in a narrative against deterministic findings."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Iterable

from src.schemas.finops import AnomalyFinding, CheckedClaim, FactCheckVerdict

_NUMBER_PATTERN = re.compile(
    r"(?<![\w/.-])(?P<currency>USD\s*|\$\s*)?"
    r"(?P<number>-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)"
    r"(?P<percent>\s*(?:%|percent\b))?",
    re.IGNORECASE,
)
_DATE_PATTERN = re.compile(r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})\b")


def check_narrative(
    narrative: str, findings: Iterable[AnomalyFinding]
) -> FactCheckVerdict:
    """Accept only when each extracted numeric claim matches a finding."""
    finding_list = list(findings)
    valid_percentages = {
        finding.delta_percentage
        for finding in finding_list
        if finding.delta_percentage is not None
    }
    valid_values: dict[Decimal, str] = {}
    for finding in finding_list:
        candidates = (
            (finding.actual_cost, "actual_cost"),
            (finding.baseline_cost, "baseline_cost"),
            (finding.delta_amount, "delta_amount"),
            (finding.z_score, "z_score"),
        )
        for value, field_name in candidates:
            if value is not None:
                valid_values.setdefault(value, field_name)

    date_spans = [match.span() for match in _DATE_PATTERN.finditer(narrative)]
    claims: list[CheckedClaim] = []
    for match in _NUMBER_PATTERN.finditer(narrative):
        if any(
            match.start() >= start and match.end() <= end for start, end in date_spans
        ):
            continue
        raw_figure = match.group("number")
        figure = Decimal(raw_figure.replace(",", ""))
        rendered = match.group(0).strip()
        if match.group("percent"):
            supported = figure in valid_percentages
            matched_field = "delta_percentage" if supported else None
        else:
            matched_field = valid_values.get(figure)
            supported = matched_field is not None
        claims.append(
            CheckedClaim(
                figure=rendered,
                supported=supported,
                matched_field=matched_field,
            )
        )

    unsupported = tuple(claim.figure for claim in claims if not claim.supported)
    return FactCheckVerdict(
        accepted=not unsupported,
        checked_claims=tuple(claims),
        unsupported_claims=unsupported,
    )
