import { useEffect, useRef, useState, useCallback } from 'react';

export type ConnectionState = 'connecting' | 'connected' | 'disconnected';

export interface WsMessage {
  type: string;
  [key: string]: unknown;
}

interface UseWebSocketOptions {
  url: string;
  token?: string;
  onMessage?: (msg: WsMessage) => void;
  reconnectDelay?: number;
  maxReconnectDelay?: number;
}

export function useWebSocket({
  url,
  token,
  onMessage,
  reconnectDelay = 1000,
  maxReconnectDelay = 30000,
}: UseWebSocketOptions) {
  const [state, setState] = useState<ConnectionState>('disconnected');
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const delayRef = useRef(reconnectDelay);
  const onMessageRef = useRef(onMessage);
  const mountedRef = useRef(true);

  // Keep callback ref up to date without triggering reconnect
  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;

    const wsUrl = token ? `${url}?token=${encodeURIComponent(token)}` : url;
    setState('connecting');

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      if (!mountedRef.current) return;
      setState('connected');
      delayRef.current = reconnectDelay; // Reset backoff
    };

    ws.onmessage = (event) => {
      if (!mountedRef.current) return;
      try {
        const data = JSON.parse(event.data) as WsMessage;
        onMessageRef.current?.(data);
      } catch {
        // Ignore non-JSON messages
      }
    };

    ws.onclose = () => {
      if (!mountedRef.current) return;
      setState('disconnected');
      wsRef.current = null;

      // Reconnect with exponential backoff
      reconnectTimer.current = setTimeout(() => {
        delayRef.current = Math.min(delayRef.current * 2, maxReconnectDelay);
        connect();
      }, delayRef.current);
    };

    ws.onerror = () => {
      // onclose will fire after this
    };
  }, [url, token, reconnectDelay, maxReconnectDelay]);

  useEffect(() => {
    mountedRef.current = true;
    connect();

    return () => {
      mountedRef.current = false;
      if (reconnectTimer.current !== null) {
        clearTimeout(reconnectTimer.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  const sendMessage = useCallback((type: string, data?: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type, ...data }));
    }
  }, []);

  return { state, sendMessage };
}
