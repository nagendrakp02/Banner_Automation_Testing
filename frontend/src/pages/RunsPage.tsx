import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getRuns, getBanners, deleteRun } from '@/lib/api'
import { PageHeader, Spinner, StatusBadge, EmptyState } from '@/components/ui'
import { formatDistanceToNow } from 'date-fns'
import { useNavigate } from 'react-router-dom'
import { PlayCircle, Trash2 } from 'lucide-react'

export default function RunsPage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { data: runs = [], isLoading } = useQuery({
    queryKey:['runs'], queryFn:() => getRuns(), refetchInterval:4000
  })
  const { data: banners = [] } = useQuery({ queryKey:['banners'], queryFn:getBanners })
  const { mutate: remove } = useMutation({
    mutationFn: deleteRun,
    onSuccess: () => qc.invalidateQueries({ queryKey:['runs'] }),
  })
  const bannerMap = Object.fromEntries(banners.map(b => [b.id, b]))

  return (
    <div>
      <PageHeader title="Test runs" subtitle={`${runs.length} runs total`}/>
      {isLoading ? (
        <div className="flex justify-center py-16"><Spinner/></div>
      ) : runs.length === 0 ? (
        <EmptyState icon={PlayCircle} title="No runs yet" subtitle="Start a test from the Banners page"/>
      ) : (
        <div className="card overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50">
                {['Banner','Status','Pass/Fail','Duration','Created',''].map(h => (
                  <th key={h} className="text-left px-5 py-3 text-xs font-medium text-gray-400">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {runs.map(run => {
                const banner = bannerMap[run.banner_id]
                const dur = run.started_at && run.completed_at
                  ? Math.round((new Date(run.completed_at).getTime()-new Date(run.started_at).getTime())/1000)
                  : null
                return (
                  <tr key={run.id}
                      className="border-b border-gray-50 hover:bg-gray-50 cursor-pointer transition-colors"
                      onClick={() => navigate(`/runs/${run.id}`)}>
                    <td className="px-5 py-3">
                      <p className="font-medium text-gray-800 truncate max-w-xs">
                        {banner?.name ?? 'Unknown'}
                      </p>
                      {banner?.dimensions && <p className="text-xs text-gray-400 mt-0.5">{banner.dimensions}</p>}
                    </td>
                    <td className="px-5 py-3"><StatusBadge status={run.status}/></td>
                    <td className="px-5 py-3">
                      <span className="text-green-600 font-medium">{run.passed_checks}</span>
                      <span className="text-gray-300 mx-1">/</span>
                      <span className="text-red-500">{run.failed_checks + run.error_checks}</span>
                    </td>
                    <td className="px-5 py-3 text-gray-500">
                      {dur != null ? `${dur}s` : run.status==='running' ? 'running…' : '—'}
                    </td>
                    <td className="px-5 py-3 text-gray-400 text-xs">
                      {formatDistanceToNow(new Date(run.created_at),{addSuffix:true})}
                    </td>
                    <td className="px-5 py-3" onClick={e => e.stopPropagation()}>
                      <button className="text-gray-300 hover:text-red-500 transition-colors"
                              onClick={() => { if(confirm('Delete run?')) remove(run.id) }}>
                        <Trash2 size={14}/>
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
