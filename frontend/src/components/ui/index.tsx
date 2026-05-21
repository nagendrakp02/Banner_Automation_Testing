import { CheckCircle, XCircle, AlertCircle, Clock, Loader, MinusCircle } from 'lucide-react'
import clsx from 'clsx'

type Status = string

const BADGE_CFG: Record<string, { cls: string; Icon: React.ElementType; label: string }> = {
  pass:           { cls:'badge-pass',    Icon:CheckCircle,  label:'Pass' },
  completed:      { cls:'badge-pass',    Icon:CheckCircle,  label:'Completed' },
  fail:           { cls:'badge-fail',    Icon:XCircle,      label:'Fail' },
  failed:         { cls:'badge-fail',    Icon:XCircle,      label:'Failed' },
  error:          { cls:'badge-error',   Icon:AlertCircle,  label:'Error' },
  pending:        { cls:'badge-pending', Icon:Clock,        label:'Pending' },
  running:        { cls:'badge-running', Icon:Loader,       label:'Running' },
  not_applicable: { cls:'badge-not_applicable', Icon:MinusCircle, label:'N/A' },
}

export function StatusBadge({ status }: { status: Status }) {
  const cfg = BADGE_CFG[status] ?? BADGE_CFG.pending
  return (
    <span className={cfg.cls}>
      <cfg.Icon size={11} className={status === 'running' ? 'animate-spin' : ''} />
      {cfg.label}
    </span>
  )
}

export function AgentBadge({ agent }: { agent: string }) {
  const colors: Record<string, string> = {
    render:'bg-blue-50 text-blue-700', visual:'bg-purple-50 text-purple-700',
    isi:'bg-teal-50 text-teal-700', interaction:'bg-amber-50 text-amber-700',
    performance:'bg-green-50 text-green-700',
  }
  return <span className={`badge ${colors[agent] ?? 'bg-gray-100 text-gray-600'} capitalize`}>{agent}</span>
}

export function PageHeader({ title, subtitle, children }: {
  title: string; subtitle?: string; children?: React.ReactNode
}) {
  return (
    <div className="flex items-start justify-between mb-6">
      <div>
        <h1 className="text-xl font-semibold text-gray-900">{title}</h1>
        {subtitle && <p className="text-sm text-gray-500 mt-0.5">{subtitle}</p>}
      </div>
      {children && <div className="flex items-center gap-2">{children}</div>}
    </div>
  )
}

export function Spinner({ size = 20 }: { size?: number }) {
  return <Loader size={size} className="animate-spin text-brand-500" />
}

export function EmptyState({ icon: Icon, title, subtitle }: {
  icon: React.ElementType; title: string; subtitle?: string
}) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="w-12 h-12 rounded-xl bg-gray-100 flex items-center justify-center mb-4">
        <Icon size={22} className="text-gray-400" />
      </div>
      <p className="font-medium text-gray-700">{title}</p>
      {subtitle && <p className="text-sm text-gray-400 mt-1">{subtitle}</p>}
    </div>
  )
}

export function StatCard({ label, value, sub }: { label: string; value: string|number; sub?: string }) {
  return (
    <div className="card px-5 py-4">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className="text-2xl font-semibold text-gray-900">{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
    </div>
  )
}
