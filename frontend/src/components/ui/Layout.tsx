import { NavLink } from 'react-router-dom'
import { LayoutDashboard, Image, PlayCircle, Eye, Activity } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { getHealth } from '@/lib/api'
import clsx from 'clsx'

const NAV = [
  { to:'/dashboard', icon:LayoutDashboard, label:'Dashboard' },
  { to:'/banners',   icon:Image,           label:'Banners' },
  { to:'/runs',      icon:PlayCircle,       label:'Test Runs' },
]

export default function Layout({ children }: { children: React.ReactNode }) {
  const { data: health } = useQuery({ queryKey:['health'], queryFn:getHealth, refetchInterval:30000 })
  const visionOk = health?.vision_api?.includes('connected')

  return (
    <div className="flex h-screen overflow-hidden">
      <aside className="w-56 flex flex-col border-r border-gray-100 bg-white shrink-0">
        <div className="flex items-center gap-2.5 px-5 py-5 border-b border-gray-100">
          <div className="w-7 h-7 rounded-lg bg-brand-600 flex items-center justify-center">
            <Eye size={14} className="text-white" />
          </div>
          <div>
            <p className="font-semibold text-gray-900 text-sm leading-none">BannerMind</p>
            <p className="text-gray-400 text-xs mt-0.5">Vision AI · v7</p>
          </div>
        </div>
        <nav className="flex-1 px-3 py-4 space-y-0.5">
          {NAV.map(({ to, icon: Icon, label }) => (
            <NavLink key={to} to={to} className={({ isActive }) =>
              clsx('flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors',
                isActive ? 'bg-brand-50 text-brand-700' : 'text-gray-600 hover:bg-gray-50')
            }>
              <Icon size={16}/>{label}
            </NavLink>
          ))}
        </nav>
        <div className="px-4 pb-5">
          <div className="flex items-center gap-2 px-3 py-2.5 rounded-lg bg-gray-50 border border-gray-100">
            <Activity size={13} className={visionOk ? 'text-green-500' : 'text-orange-400'} />
            <div>
              <p className="text-xs font-medium text-gray-700">Claude Vision</p>
              <p className="text-xs text-gray-400">{visionOk ? 'connected' : 'checking…'}</p>
            </div>
          </div>
        </div>
      </aside>
      <main className="flex-1 overflow-y-auto bg-gray-50">
        <div className="max-w-6xl mx-auto px-6 py-8">{children}</div>
      </main>
    </div>
  )
}
