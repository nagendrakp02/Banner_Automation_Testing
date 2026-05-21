import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { X, Play, Eye } from 'lucide-react'
import { createRun, getChecks } from '@/lib/api'
import type { Banner } from '@/types'
import { Spinner } from '@/components/ui'
import { useNavigate } from 'react-router-dom'

const AGENT_COLORS: Record<string, string> = {
  render:'bg-blue-50 text-blue-700 border-blue-100',
  visual:'bg-purple-50 text-purple-700 border-purple-100',
  isi:'bg-teal-50 text-teal-700 border-teal-100',
  interaction:'bg-amber-50 text-amber-700 border-amber-100',
  performance:'bg-green-50 text-green-700 border-green-100',
}

export function RunModal({ banner, onClose }: { banner: Banner; onClose: () => void }) {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { data: checks = [], isLoading } = useQuery({ queryKey:['checks'], queryFn:getChecks })
  const [selected, setSelected] = useState<Set<string>>(new Set())

  if (checks.length > 0 && selected.size === 0 && !isLoading) {
    setSelected(new Set(checks.map(c => c.id)))
  }

  const toggle = (id: string) => setSelected(prev => {
    const next = new Set(prev); next.has(id) ? next.delete(id) : next.add(id); return next
  })

  const { mutate, isPending } = useMutation({
    mutationFn: () => createRun(banner.id, Array.from(selected)),
    onSuccess: (run) => { qc.invalidateQueries({ queryKey:['runs'] }); navigate(`/runs/${run.id}`) },
  })

  return (
    <div className="fixed inset-0 bg-black/30 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="card w-full max-w-lg p-6">
        <div className="flex items-start justify-between mb-5">
          <div>
            <h2 className="font-semibold text-gray-900">Run banner test</h2>
            <p className="text-sm text-gray-500 mt-0.5 truncate max-w-xs">{banner.name}</p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X size={18}/></button>
        </div>

        <div className="flex items-start gap-2.5 bg-brand-50 border border-brand-100 rounded-lg px-3.5 py-3 mb-5">
          <Eye size={15} className="text-brand-600 mt-0.5 shrink-0"/>
          <p className="text-xs text-brand-700 leading-relaxed">
            Each check sends actual screenshots to Claude claude-sonnet-4-20250514 vision — the AI sees what
            a human QA tester sees and reasons accordingly.
          </p>
        </div>

        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-3">Select checks</p>
        {isLoading ? (
          <div className="flex justify-center py-6"><Spinner/></div>
        ) : (
          <div className="space-y-2 mb-6">
            {checks.map(c => (
              <label key={c.id}
                className="flex items-center gap-3 p-3 rounded-lg border border-gray-100 hover:bg-gray-50 cursor-pointer transition-colors">
                <input type="checkbox" checked={selected.has(c.id)} onChange={() => toggle(c.id)}
                  className="accent-brand-600 w-3.5 h-3.5"/>
                <span className="flex-1 text-sm text-gray-800">{c.name}</span>
                <span className={`badge border text-xs ${AGENT_COLORS[c.agent] ?? 'bg-gray-100 text-gray-600'}`}>
                  {c.agent}
                </span>
              </label>
            ))}
          </div>
        )}

        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-400">{selected.size} of {checks.length} selected</span>
          <div className="flex gap-2">
            <button className="btn-secondary" onClick={onClose}>Cancel</button>
            <button className="btn-primary" disabled={selected.size === 0 || isPending} onClick={() => mutate()}>
              {isPending ? <Spinner size={14}/> : <Play size={14}/>}
              Start run
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
