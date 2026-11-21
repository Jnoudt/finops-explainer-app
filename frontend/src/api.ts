import type {
  AnalysisResponse,
  AnomaliesResponse,
  HealthResponse,
  RunDetail,
  RunsResponse,
} from "./types";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export interface DashboardSnapshot {
  health: HealthResponse;
  anomalies: AnomaliesResponse["anomalies"];
  runs: RunsResponse["runs"];
  latestRun: RunDetail | null;
}

async function requestJson<T>(
  apiBaseUrl: string,
  path: string,
  functionKey: string,
  signal?: AbortSignal,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      "x-functions-key": functionKey,
      ...init?.headers,
    },
    cache: "no-store",
    signal,
  });

  if (!response.ok) {
    throw new ApiError(response.status, "The FinOps API request was rejected.");
  }

  try {
    return (await response.json()) as T;
  } catch {
    throw new Error("The FinOps API returned an invalid response.");
  }
}

export async function fetchDashboard(
  apiBaseUrl: string,
  functionKey: string,
  signal?: AbortSignal,
): Promise<DashboardSnapshot> {
  const [health, anomalyResponse, runResponse] = await Promise.all([
    requestJson<HealthResponse>(apiBaseUrl, "/health", functionKey, signal),
    requestJson<AnomaliesResponse>(
      apiBaseUrl,
      "/anomalies?limit=100",
      functionKey,
      signal,
    ),
    requestJson<RunsResponse>(apiBaseUrl, "/runs?limit=25", functionKey, signal),
  ]);
  const latestRun = runResponse.runs[0]
    ? await requestJson<RunDetail>(
        apiBaseUrl,
        `/runs?run_id=${encodeURIComponent(runResponse.runs[0].run_id)}`,
        functionKey,
        signal,
      )
    : null;

  return {
    health,
    anomalies: latestRun
      ? latestRun.anomalies.map((anomaly) => ({
          ...anomaly,
          run_id: latestRun.run_id,
        }))
      : anomalyResponse.anomalies,
    runs: runResponse.runs,
    latestRun,
  };
}

export function analyzeNow(
  apiBaseUrl: string,
  functionKey: string,
  signal?: AbortSignal,
): Promise<AnalysisResponse> {
  return requestJson<AnalysisResponse>(
    apiBaseUrl,
    "/analyze",
    functionKey,
    signal,
    {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
    },
  );
}

export function fetchRun(
  apiBaseUrl: string,
  runId: string,
  functionKey: string,
  signal?: AbortSignal,
): Promise<RunDetail> {
  return requestJson<RunDetail>(
    apiBaseUrl,
    `/runs?run_id=${encodeURIComponent(runId)}`,
    functionKey,
    signal,
  );
}

export function apiErrorMessage(error: unknown): string {
  if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
    return "Function key was rejected. Check the key and try again.";
  }
  if (error instanceof TypeError) {
    return "The API could not be reached. Showing the in-memory demo preview.";
  }
  return "The request could not be completed. Try again or check API availability.";
}

export function isNetworkError(error: unknown): boolean {
  return error instanceof TypeError;
}

