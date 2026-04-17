import { useEffect, useMemo, useRef, useState } from "react";
import { createChart, ColorType } from "lightweight-charts";
import { useWebSocketFeed } from "./useWebSocketFeed.js";

type LogEntry = { t: number; text: string };

function formatNum(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toFixed(0);
}

export interface DashboardProps {
  token: string;
  onLogout: () => void;
}

export function Dashboard({ token, onLogout }: DashboardProps) {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [watchQuery, setWatchQuery] = useState("");
  const chartRef = useRef<HTMLDivElement>(null);

  const pushLog = (text: string) => {
    setLogs((prev) => [{ t: Date.now(), text }, ...prev].slice(0, 200));
  };

  const { signals, options, last, wsConnected } = useWebSocketFeed(token, pushLog);

  useEffect(() => {
    if (!chartRef.current) return;
    const chart = createChart(chartRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#94a3b8",
        fontFamily: "'JetBrains Mono', ui-monospace, monospace",
      },
      grid: {
        vertLines: { color: "rgba(51, 65, 85, 0.35)" },
        horzLines: { color: "rgba(51, 65, 85, 0.35)" },
      },
      rightPriceScale: { borderColor: "rgba(51, 65, 85, 0.5)" },
      timeScale: { borderColor: "rgba(51, 65, 85, 0.5)" },
      crosshair: {
        vertLine: { color: "rgba(45, 212, 191, 0.35)", width: 1 },
        horzLine: { color: "rgba(45, 212, 191, 0.35)", width: 1 },
      },
      width: chartRef.current.clientWidth,
      height: chartRef.current.clientHeight,
    });

    const series = chart.addCandlestickSeries({
      upColor: "#2dd4bf",
      downColor: "#f87171",
      borderVisible: false,
      wickUpColor: "#2dd4bf",
      wickDownColor: "#f87171",
    });

    const seed = Array.from({ length: 120 }).map((_, i) => {
      const t = Math.floor(Date.now() / 1000) - (120 - i) * 60;
      const o = 100 + Math.sin(i / 7) * 3;
      const c = o + (Math.random() - 0.45) * 1.2;
      const h = Math.max(o, c) + Math.random() * 0.4;
      const l = Math.min(o, c) - Math.random() * 0.4;
      return { time: t as import("lightweight-charts").Time, open: o, high: h, low: l, close: c };
    });
    series.setData(seed);

    const ro = new ResizeObserver(() => {
      if (!chartRef.current) return;
      chart.applyOptions({ width: chartRef.current.clientWidth, height: chartRef.current.clientHeight });
    });
    ro.observe(chartRef.current);

    return () => {
      ro.disconnect();
      chart.remove();
    };
  }, []);

  const watchlist = useMemo(
    () => ["NIFTY", "BANKNIFTY", "FINNIFTY", "RELIANCE", "TCS"],
    [],
  );

  const filteredWatch = useMemo(() => {
    const q = watchQuery.trim().toUpperCase();
    if (!q) return watchlist;
    return watchlist.filter((s) => s.includes(q));
  }, [watchlist, watchQuery]);

  const streamLabel = last?.channel?.replace(":", " · ") ?? "—";

  return (
    <div className="app">
      <header className="top-bar">
        <div className="brand">
          <span className="brand-mark" aria-hidden />
          <div>
            <div className="brand-name">Trading Assistant</div>
            <div className="brand-tag">Signals · Risk · Options intel</div>
          </div>
        </div>
        <div className="top-bar__meta">
          <div className={`status-pill ${token ? "status-pill--ok" : ""}`}>
            <span className="status-dot" data-live={Boolean(token && wsConnected)} />
            {wsConnected ? "Stream live" : "Reconnecting…"}
          </div>
          <div className="meta-chip" title="Last websocket channel">
            <span className="meta-chip__k">Feed</span>
            <span className="meta-chip__v">{streamLabel}</span>
          </div>
          <button type="button" className="btn btn--signout" onClick={onLogout}>
            Sign out
          </button>
        </div>
      </header>

      <div className="layout">
        <aside className="panel panel--sidebar watch">
          <div className="section-head">
            <h2 className="section-title">Watchlist</h2>
            <p className="section-desc">Symbols you track. Wire selection to your data feed.</p>
          </div>
          <input
            className="search-input search-input--flush"
            value={watchQuery}
            onChange={(e) => setWatchQuery(e.target.value)}
            placeholder="Filter symbols…"
            aria-label="Filter watchlist"
          />
          <ul className="watchlist">
            {filteredWatch.map((s) => (
              <li key={s}>
                <span className="sym">{s}</span>
                <span className="sym-hint">Index</span>
              </li>
            ))}
          </ul>
          {filteredWatch.length === 0 && (
            <p className="empty-hint">No symbols match your filter.</p>
          )}
        </aside>

        <section className="panel panel--chart chart">
          <div className="chart-head">
            <div>
              <h2 className="section-title section-title--lg">Price</h2>
              <p className="section-desc">Candle preview · connect data feed for live series</p>
            </div>
            <div className="chart-badges">
              <span className="pill">1m</span>
              <span className="pill pill--muted">Demo seed</span>
            </div>
          </div>
          <div className="chart-surface">
            <div className="chart-container" ref={chartRef} />
          </div>
        </section>

        <aside className="panel panel--scroll signals">
          <div className="section-head">
            <h2 className="section-title">Signals &amp; risk</h2>
            <p className="section-desc">Validated events from the risk engine.</p>
          </div>
          <div className="signal-list">
            {signals.slice(0, 14).map((s, i) => (
              <article
                key={`${s.validatedAt}-${i}`}
                className={`signal-card ${s.risk.approved ? "signal-card--ok" : "signal-card--reject"}`}
              >
                <div className="signal-card__top">
                  <div>
                    <div className="signal-card__symbol">{s.suggestion.symbol}</div>
                    {(s.suggestion.regime || s.suggestion.strategyId) && (
                      <div className="signal-card__tags">
                        {s.suggestion.regime && (
                          <span className="tag">{s.suggestion.regime.replace(/_/g, " ")}</span>
                        )}
                        {s.suggestion.strategyId && (
                          <span className="tag tag--accent">{s.suggestion.strategyId.replace(/_/g, " ")}</span>
                        )}
                      </div>
                    )}
                  </div>
                  <span
                    className={`badge ${s.suggestion.action === "BUY" ? "badge--buy" : "badge--sell"}`}
                  >
                    {s.suggestion.action}
                  </span>
                </div>
                <div className="signal-card__meta">
                  <span>Conf {s.suggestion.confidence}%</span>
                  <span className="dot-sep" />
                  <span>RR {s.risk.riskRewardRatio}</span>
                  {s.suggestion.confirmationScore != null && (
                    <>
                      <span className="dot-sep" />
                      <span>Confirm {s.suggestion.confirmationScore}</span>
                    </>
                  )}
                  {s.suggestion.allocationMultiplier != null && (
                    <>
                      <span className="dot-sep" />
                      <span>Alloc ×{s.suggestion.allocationMultiplier.toFixed(2)}</span>
                    </>
                  )}
                </div>
                <div className="risk-metrics">
                  <div className="risk-metrics__cell">
                    <span className="risk-metrics__k">Size</span>
                    <span className="risk-metrics__v">{s.risk.positionSizeUnits} u</span>
                  </div>
                  <div className="risk-metrics__cell">
                    <span className="risk-metrics__k">Max loss</span>
                    <span className="risk-metrics__v mono">{s.risk.maxLossAmount.toFixed(0)}</span>
                  </div>
                  <div className="risk-metrics__cell risk-metrics__cell--full">
                    <span className="risk-metrics__k">Approved</span>
                    <span
                      className={`risk-metrics__v ${s.risk.approved ? "text-ok" : "text-warn"}`}
                    >
                      {s.risk.approved ? "Yes" : "No"}
                    </span>
                  </div>
                </div>
                {!s.risk.approved && s.risk.rejectReasons && s.risk.rejectReasons.length > 0 && (
                  <div className="reject-box">
                    {s.risk.rejectReasons.map((r) => (
                      <div key={r} className="reject-line">
                        {r}
                      </div>
                    ))}
                  </div>
                )}
                {s.suggestion.reason && s.suggestion.reason.length > 0 && (
                  <div className="reason-lines">
                    {s.suggestion.reason.slice(0, 3).map((line, ri) => (
                      <span key={`${line}-${ri}`} className="reason-chip">
                        {line}
                      </span>
                    ))}
                  </div>
                )}
              </article>
            ))}
          </div>
          {signals.length === 0 && (
            <div className="empty-state">
              <div className="empty-state__icon" aria-hidden />
              <p className="empty-state__title">Waiting for stream</p>
              <p className="empty-state__text">Ensure the alert websocket service is running.</p>
            </div>
          )}

          <div className="section-head section-head--divider">
            <h2 className="section-title">Options intelligence</h2>
            <p className="section-desc">PCR and OI context from the chain analyzer.</p>
          </div>
          <div className="options-list">
            {options.slice(0, 4).map((o) => {
              const pcrPct = Math.min(100, Math.max(0, (o.pcr / 2) * 100));
              return (
                <div key={`${o.symbol}-${o.computedAt}`} className="options-card">
                  <div className="options-card__head">
                    <span className="options-card__sym">{o.symbol}</span>
                    <span className="options-card__time mono">
                      {new Date(o.computedAt).toLocaleTimeString()}
                    </span>
                  </div>
                  <div className="pcr-row">
                    <span className="pcr-label">PCR</span>
                    <div className="pcr-bar" title={`PCR ${o.pcr}`}>
                      <div className="pcr-bar__fill" style={{ width: `${pcrPct}%` }} />
                    </div>
                    <span className="pcr-val mono">{o.pcr.toFixed(2)}</span>
                  </div>
                  <div className="oi-row mono">
                    <span>CE OI {formatNum(o.totalCeOi)}</span>
                    <span className="dot-sep" />
                    <span>PE OI {formatNum(o.totalPeOi)}</span>
                  </div>
                  {o.oiBuildupNotes.length > 0 && (
                    <p className="options-notes">{o.oiBuildupNotes.join(" · ")}</p>
                  )}
                </div>
              );
            })}
          </div>
          {options.length === 0 && (
            <p className="empty-hint">No options snapshots yet.</p>
          )}
        </aside>

        <footer className="panel panel--logs logs">
          <div className="logs-head">
            <h2 className="section-title">System logs</h2>
            <span className="logs-head__hint mono">{logs.length} lines</span>
          </div>
          <div className="logs-scroll">
            {last && (
              <div className="log-line log-line--accent">
                <span className="mono log-ts">{new Date().toLocaleTimeString()}</span>
                <span>Last channel: {last.channel}</span>
              </div>
            )}
            {logs.map((l) => (
              <div key={l.t} className="log-line">
                <span className="mono log-ts">{new Date(l.t).toLocaleTimeString()}</span>
                <span>{l.text}</span>
              </div>
            ))}
            {logs.length === 0 && <div className="log-line log-line--muted">No log lines yet.</div>}
          </div>
        </footer>
      </div>
    </div>
  );
}
