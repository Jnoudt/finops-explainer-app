export type Mode = "demo" | "live";
export type Severity = "low" | "medium" | "high" | "critical";

export interface AnomalyFinding {
  date: string;
  service_name: string;
  actual_cost: string;
  baseline_cost: string;
  delta_amount: string;
  delta_percentage: string | null;
  z_score: string | null;
  currency: string;
  severity: Severity;
  direction: "increase" | "decrease";
}

export interface RunSummary {
  start_date: string;
  end_date: string;
  total_cost: string;
  currency: string;
  point_count: number;
  service_count: number;
  anomaly_count: number;
  source_mode: Mode;
}

export interface NarrativeOutput {
  text: string;
  generated_at: string;
  provider: string;
}

export interface FactCheckVerdict {
  accepted: boolean;
  checked_claims: Array<{
    figure: string;
    supported: boolean;
    matched_field: string | null;
  }>;
  unsupported_claims: string[];
}

export interface DashboardPayload {
  correlation_id: string;
  summary: RunSummary;
  anomalies: AnomalyFinding[];
  narrative: NarrativeOutput | null;
  fact_check: FactCheckVerdict | null;
}

export interface RunListItem {
  run_id: string;
  created_at: string;
  summary: RunSummary;
  anomaly_count: number;
}

export interface HealthResponse {
  status: string;
  mode: Mode;
  persistence_mode: "memory" | "azure";
  correlation_id: string;
}

export interface AnomaliesResponse {
  anomalies: Array<AnomalyFinding & { run_id: string }>;
}

export interface RunsResponse {
  runs: RunListItem[];
}

export type RunDetail = DashboardPayload & {
  run_id: string;
  created_at: string;
};

export type AnalysisResponse = DashboardPayload & { run_id: string };
