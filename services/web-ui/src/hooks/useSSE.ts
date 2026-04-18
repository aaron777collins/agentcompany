'use client';

/**
 * useSSE — Server-Sent Events hook for the activity feed and real-time updates.
 *
 * EventSource does not support setting request headers, so auth relies on
 * cookies (credentials: 'include' equivalent is automatic for same-origin SSE).
 * For cross-origin, Keycloak token passing via query param is addressed in
 * the security architecture doc.
 *
 * Reconnects automatically on error with exponential backoff (capped at 30s).
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { events as eventsApi } from '@/lib/api';
import type { Event } from '@/lib/types';

interface UseSSEOptions {
  company_id?: string;
  /** Maximum number of events to keep in memory */
  maxEvents?: number;
  enabled?: boolean;
}

interface UseSSEResult {
  events: Event[];
  connected: boolean;
  error: string | null;
  clearEvents: () => void;
}

const DEFAULT_MAX_EVENTS = 100;
const BASE_RECONNECT_MS = 1_000;
const MAX_RECONNECT_MS = 30_000;

export function useSSE(options: UseSSEOptions = {}): UseSSEResult {
  const { company_id, maxEvents = DEFAULT_MAX_EVENTS, enabled = true } = options;

  const [eventList, setEventList] = useState<Event[]>([]);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const esRef = useRef<EventSource | null>(null);
  const reconnectDelayRef = useRef(BASE_RECONNECT_MS);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearEvents = useCallback(() => setEventList([]), []);

  const connect = useCallback(() => {
    if (!enabled) return;

    // Close any existing connection before creating a new one
    esRef.current?.close();

    const url = eventsApi.streamUrl({ company_id });
    const es = new EventSource(url);
    esRef.current = es;

    es.onopen = () => {
      setConnected(true);
      setError(null);
      // Reset backoff on successful connection
      reconnectDelayRef.current = BASE_RECONNECT_MS;
    };

    es.onmessage = (messageEvent) => {
      try {
        const parsed = JSON.parse(messageEvent.data) as Event;
        setEventList((prev) => {
          const next = [parsed, ...prev];
          // Trim to maxEvents to prevent unbounded memory growth
          return next.length > maxEvents ? next.slice(0, maxEvents) : next;
        });
      } catch {
        // Malformed SSE data — skip silently, don't crash the feed
      }
    };

    es.onerror = () => {
      setConnected(false);
      es.close();

      const delay = reconnectDelayRef.current;
      setError(`Reconnecting in ${Math.round(delay / 1000)}s…`);

      reconnectTimerRef.current = setTimeout(() => {
        // Exponential backoff capped at MAX_RECONNECT_MS
        reconnectDelayRef.current = Math.min(delay * 2, MAX_RECONNECT_MS);
        connect();
      }, delay);
    };
  }, [enabled, company_id, maxEvents]);

  useEffect(() => {
    connect();

    return () => {
      // Cleanup on unmount or when deps change
      esRef.current?.close();
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
      }
    };
  }, [connect]);

  return { events: eventList, connected, error, clearEvents };
}
