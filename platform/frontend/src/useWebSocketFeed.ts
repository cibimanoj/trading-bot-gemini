import { useEffect, useState } from "react";

type Validated = {
  suggestion: {
    symbol: string;
    action: string;
    confidence: number;
    regime?: string;
    regimeConfidence?: number;
    strategyId?: string;
    confirmationScore?: number;
    confirmationFactors?: string[];
    allocationMultiplier?: number;
    reason?: string[];
  };
  risk: {
    approved: boolean;
    riskRewardRatio: number;
    positionSizeUnits: number;
    maxLossAmount: number;
    effectiveRiskPct?: number;
    rejectReasons?: string[];
  };
  validatedAt: number;
};

type OptionsIntel = {
  symbol: string;
  pcr: number;
  totalCeOi: number;
  totalPeOi: number;
  oiBuildupNotes: string[];
  computedAt: number;
};

export function useWebSocketFeed(
  token: string | null,
  onLog: (s: string) => void,
): {
  signals: Validated[];
  options: OptionsIntel[];
  last: { channel: string } | null;
  wsConnected: boolean;
} {
  const [signals, setSignals] = useState<Validated[]>([]);
  const [options, setOptions] = useState<OptionsIntel[]>([]);
  const [last, setLast] = useState<{ channel: string } | null>(null);
  const [wsConnected, setWsConnected] = useState(false);

  useEffect(() => {
    if (!token) return;

    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = import.meta.env.VITE_WS_HOST ?? `${window.location.hostname}:3010`;
    const url = `${proto}//${host}/stream?token=${encodeURIComponent(token)}`;

    let ws: WebSocket | null = null;
    let reconnect: number | undefined;
    let intentionalClose = false;

    const connect = () => {
      ws = new WebSocket(url);
      ws.onopen = () => {
        setWsConnected(true);
        onLog("websocket connected");
      };
      ws.onclose = () => {
        setWsConnected(false);
        if (intentionalClose) return;
        onLog("websocket disconnected — reconnecting");
        reconnect = window.setTimeout(connect, 3000);
      };
      ws.onerror = () => onLog("websocket error");
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data as string) as {
            channel: string;
            data: unknown;
          };
          setLast({ channel: msg.channel });
          if (msg.channel === "signals:validated" && msg.data && typeof msg.data === "object") {
            const d = msg.data as { suggestion?: unknown; risk?: unknown; validatedAt?: number };
            if (d.suggestion && d.risk && d.validatedAt) {
              setSignals((prev) => [msg.data as Validated, ...prev].slice(0, 50));
            }
          }
          if (msg.channel === "options:intelligence") {
            setOptions((prev) => [msg.data as OptionsIntel, ...prev].slice(0, 20));
          }
        } catch {
          onLog("non-json ws message");
        }
      };
    };

    connect();

    return () => {
      intentionalClose = true;
      if (reconnect) window.clearTimeout(reconnect);
      ws?.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- stable log sink
  }, [token]);

  return { signals, options, last, wsConnected };
}
