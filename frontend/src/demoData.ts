import type {
  AnomalyFinding,
  DashboardPayload,
  RunListItem,
} from "./types";

export const demoAnomalies: Array<AnomalyFinding & { run_id: string }> = [
  {
    run_id: "offline-preview",
    date: "2025-01-23",
    service_name: "Virtual Machines",
    actual_cost: "156.40",
    baseline_cost: "46.00",
    delta_amount: "110.40",
    delta_percentage: "240.00",
    z_score: "100.56",
    currency: "USD",
    severity: "critical",
    direction: "increase",
  },
  {
    run_id: "offline-preview",
    date: "2025-01-26",
    service_name: "Azure SQL Database",
    actual_cost: "56.56",
    baseline_cost: "21.06",
    delta_amount: "35.50",
    delta_percentage: "168.59",
    z_score: "65.49",
    currency: "USD",
    severity: "critical",
    direction: "increase",
  },
];

export const demoDashboard: DashboardPayload = {
  correlation_id: "offline-preview",
  summary: {
    start_date: "2025-01-01",
    end_date: "2025-01-30",
    total_cost: "2741.76",
    currency: "USD",
    point_count: 120,
    service_count: 4,
    anomaly_count: 2,
    source_mode: "demo",
  },
  anomalies: demoAnomalies,
  narrative: {
    text: "Virtual Machines on 2025-01-23 was USD 156.40, 240.00% above its USD 46.00 baseline. Azure SQL Database on 2025-01-26 was USD 56.56, 168.59% above its USD 21.06 baseline.",
    generated_at: "2025-01-30T00:00:00Z",
    provider: "deterministic_template",
  },
  fact_check: {
    accepted: true,
    checked_claims: [
      { figure: "156.40", supported: true, matched_field: "actual_cost" },
      { figure: "240.00%", supported: true, matched_field: "delta_percentage" },
      { figure: "46.00", supported: true, matched_field: "baseline_cost" },
      { figure: "56.56", supported: true, matched_field: "actual_cost" },
      { figure: "168.59%", supported: true, matched_field: "delta_percentage" },
      { figure: "21.06", supported: true, matched_field: "baseline_cost" },
    ],
    unsupported_claims: [],
  },
};

export const demoRuns: RunListItem[] = [
  {
    run_id: "offline-preview",
    created_at: "2025-01-30T00:00:00Z",
    summary: demoDashboard.summary,
    anomaly_count: 2,
  },
];

export const demoRemediation: Record<string, string> = {
  "Virtual Machines":
    "Review utilization and recent SKU or autoscale changes; right-size only after confirming workload demand.",
  "Azure SQL Database":
    "Check database utilization, compute tier changes, and autoscale settings before adjusting capacity.",
  Storage:
    "Inspect storage growth, transaction volume, and lifecycle policies for unexpected changes.",
  "App Service":
    "Review plan scaling, instance count, and deployment activity for the affected period.",
};
