import { useQuery } from '@tanstack/react-query'
import { getBanners, getRuns } from '@/lib/api'
import { StatCard, StatusBadge, PageHeader, Spinner, EmptyState } from '@/components/ui'
import { formatDistanceToNow } from 'date-fns'
import { useNavigate } from 'react-router-dom'
import { Activity, PlayCircle } from 'lucide-react'

export default function DashboardPage() {
  const navigate  = useNavigate()
  const { data: banners = [], isLoading: bl } = useQuery({ queryKey:['banners'], queryFn:getBanners })
  const { data: runs = [], isLoading: rl } = useQuery({
    queryKey:['runs'], queryFn:() => getRuns(), refetchInterval: 5000
  })

  const totalPass = runs.reduce((a,r) => a + r.passed_checks, 0)
  const totalFail = runs.reduce((a,r) => a + r.failed_checks, 0)
  const passRate  = totalPass + totalFail > 0
    ? Math.round((totalPass / (totalPass + totalFail)) * 100) : 0

  return (
    <div>
      <PageHeader title="Dashboard" subtitle="Vision-AI banner testing overview"/>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <StatCard label="Banners"     value={bl ? '—' : banners.length} sub="in registry"/>
        <StatCard label="Total runs"  value={rl ? '—' : runs.length}    sub="all time"/>
        <StatCard label="Pass rate"   value={rl ? '—' : `${passRate}%`}
                  sub={`${totalPass} passed / ${totalFail} failed`}/>
        <StatCard label="Active runs" value={rl ? '—' : runs.filter(r=>r.status==='running').length}
                  sub="in progress"/>
      </div>

      <div className="card">
        <div className="flex items-center gap-2 px-5 py-4 border-b border-gray-100">
          <Activity size={15} className="text-gray-400"/>
          <h2 className="font-medium text-gray-800 text-sm">Recent runs</h2>
        </div>
        {rl ? (
          <div className="flex justify-center py-12"><Spinner/></div>
        ) : runs.length === 0 ? (
          <EmptyState icon={PlayCircle} title="No runs yet" subtitle="Go to Banners to start testing"/>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-50">
                {['Banner','Status','Checks','Duration','Started'].map(h => (
                  <th key={h} className="text-left px-5 py-2.5 text-xs font-medium text-gray-400">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {runs.slice(0,8).map(run => {
                const banner = banners.find(b => b.id === run.banner_id)
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
                    </td>
                    <td className="px-5 py-3"><StatusBadge status={run.status}/></td>
                    <td className="px-5 py-3">
                      <span className="text-green-600 font-medium">{run.passed_checks}</span>
                      <span className="text-gray-300 mx-1">/</span>
                      <span className="text-red-500">{run.failed_checks}</span>
                      <span className="text-gray-400 text-xs ml-1">({run.total_checks})</span>
                    </td>
                    <td className="px-5 py-3 text-gray-500">{dur != null ? `${dur}s` : '—'}</td>
                    <td className="px-5 py-3 text-gray-400 text-xs">
                      {run.created_at ? formatDistanceToNow(new Date(run.created_at),{addSuffix:true}) : '—'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
