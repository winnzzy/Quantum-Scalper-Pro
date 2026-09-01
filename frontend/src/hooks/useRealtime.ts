import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from 'react-query';

import { useAuthStore } from '../store/authStore';
import { RealtimeSnapshot } from '../types/api';


const WS_URL = process.env.REACT_APP_WS_URL || 'ws://localhost:8000/ws';
const MAX_BACKOFF_MS = 30_000;

export const useRealtime = () => {
  const token = useAuthStore((state) => state.token);
  const queryClient = useQueryClient();
  const reconnectAttempt = useRef(0);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const socket = useRef<WebSocket | null>(null);
  const [isConnected, setConnected] = useState(false);

  useEffect(() => {
    let disposed = false;

    const connect = () => {
      if (disposed || !token) return;

      const url = new URL(WS_URL);
      url.searchParams.set('token', token);
      const ws = new WebSocket(url.toString());
      socket.current = ws;

      ws.onopen = () => {
        reconnectAttempt.current = 0;
        setConnected(true);
      };

      ws.onmessage = (event) => {
        let message: RealtimeSnapshot;
        try {
          message = JSON.parse(event.data);
        } catch {
          return;
        }
        if (message.type !== 'snapshot') return;

        queryClient.setQueryData('positions', { data: message.positions });
        queryClient.setQueryData('trades', { data: message.trades });
        queryClient.setQueryData('notifications', { data: message.notifications });
      };

      ws.onclose = () => {
        setConnected(false);
        if (disposed) return;
        const delay = Math.min(1000 * 2 ** reconnectAttempt.current, MAX_BACKOFF_MS);
        reconnectAttempt.current += 1;
        reconnectTimer.current = setTimeout(connect, delay);
      };

      ws.onerror = () => ws.close();
    };

    connect();

    return () => {
      disposed = true;
      setConnected(false);
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      socket.current?.close();
      socket.current = null;
    };
  }, [queryClient, token]);

  return { isConnected };
};
