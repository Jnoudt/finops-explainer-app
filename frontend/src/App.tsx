import {
  Activity,
  AlertCircle,
  ArrowDownRight,
  ArrowUpRight,
  BadgeCheck,
  BarChart3,
  Check,
  ChevronRight,
  CircleHelp,
  Clock3,
  Cloud,
  Database,
  Gauge,
  KeyRound,
  LockKeyhole,
  Play,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Wallet,
  X,
} from "lucide-react";
import { useMemo, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import {
  analyzeNow,
  apiErrorMessage,
  fetchDashboard,
  fetchRun,
  isNetworkError,
  type DashboardSnapshot,
} from "./api";
import {
  demoAnomalies,
  demoDashboard,
  demoRemediation,
  demoRuns,
} from "./demoData";
import type {
  AnomalyFinding,
  DashboardPayload,
  HealthResponse,
  RunListItem,
} from "./types";

type ViewMode = "live" | "offline-demo";
type RequestState = "idle" | "loading" | "ready" | "error";

const initialHealth: HealthResponse = {
  status: "offline-preview",
  mode: "demo",
  persistence_mode: "memory",
  correlation_id: "offline-preview",
};

function formatCurrency(value: string | null | undefined, currency = "USD") {
  if (value == null) return "—";
  const parsed = /^(-?)(\d+)(?:\.(\d+))?$/.exec(value);
  if (!parsed) return `${currency} ${value}`;
  const [, sign = "", whole = "0", rawFraction = ""] = parsed;
  const fraction = rawFraction.padEnd(2, "0");
  const groupedWhole = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  try {
    const symbol = new Intl.NumberFormat("en-US", {
      style: "currency",
      currency,
    })
      .formatToParts(0)
      .find((part) => part.type === "currency")?.value;
    return `${symbol ?? currency}${sign}${groupedWhole}.${fraction}`;
  } catch {
    return `${currency} ${sign}${groupedWhole}.${fraction}`;
  }
}

function formatDate(value: string | null | undefined) {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.valueOf())
    ? value
    : new Intl.DateTimeFormat("en-US", {
        month: "short",
        day: "2-digit",
        year: "numeric",
        timeZone: "UTC",
      }).format(parsed);
}

function getRemediation(serviceName: string) {
  return (
    demoRemediation[serviceName] ??
    "Review the service's utilization, recent configuration changes, and allocation tags before taking action."
  );
}

function anomalyKey(anomaly: AnomalyFinding | undefined) {
  return anomaly ? `${anomaly.date}:${anomaly.service_name}` : "";
}

function App() {
  const [apiBaseUrl, setApiBaseUrl] = useState(
    import.meta.env.VITE_API_BASE_URL ?? "/api",
  );
  const [functionKey, setFunctionKey] = useState("");
  const [requestState, setRequestState] = useState<RequestState>("idle");
  const [viewMode, setViewMode] = useState<ViewMode>("offline-demo");
  const [dashboard, setDashboard] = useState<DashboardPayload | null>(demoDashboard);
  const [health, setHealth] = useState<HealthResponse>(initialHealth);
  const [anomalies, setAnomalies] = useState(demoAnomalies);
  const [runs, setRuns] = useState<RunListItem[]>(demoRuns);
  const [selectedKey, setSelectedKey] = useState(
    anomalyKey(demoAnomalies[0]),
  );
  const [errorMessage, setErrorMessage] = useState("");
  const [offlineNotice, setOfflineNotice] = useState(true);

  const selectedAnomaly = useMemo(
    () => anomalies.find((item) => anomalyKey(item) === selectedKey) ?? anomalies[0],
    [anomalies, selectedKey],
  );
  const currentDashboard = dashboard;
  const currentHealth = health;
  const factCheckPassed = currentDashboard?.fact_check?.accepted === true;
  const templateFallback =
    currentDashboard?.narrative?.provider === "deterministic_template";
  const liveReady = viewMode === "live" && requestState === "ready";
  const isBusy = requestState === "loading";

  async function connectToApi(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    if (!functionKey.trim()) {
      setErrorMessage("Enter a Function key to connect to the protected API.");
      return;
    }

    setRequestState("loading");
    setErrorMessage("");
    try {
      const snapshot: DashboardSnapshot = await fetchDashboard(
        apiBaseUrl.trim().replace(/\/+$/, ""),
        functionKey.trim(),
      );
      setHealth(snapshot.health);
      setAnomalies(snapshot.anomalies);
      setRuns(snapshot.runs);
      setDashboard(snapshot.latestRun);
      setSelectedKey(
        snapshot.anomalies[0] ? anomalyKey(snapshot.anomalies[0]) : "",
      );
      setViewMode("live");
      setRequestState("ready");
      setOfflineNotice(false);
    } catch (error) {
      if (isNetworkError(error)) {
        activateOfflinePreview();
        setErrorMessage(apiErrorMessage(error));
      } else {
        setRequestState("error");
        setErrorMessage(apiErrorMessage(error));
      }
    }
  }

  function activateOfflinePreview() {
    setViewMode("offline-demo");
    setHealth(initialHealth);
    setDashboard(demoDashboard);
    setAnomalies(demoAnomalies);
    setRuns(demoRuns);
    setSelectedKey(anomalyKey(demoAnomalies[0]));
    setRequestState("idle");
    setOfflineNotice(true);
  }

  function clearFunctionKey() {
    setFunctionKey("");
    setErrorMessage("");
    if (viewMode === "live") {
      setRequestState("idle");
    }
  }

  async function runAnalysis() {
    if (!functionKey.trim() || !liveReady) return;
    setRequestState("loading");
    setErrorMessage("");
    try {
      const base = apiBaseUrl.trim().replace(/\/+$/, "");
      await analyzeNow(base, functionKey.trim());
      const snapshot = await fetchDashboard(base, functionKey.trim());
      setHealth(snapshot.health);
      setAnomalies(snapshot.anomalies);
      setRuns(snapshot.runs);
      setDashboard(snapshot.latestRun);
      setSelectedKey(
        snapshot.anomalies[0] ? anomalyKey(snapshot.anomalies[0]) : "",
      );
      setRequestState("ready");
    } catch (error) {
      if (isNetworkError(error)) activateOfflinePreview();
      else setRequestState("ready");
      setErrorMessage(apiErrorMessage(error));
    }
  }

  async function openRun(run: RunListItem) {
    if (viewMode !== "live" || !functionKey.trim()) return;
    setRequestState("loading");
    setErrorMessage("");
    try {
      const detail = await fetchRun(
        apiBaseUrl.trim().replace(/\/+$/, ""),
        run.run_id,
        functionKey.trim(),
      );
      setDashboard(detail);
      setAnomalies(detail.anomalies.map((item) => ({ ...item, run_id: run.run_id })));
      setSelectedKey(
        detail.anomalies[0] ? anomalyKey(detail.anomalies[0]) : "",
      );
      setRequestState("ready");
    } catch (error) {
      setRequestState("ready");
      setErrorMessage(apiErrorMessage(error));
    }
  }

  return (
    <main className="min-h-screen bg-[#f4f6f8] text-slate-900">
      <div className="flex min-h-screen">
        <aside className="hidden w-[248px] shrink-0 flex-col bg-[#101927] text-slate-300 lg:flex">
          <div className="flex items-center gap-3 border-b border-white/10 px-6 py-6">
            <div className="grid size-10 place-items-center rounded-xl bg-teal-400 text-slate-950">
              <Gauge size={21} strokeWidth={2.5} />
            </div>
            <div>
              <p className="text-sm font-bold tracking-[0.18em] text-white">
                FINOPS
              </p>
              <p className="mt-0.5 text-[10px] uppercase tracking-[0.2em] text-slate-500">
                Control room
              </p>
            </div>
          </div>
          <div className="px-4 pt-7">
            <p className="px-3 text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">
              Workspace
            </p>
            <div className="mt-3 flex items-center gap-3 rounded-lg bg-white/10 px-3 py-3 text-sm text-white">
              <BarChart3 size={17} className="text-teal-300" />
              Cost overview
              <span className="ml-auto size-1.5 rounded-full bg-teal-300" />
            </div>
            <div className="mt-2 flex items-center gap-3 rounded-lg px-3 py-3 text-sm text-slate-400">
              <Activity size={17} />
              Anomaly review
            </div>
            <div className="mt-2 flex items-center gap-3 rounded-lg px-3 py-3 text-sm text-slate-400">
              <Database size={17} />
              Run ledger
            </div>
          </div>
          <div className="mt-auto border-t border-white/10 p-5">
            <div className="flex items-center gap-2 text-xs font-medium text-slate-300">
              <ShieldCheck size={15} className="text-teal-300" />
              Numerical guardrails active
            </div>
            <p className="mt-2 text-[11px] leading-5 text-slate-500">
              Findings are computed deterministically. Narrative figures are
              verified before display.
            </p>
            <div className="mt-5 flex items-center gap-2 text-[10px] uppercase tracking-[0.14em] text-slate-600">
              <LockKeyhole size={12} />
              Function-key protected API
            </div>
          </div>
        </aside>

        <div className="min-w-0 flex-1">
          <header className="border-b border-slate-200 bg-white">
            <div className="mx-auto flex max-w-[1500px] flex-wrap items-center justify-between gap-4 px-5 py-4 sm:px-8">
              <div className="flex items-center gap-3">
                <div className="grid size-9 place-items-center rounded-lg bg-[#101927] text-teal-300 lg:hidden">
                  <Gauge size={18} />
                </div>
                <div>
                  <div className="flex items-center gap-2 text-xs text-slate-500">
                    <span>FinOps</span>
                    <ChevronRight size={13} />
                    <span className="font-medium text-slate-700">Overview</span>
                  </div>
                  <p className="mt-1 text-[11px] text-slate-400">
                    Enterprise audit &amp; cloud cost intelligence
                  </p>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <div className="flex items-center gap-2 rounded-full border border-slate-200 px-3 py-1.5 text-xs">
                  <span
                    className={`size-2 rounded-full ${liveReady ? "bg-emerald-500" : "bg-amber-400"}`}
                  />
                  <span className="font-medium text-slate-700">
                    {liveReady ? "API connected" : "Preview mode"}
                  </span>
                </div>
                <span className="rounded-full bg-slate-100 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-600">
                  {currentHealth.mode}
                </span>
                {liveReady && (
                  <button
                    type="button"
                    onClick={clearFunctionKey}
                    className="inline-flex items-center gap-1.5 rounded-md px-2 py-1.5 text-xs text-slate-500 hover:bg-slate-100 hover:text-slate-800"
                  >
                    <X size={14} />
                    Clear key
                  </button>
                )}
              </div>
            </div>
          </header>

          <section className="mx-auto max-w-[1500px] space-y-6 px-5 py-7 sm:px-8 sm:py-9">
            <div className="flex flex-col justify-between gap-5 xl:flex-row xl:items-end">
              <div>
                <div className="mb-3 inline-flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-teal-800">
                  <span className="size-1.5 rounded-full bg-teal-500" />
                  Cloud spend intelligence
                </div>
                <h1 className="text-3xl font-semibold tracking-tight text-slate-950 sm:text-[38px]">
                  Cost overview
                </h1>
                <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">
                  Deterministic variance detection with a numerically grounded
                  executive brief.
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => void runAnalysis()}
                  disabled={!liveReady || isBusy}
                  className="inline-flex items-center gap-2 rounded-lg bg-[#102c3c] px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-[#174357] disabled:cursor-not-allowed disabled:opacity-45"
                >
                  {isBusy ? (
                    <RefreshCw size={16} className="animate-spin" />
                  ) : (
                    <Play size={15} fill="currentColor" />
                  )}
                  Run analysis
                </button>
                <button
                  type="button"
                  onClick={() => void connectToApi()}
                  disabled={isBusy || !functionKey.trim()}
                  className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-45"
                >
                  <RefreshCw
                    size={15}
                    className={isBusy ? "animate-spin" : ""}
                  />
                  Refresh
                </button>
              </div>
            </div>

            {offlineNotice && viewMode === "offline-demo" && (
              <div className="flex flex-col justify-between gap-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-4 sm:flex-row sm:items-center">
                <div className="flex gap-3">
                  <div className="mt-0.5 text-amber-700">
                    <CircleHelp size={18} />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-amber-950">
                      In-memory demo preview
                    </p>
                    <p className="mt-1 text-xs leading-5 text-amber-900/80">
                      Sample fixture only. No API connection, Azure persistence,
                      or real billing data. This preview resets on page reload.
                    </p>
                  </div>
                </div>
                <span className="shrink-0 rounded-md border border-amber-300 bg-white/70 px-2.5 py-1.5 text-[10px] font-bold uppercase tracking-[0.12em] text-amber-800">
                  Not persisted
                </span>
              </div>
            )}

            {errorMessage && (
              <div
                role="alert"
                className="flex items-start gap-3 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800"
              >
                <AlertCircle size={17} className="mt-0.5 shrink-0" />
                <p>{errorMessage}</p>
              </div>
            )}

            <section className="grid gap-4 sm:grid-cols-2 2xl:grid-cols-5">
              <KpiCard
                label="Total analyzed spend"
                value={
                  currentDashboard
                    ? formatCurrency(
                        currentDashboard.summary.total_cost,
                        currentDashboard.summary.currency,
                      )
                    : "No runs yet"
                }
                meta={
                  currentDashboard
                    ? `${currentDashboard.summary.service_count} services · ${currentDashboard.summary.point_count} daily records`
                    : "Run an analysis to populate this view"
                }
                icon={<Wallet size={18} />}
                accent="teal"
              />
              <KpiCard
                label="Detected anomalies"
                value={String(currentDashboard?.summary.anomaly_count ?? 0)}
                meta={
                  selectedAnomaly
                    ? `${selectedAnomaly.severity} · ${selectedAnomaly.service_name}`
                    : "No anomaly selected"
                }
                icon={<Activity size={18} />}
                accent="amber"
              />
              <KpiCard
                label="Latest variance"
                value={
                  selectedAnomaly
                    ? formatCurrency(
                        selectedAnomaly.delta_amount,
                        selectedAnomaly.currency,
                      )
                    : "—"
                }
                meta={
                  selectedAnomaly?.delta_percentage
                    ? `${selectedAnomaly.delta_percentage}% vs. rolling baseline`
                    : "Dollar and percentage delta"
                }
                icon={<BarChart3 size={18} />}
                accent="blue"
              />
              <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold uppercase tracking-[0.1em] text-slate-500">
                    Grounding check
                  </span>
                  <div className="text-violet-600">
                    <BadgeCheck size={18} />
                  </div>
                </div>
                <div className="mt-4 flex items-end justify-between gap-2">
                  <p className="text-2xl font-semibold tracking-tight text-slate-950">
                    {factCheckPassed ? "Verified" : "Pending"}
                  </p>
                  {templateFallback && (
                    <span className="rounded-md bg-violet-50 px-2 py-1 text-[10px] font-bold uppercase tracking-wide text-violet-700">
                      Template fallback
                    </span>
                  )}
                </div>
                <p className="mt-2 text-xs text-slate-500">
                  {currentDashboard?.fact_check
                    ? `${currentDashboard.fact_check.checked_claims.length} figures checked · ${currentDashboard.fact_check.unsupported_claims.length} unsupported`
                    : "Narrative figures are checked against findings"}
                </p>
              </div>
              <KpiCard
                label="Active data mode"
                value={currentHealth.mode}
                meta={
                  viewMode === "offline-demo"
                    ? "Static in-memory preview"
                    : currentHealth.persistence_mode === "azure"
                      ? "Connected · Azure persistence"
                      : "Connected · memory persistence"
                }
                icon={<Cloud size={18} />}
                accent="blue"
              />
            </section>

            <section className="grid gap-5 2xl:grid-cols-[minmax(0,1.65fr)_minmax(340px,0.85fr)]">
              <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
                <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-5 py-4">
                  <div>
                    <h2 className="text-sm font-semibold text-slate-900">
                      Anomaly &amp; variance inspector
                    </h2>
                    <p className="mt-1 text-xs text-slate-500">
                      Rolling baseline deviations by Azure service
                    </p>
                  </div>
                  <span className="rounded-md bg-slate-100 px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-slate-600">
                    {anomalies.length} findings
                  </span>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[690px] text-left text-xs">
                    <thead className="bg-slate-50 text-[10px] uppercase tracking-[0.12em] text-slate-500">
                      <tr>
                        <th className="px-5 py-3 font-semibold">Service / date</th>
                        <th className="px-4 py-3 font-semibold">Actual</th>
                        <th className="px-4 py-3 font-semibold">Baseline</th>
                        <th className="px-4 py-3 font-semibold">Variance</th>
                        <th className="px-5 py-3 text-right font-semibold">
                          Signal
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {anomalies.map((anomaly) => (
                        <tr
                          key={anomalyKey(anomaly)}
                          onClick={() => setSelectedKey(anomalyKey(anomaly))}
                          className={`cursor-pointer transition hover:bg-slate-50 ${selectedAnomaly && anomalyKey(selectedAnomaly) === anomalyKey(anomaly) ? "bg-teal-50/60" : ""}`}
                        >
                          <td className="px-5 py-4">
                            <p className="font-semibold text-slate-800">
                              {anomaly.service_name}
                            </p>
                            <p className="mt-1 text-[11px] text-slate-400">
                              {formatDate(anomaly.date)}
                            </p>
                          </td>
                          <td className="px-4 py-4 font-medium text-slate-700">
                            {formatCurrency(anomaly.actual_cost, anomaly.currency)}
                          </td>
                          <td className="px-4 py-4 text-slate-500">
                            {formatCurrency(
                              anomaly.baseline_cost,
                              anomaly.currency,
                            )}
                          </td>
                          <td className="px-4 py-4">
                            <Variance anomaly={anomaly} />
                          </td>
                          <td className="px-5 py-4 text-right">
                            <SeverityBadge severity={anomaly.severity} />
                          </td>
                        </tr>
                      ))}
                      {anomalies.length === 0 && (
                        <tr>
                          <td
                            colSpan={5}
                            className="px-5 py-12 text-center text-sm text-slate-500"
                          >
                            No anomalies in the selected run.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="space-y-5">
                <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Sparkles size={16} className="text-violet-600" />
                      <h2 className="text-sm font-semibold text-slate-900">
                        Executive brief
                      </h2>
                    </div>
                    <span
                      className={`inline-flex items-center gap-1 rounded-full px-2 py-1 text-[10px] font-bold uppercase tracking-wide ${factCheckPassed ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-500"}`}
                    >
                      {factCheckPassed ? <Check size={12} /> : <Clock3 size={12} />}
                      {factCheckPassed ? "Fact checked" : "No verified narrative"}
                    </span>
                  </div>
                  <p className="mt-4 text-sm leading-6 text-slate-700">
                    {currentDashboard?.narrative?.text ??
                      "Run an analysis to generate a narrative grounded in deterministic findings."}
                  </p>
                  <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-4 text-[11px] text-slate-500">
                    <span className="rounded bg-slate-100 px-2 py-1 font-medium">
                      {currentDashboard?.narrative?.provider ?? "Awaiting analysis"}
                    </span>
                    <span>
                      {currentDashboard?.narrative
                        ? `Generated ${formatDate(currentDashboard.narrative.generated_at)}`
                        : "Unsupported claims are rejected"}
                    </span>
                  </div>
                </section>

                <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
                  <div className="flex items-center gap-2">
                    <ShieldCheck size={16} className="text-teal-700" />
                    <h2 className="text-sm font-semibold text-slate-900">
                      Suggested review
                    </h2>
                  </div>
                  {selectedAnomaly ? (
                    <>
                      <p className="mt-3 text-xs leading-5 text-slate-600">
                        {getRemediation(selectedAnomaly.service_name)}
                      </p>
                      <div className="mt-4 rounded-lg bg-slate-50 px-3 py-3">
                        <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                          Deterministic signal
                        </p>
                        <div className="mt-2 flex items-center justify-between gap-4 text-xs">
                          <span className="text-slate-500">Z-score</span>
                          <span className="font-mono font-semibold text-slate-800">
                            {selectedAnomaly.z_score ?? "—"}
                          </span>
                        </div>
                        <div className="mt-2 flex items-center justify-between gap-4 text-xs">
                          <span className="text-slate-500">Delta</span>
                          <span className="font-mono font-semibold text-slate-800">
                            {formatCurrency(
                              selectedAnomaly.delta_amount,
                              selectedAnomaly.currency,
                            )}
                            {selectedAnomaly.delta_percentage
                              ? ` · ${selectedAnomaly.delta_percentage}%`
                              : ""}
                          </span>
                        </div>
                      </div>
                    </>
                  ) : (
                    <p className="mt-3 text-xs text-slate-500">
                      Select a finding to view service-specific review guidance.
                    </p>
                  )}
                </section>
              </div>
            </section>

            <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-5 py-4">
                <div>
                  <div className="flex items-center gap-2">
                    <Clock3 size={16} className="text-slate-500" />
                    <h2 className="text-sm font-semibold text-slate-900">
                      Run history
                    </h2>
                  </div>
                  <p className="mt-1 text-xs text-slate-500">
                    Scheduled every six hours · on-demand runs available
                  </p>
                </div>
                <div className="flex items-center gap-2 text-[11px] text-slate-500">
                  <Cloud size={14} />
                  {currentHealth.persistence_mode === "memory"
                    ? "Memory backend"
                    : "Azure persistence"}
                </div>
              </div>
              <div className="divide-y divide-slate-100">
                {runs.map((run) => (
                  <button
                    type="button"
                    key={run.run_id}
                    onClick={() => void openRun(run)}
                    disabled={viewMode !== "live"}
                    className="flex w-full flex-wrap items-center justify-between gap-3 px-5 py-3.5 text-left transition hover:bg-slate-50 disabled:cursor-default"
                  >
                    <div className="flex items-center gap-3">
                      <span className="grid size-8 place-items-center rounded-lg bg-slate-100 text-slate-600">
                        <Activity size={15} />
                      </span>
                      <span>
                        <span className="block text-xs font-semibold text-slate-800">
                          {viewMode === "offline-demo"
                            ? "Offline preview fixture"
                            : `Run ${run.run_id.slice(0, 8)}`}
                        </span>
                        <span className="mt-1 block text-[11px] text-slate-500">
                          {formatDate(run.created_at)} ·{" "}
                          {run.summary.source_mode} mode
                        </span>
                      </span>
                    </div>
                    <span className="flex items-center gap-4 text-xs text-slate-600">
                      <span>
                        {run.anomaly_count} anomalies
                      </span>
                      <span className="font-semibold">
                        {formatCurrency(
                          run.summary.total_cost,
                          run.summary.currency,
                        )}
                      </span>
                      {viewMode === "live" && <ChevronRight size={15} />}
                    </span>
                  </button>
                ))}
                {runs.length === 0 && (
                  <p className="px-5 py-8 text-center text-xs text-slate-500">
                    No stored runs are available yet.
                  </p>
                )}
              </div>
            </section>

            <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
              <div className="flex flex-col justify-between gap-5 xl:flex-row xl:items-center">
                <div>
                  <div className="flex items-center gap-2">
                    <KeyRound size={16} className="text-slate-600" />
                    <h2 className="text-sm font-semibold text-slate-900">
                      Protected API connection
                    </h2>
                  </div>
                  <p className="mt-1.5 max-w-xl text-xs leading-5 text-slate-500">
                    Function key stays only in this tab&apos;s React memory. It
                    is never stored, placed in a URL, or bundled into the app.
                  </p>
                </div>
                <form
                  onSubmit={(event) => void connectToApi(event)}
                  className="flex w-full flex-col gap-2 sm:flex-row xl:max-w-2xl"
                >
                  <label className="sr-only" htmlFor="api-base">
                    API base URL
                  </label>
                  <input
                    id="api-base"
                    value={apiBaseUrl}
                    onChange={(event) => setApiBaseUrl(event.target.value)}
                    autoComplete="url"
                    spellCheck={false}
                    aria-label="API base URL"
                    className="min-w-0 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5 text-xs text-slate-700 outline-none transition focus:border-teal-500 focus:ring-2 focus:ring-teal-100 sm:w-44"
                  />
                  <label className="sr-only" htmlFor="function-key">
                    Azure Function key
                  </label>
                  <input
                    id="function-key"
                    type="password"
                    value={functionKey}
                    onChange={(event) => setFunctionKey(event.target.value)}
                    autoComplete="off"
                    spellCheck={false}
                    aria-label="Azure Function key"
                    placeholder="Paste Function key"
                    className="min-w-0 flex-1 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5 text-xs text-slate-700 outline-none transition placeholder:text-slate-400 focus:border-teal-500 focus:ring-2 focus:ring-teal-100"
                  />
                  <button
                    type="submit"
                    disabled={requestState === "loading" || !functionKey.trim()}
                    className="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg bg-teal-700 px-4 py-2.5 text-xs font-semibold text-white transition hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-45"
                  >
                    <KeyRound size={14} />
                    {liveReady ? "Reconnect" : "Connect"}
                  </button>
                </form>
              </div>
              <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-slate-100 pt-3 text-[10px] text-slate-500">
                <span className="inline-flex items-center gap-1.5">
                  <LockKeyhole size={12} />
                  Session memory only
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <Database size={12} />
                  {currentHealth.persistence_mode === "memory"
                    ? "Runs are not persisted"
                    : "Runs stored in Azure"}
                </span>
                {liveReady && (
                  <span className="inline-flex items-center gap-1.5">
                    <Check size={12} className="text-emerald-600" />
                    Connected · {currentHealth.mode} mode
                  </span>
                )}
              </div>
            </section>

            <footer className="flex flex-wrap items-center justify-between gap-2 pb-2 text-[10px] text-slate-400">
              <span>FinOps Explainer · Deterministic by design</span>
              <span>
                {viewMode === "offline-demo"
                  ? "Offline values are static preview data"
                  : `Correlation ${currentDashboard?.correlation_id ?? currentHealth.correlation_id}`}
              </span>
            </footer>
          </section>
        </div>
      </div>
    </main>
  );
}

function KpiCard({
  label,
  value,
  meta,
  icon,
  accent,
}: {
  label: string;
  value: string;
  meta: string;
  icon: ReactNode;
  accent: "teal" | "amber" | "blue";
}) {
  const colors = {
    teal: "bg-teal-50 text-teal-700",
    amber: "bg-amber-50 text-amber-700",
    blue: "bg-blue-50 text-blue-700",
  };
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-[0.1em] text-slate-500">
          {label}
        </span>
        <span className={`grid size-8 place-items-center rounded-lg ${colors[accent]}`}>
          {icon}
        </span>
      </div>
      <p className="mt-4 truncate text-[26px] font-semibold tracking-tight text-slate-950">
        {value}
      </p>
      <p className="mt-1.5 truncate text-xs text-slate-500">{meta}</p>
    </div>
  );
}

function Variance({ anomaly }: { anomaly: AnomalyFinding }) {
  const isIncrease = anomaly.direction === "increase";
  return (
    <span
      className={`inline-flex flex-col ${isIncrease ? "text-rose-700" : "text-emerald-700"}`}
    >
      <span className="inline-flex items-center gap-1 font-semibold">
        {isIncrease ? (
          <ArrowUpRight size={13} />
        ) : (
          <ArrowDownRight size={13} />
        )}
        {formatCurrency(anomaly.delta_amount, anomaly.currency)}
      </span>
      <span className="mt-1 pl-4 text-[10px]">
        {anomaly.delta_percentage
          ? `${anomaly.delta_percentage}%`
          : "—"}
      </span>
    </span>
  );
}

function SeverityBadge({ severity }: { severity: AnomalyFinding["severity"] }) {
  const severityStyles = {
    low: "bg-sky-50 text-sky-700",
    medium: "bg-amber-50 text-amber-800",
    high: "bg-orange-50 text-orange-800",
    critical: "bg-rose-50 text-rose-700",
  };
  return (
    <span
      className={`rounded-md px-2 py-1 text-[10px] font-bold uppercase tracking-wide ${severityStyles[severity]}`}
    >
      {severity}
    </span>
  );
}

export default App;
