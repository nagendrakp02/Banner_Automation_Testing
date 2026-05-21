import { useEffect, useRef, useState } from 'react'
import type { LogEntry } from '@/types'

export function useRunLogs(runId: string | null) {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    if (!runId) return
    setLogs([])
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${window.location.host}/ws/runs/${runId}`)
    wsRef.current = ws
    ws.onmessage = (e) => {
      try {
        const entry: LogEntry = JSON.parse(e.data)
        setLogs(prev => [...prev.slice(-500), entry])
      } catch {}
    }
    ws.onclose = () => { wsRef.current = null }
    const ping = setInterval(() => { if (ws.readyState === WebSocket.OPEN) ws.send('ping') }, 20000)
    return () => { clearInterval(ping); ws.close() }
  }, [runId])

  return logs
}
