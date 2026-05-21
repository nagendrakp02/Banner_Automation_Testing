import { useEffect, useRef } from 'react'
import { Terminal } from 'lucide-react'
import type { LogEntry } from '@/types'
import { format } from 'date-fns'

export function LogTerminal({ logs, title='Live log' }: { logs: LogEntry[]; title?: string }) {
  const endRef = useRef<HTMLDivElement>(null)
  useEffect(() => { endRef.current?.scrollIntoView({ behavior:'smooth' }) }, [logs.length])

  return (
    <div className="card overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-100">
        <Terminal size={14} className="text-gray-400"/>
        <span className="text-sm font-medium text-gray-700">{title}</span>
        <span className="ml-auto text-xs text-gray-400">{logs.length} lines</span>
      </div>
      <div className="log-terminal">
        {logs.length === 0 && <span className="text-gray-600">Waiting for agent output…</span>}
        {logs.map((log, i) => (
          <div key={i} className={`flex gap-3 mb-0.5 log-${log.level}`}>
            <span className="text-gray-600 shrink-0 select-none">
              {format(new Date(log.timestamp), 'HH:mm:ss')}
            </span>
            {log.agent && <span className="text-brand-400 shrink-0 w-20 truncate">[{log.agent}]</span>}
            <span className="break-all">{log.message}</span>
          </div>
        ))}
        <div ref={endRef}/>
      </div>
    </div>
  )
}
