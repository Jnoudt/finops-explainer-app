"""Deterministic demo costs and Azure Cost Management ingestion."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from azure.identity import DefaultAzureCredential
from azure.mgmt.costmanagement import CostManagementClient
from azure.mgmt.costmanagement.models import (
    GranularityType,
    QueryAggregation,
    QueryDataset,
    QueryDefinition,
    QueryGrouping,
    QueryTimePeriod,
    TimeframeType,
)

from src.config import Mode, Settings
from src.schemas.finops import DailyCostPoint

CENT = Decimal("0.01")
DEMO_DAYS = 30
DEMO_END_DATE = date(2025, 1, 30)


def load_costs(
    mode: Mode | None = None,
    *,
    as_of: date | None = None,
    settings: Settings | None = None,
) -> list[DailyCostPoint]:
    """Load a 30-day daily cost series from demo data or Cost Management."""
    runtime = settings or Settings.from_environment()
    selected_mode = mode or runtime.mode

    if selected_mode == "demo":
        return create_demo_costs(as_of)
    if runtime.subscription_id is None:
        raise ValueError("AZURE_SUBSCRIPTION_ID is required when MODE=live.")
    if runtime.cost_management_scope is None:
        raise ValueError("COST_MANAGEMENT_SCOPE could not be resolved for live mode.")
    return _load_live_costs(runtime, as_of or date.today())


def create_demo_costs(as_of: date | None = None) -> list[DailyCostPoint]:
    """Build a reproducible 30-day, four-service Azure cost fixture."""
    last_day = as_of or DEMO_END_DATE
    first_day = last_day - timedelta(days=DEMO_DAYS - 1)
    service_profiles: tuple[tuple[str, Decimal, Decimal, dict[int, Decimal]], ...] = (
        ("Virtual Machines", Decimal("46.00"), Decimal("0.75"), {22: Decimal("3.4")}),
        ("Azure SQL Database", Decimal("21.00"), Decimal("0.40"), {25: Decimal("2.8")}),
        ("Storage", Decimal("7.50"), Decimal("0.12"), {}),
        ("App Service", Decimal("12.00"), Decimal("0.25"), {}),
    )
    points: list[DailyCostPoint] = []

    for service_name, base_cost, daily_step, spikes in service_profiles:
        for day_index in range(DEMO_DAYS):
            ordinary_variation = Decimal((day_index % 5) - 2) * daily_step
            amount = base_cost + ordinary_variation
            if day_index in spikes:
                amount *= spikes[day_index]
            points.append(
                DailyCostPoint(
                    date=first_day + timedelta(days=day_index),
                    service_name=service_name,
                    amount=amount.quantize(CENT, rounding=ROUND_HALF_UP),
                    currency="USD",
                )
            )
    return sorted(points, key=lambda point: (point.date, point.service_name))


def _load_live_costs(settings: Settings, end_date: date) -> list[DailyCostPoint]:
    if settings.cost_management_scope is None or settings.subscription_id is None:
        raise ValueError("Live Cost Management settings are incomplete.")
    start_date = end_date - timedelta(days=DEMO_DAYS - 1)
    credential = DefaultAzureCredential(
        managed_identity_client_id=settings.managed_identity_client_id
    )
    query = QueryDefinition(
        type="Usage",
        timeframe=TimeframeType.CUSTOM,
        time_period=QueryTimePeriod(
            from_property=datetime.combine(start_date, time.min, tzinfo=timezone.utc),
            to=datetime.combine(end_date, time.min, tzinfo=timezone.utc),
        ),
        dataset=QueryDataset(
            granularity=GranularityType.DAILY,
            aggregation={
                "totalCost": QueryAggregation(name="PreTaxCost", function="Sum")
            },
            grouping=[QueryGrouping(type="Dimension", name="ServiceName")],
        ),
    )

    with credential:
        with CostManagementClient(credential) as client:
            result = client.query.usage(settings.cost_management_scope, query)

    if result is None or result.columns is None:
        raise ValueError("Cost Management returned an empty query result.")
    column_names = [column.name for column in result.columns]
    required_columns = {"PreTaxCost", "UsageDate", "ServiceName", "Currency"}
    missing_columns = required_columns.difference(column_names)
    if missing_columns:
        raise ValueError(
            "Cost Management response is missing required columns: "
            + ", ".join(sorted(missing_columns))
        )

    points: list[DailyCostPoint] = []
    for row in result.rows or []:
        if len(row) != len(column_names):
            raise ValueError("Cost Management returned a row with an unexpected shape.")
        values = dict(zip(column_names, row, strict=True))
        raw_date = str(values["UsageDate"])
        point_date = (
            date.fromisoformat(raw_date)
            if "-" in raw_date
            else datetime.strptime(raw_date, "%Y%m%d").date()
        )
        points.append(
            DailyCostPoint(
                date=point_date,
                service_name=str(values["ServiceName"]),
                amount=Decimal(str(values["PreTaxCost"])).quantize(
                    CENT, rounding=ROUND_HALF_UP
                ),
                currency=str(values["Currency"]),
            )
        )
    return sorted(points, key=lambda point: (point.date, point.service_name))
