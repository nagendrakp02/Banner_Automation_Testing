import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { getRun, getBanners } from '@/lib/api'
import { StatusBadge, PageHeader, Spinner } from '@/components/ui'
import { LogTerminal } from '@/components/runs/LogTerminal'
import { CheckResultCard } from '@/components/results/CheckResultCard'
import { useRunLogs } from '@/hooks/useRunLogs'
import { formatDistanceToNow, format } from 'date-fns'
import { ArrowLeft, Brain, ExternalLink, Eye } from 'lucide-react'

export default function RunDetailPage() {
  const { runId } = useParams<{ runId: string }>()
  const navigate   = useNavigate()
  const logs       = useRunLogs(runId ?? null)

  const { data: run, isLoading } = useQuery({
    queryKey:['run', runId],
    queryFn: () => getRun(runId!),
    refetchInterval: q =>
      q.state.data?.status === 'running' || q.state.data?.status === 'pending' ? 2500 : false,
    enabled: !!runId,
  })

  const { data: banners = [] } = useQuery({ queryKey:['banners'], queryFn:getBanners })
  const banner = banners.find(b => b.id === run?.banner_id)

  if (isLoading) return <div className="flex justify-center py-20"><Spinner/></div>
  if (!run) return <div className="text-center py-20 text-gray-500">Run not found</div>

  const dur = run.started_at && run.completed_at
    ? Math.round((new Date(run.completed_at).getTime()-new Date(run.started_at).getTime())/1000)
    : null

  const total    = run.total_checks || 1
  const passW    = Math.round((run.passed_checks / total) * 100)
  const failW    = Math.round(((run.failed_checks + run.error_checks) / total) * 100)

  return (
    <div>
      <button className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-800 mb-5 transition-colors"
              onClick={() => navigate(-1)}>
        <ArrowLeft size={14}/>Back
      </button>

      <PageHeader
        title={banner?.name ?? 'Test run'}
        subtitle={banner?.dimensions ? `${banner.dimensions} · ${banner.client ?? ''}` : undefined}
      >
        <StatusBadge status={run.status}/>
      </PageHeader>

      {/* Meta */}
      <div className="flex flex-wrap gap-4 text-sm text-gray-500 mb-6">
        {run.started_at && (
          <span>Started: <span className="text-gray-700">{format(new Date(run.started_at),'MMM d, HH:mm:ss')}</span></span>
        )}
        {dur != null && <span>Duration: <span className="text-gray-700">{dur}s</span></span>}
        <span className="flex items-center gap-1">
          <Eye size={12} className="text-brand-500"/>
          <span className="text-gray-700">Ollama model - qwen2.5:7b</span>
        </span>
        {banner && (
          <a href={banner.url} target="_blank" rel="noreferrer"
             className="flex items-center gap-1 text-brand-600 hover:underline">
            <ExternalLink size={11}/>View banner
          </a>
        )}
      </div>

      {/* Progress bar */}
      <div className="card px-5 py-4 mb-6">
        <div className="flex items-center justify-between mb-3 text-sm">
          <span className="font-medium text-gray-700">
            {run.passed_checks} passed · {run.failed_checks} failed · {run.error_checks} errors
          </span>
          <span className="text-gray-400 text-xs">{run.total_checks} checks</span>
        </div>
        <div className="flex h-2 rounded-full overflow-hidden bg-gray-100 gap-0.5">
          {passW > 0 && <div className="bg-green-400 transition-all" style={{width:`${passW}%`}}/>}
          {failW > 0 && <div className="bg-red-400 transition-all" style={{width:`${failW}%`}}/>}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left: live log + plan */}
        <div className="space-y-4">
          <LogTerminal logs={logs} title="Live agent log"/>
          {run.orchestrator_reasoning && (
            <div className="card p-4">
              <p className="flex items-center gap-1.5 text-xs font-medium text-gray-500 mb-2">
                <Brain size={12}/>Orchestrator plan
              </p>
              <p className="text-sm text-gray-700 leading-relaxed">{run.orchestrator_reasoning}</p>
            </div>
          )}
        </div>

        {/* Right: check results */}
        <div className="space-y-2">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-3">
            Check results
          </p>
          {run.check_results.length === 0 ? (
            <div className="flex flex-col items-center py-10 text-center text-gray-400">
              <Spinner/><p className="mt-3 text-sm">Agents running…</p>
            </div>
          ) : (
            run.check_results
              .sort((a,b) => {
                const o = ['fail','error','pass','not_applicable','pending']
                return o.indexOf(a.status) - o.indexOf(b.status)
              })
              .map(cr => <CheckResultCard key={cr.id} result={cr}/>)
          )}
        </div>
      </div>
    </div>
  )
}
