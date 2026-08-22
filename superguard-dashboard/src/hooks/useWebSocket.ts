import { useEffect, useRef, useState, useCallback } from 'react';

interface WebSocketMessage {
  type: string;
  payload: any;
  timestamp: string;
}

type MessageHandler = (message: WebSocketMessage) => void;

export function useWebSocket(url: string, handlers: Map<string, MessageHandler> = new Map()) {
  const wsRef = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttempts = useRef(0);
  const maxReconnectAttempts = 10;
  const baseReconnectDelay = 1000;

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
        setError(null);
        reconnectAttempts.current = 0;
        console.log('WebSocket connected');
      };

      ws.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data);
          const handler = handlers.get(message.type);
          if (handler) {
            handler(message);
          }
          // Call generic handlers
          handlers.forEach((h, type) => {
            if (type === '*') h(message);
          });
        } catch (err) {
          console.error('Failed to parse WebSocket message:', err);
        }
      };

      ws.onclose = () => {
        setConnected(false);
        console.log('WebSocket disconnected');
        
        if (reconnectAttempts.current < maxReconnectAttempts) {
          const delay = baseReconnectDelay * Math.pow(2, reconnectAttempts.current);
          reconnectTimeoutRef.current = setTimeout(() => {
            reconnectAttempts.current++;
            connect();
          }, delay);
        } else {
          setError('Max reconnection attempts reached');
        }
      };

      ws.onerror = (err) => {
        setError('WebSocket error');
        console.error('WebSocket error:', err);
      };
    } catch (err) {
      setError('Failed to create WebSocket connection');
    }
  }, [url, handlers]);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setConnected(false);
  }, []);

  const send = useCallback((type: string, payload: any) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type, payload, timestamp: new Date().toISOString() }));
      return true;
    }
    return false;
  }, []);

  useEffect(() => {
    connect();
    return () => disconnect();
  }, [connect, disconnect]);

  return { connected, error, send, disconnect, reconnect: connect };
}

// Specialized hooks for common use cases - matching backend /ws/{site_id} endpoint
export function useSiteWebSocket(siteId: string) {
  const handlers = new Map<string, (msg: any) => void>();
  
  // Backend event types: alarm.triggered, alarm.acknowledged, alarm.resolved
  // camera.status, actuator.status, detection.stats, system.health
  return useWebSocket(`ws://localhost:3001/ws/${siteId}`, handlers);
}

export function useAlarmWebSocket(siteId: string, onAlarm: (alarm: any) => void) {
  const handlers = new Map<string, (msg: any) => void>();
  handlers.set('alarm.triggered', (msg) => onAlarm(msg.payload));
  handlers.set('alarm.acknowledged', (msg) => onAlarm(msg.payload));
  handlers.set('alarm.resolved', (msg) => onAlarm(msg.payload));
  
  return useWebSocket(`ws://localhost:3001/ws/${siteId}`, handlers);
}

export function useCameraWebSocket(siteId: string, onCameraUpdate: (camera: any) => void) {
  const handlers = new Map<string, (msg: any) => void>();
  handlers.set('camera.status', (msg) => onCameraUpdate(msg.payload));
  
  return useWebSocket(`ws://localhost:3001/ws/${siteId}`, handlers);
}

export function useActuatorWebSocket(siteId: string, onActuatorUpdate: (actuator: any) => void) {
  const handlers = new Map<string, (msg: any) => void>();
  handlers.set('actuator.status', (msg) => onActuatorUpdate(msg.payload));
  handlers.set('actuator.command', (msg) => onActuatorUpdate(msg.payload));
  
  return useWebSocket(`ws://localhost:3001/ws/${siteId}`, handlers);
}

export function useDetectionWebSocket(siteId: string, onStats: (stats: any) => void) {
  const handlers = new Map<string, (msg: any) => void>();
  handlers.set('detection.stats', (msg) => onStats(msg.payload));
  
  return useWebSocket(`ws://localhost:3001/ws/${siteId}`, handlers);
}

export function useSystemWebSocket(onHealth: (health: any) => void, onLog: (log: any) => void) {
  const handlers = new Map<string, (msg: any) => void>();
  handlers.set('system.health', (msg) => onHealth(msg.payload));
  handlers.set('system.log', (msg) => onLog(msg.payload));
  
  return useWebSocket(`ws://localhost:8080/ws/system`, handlers);
}