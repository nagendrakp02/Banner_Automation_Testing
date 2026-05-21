import { ExternalLink, Play, Trash2, Monitor } from 'lucide-react'
import type { Banner } from '@/types'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { deleteBanner } from '@/lib/api'

export function BannerCard({ banner, onRun }: { banner: Banner; onRun: (b: Banner) => void }) {
  const qc = useQueryClient()
  const { mutate: remove } = useMutation({
    mutationFn: () => deleteBanner(banner.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['banners'] }),
  })

  const clientColor: Record<string, string> = {
    'Gilead': 'bg-blue-50 text-blue-700',
    'Bayer':  'bg-orange-50 text-orange-700',
  }
  const clientCls = Object.entries(clientColor).find(([k]) => banner.client?.includes(k))?.[1] ?? 'bg-gray-100 text-gray-600'

  return (
    <div className="card p-4 flex flex-col gap-3 hover:shadow-md transition-shadow">
      <div className="flex items-start gap-3">
        <div className="w-9 h-9 rounded-lg bg-gray-100 flex items-center justify-center shrink-0">
          <Monitor size={16} className="text-gray-500"/>
        </div>
        <div className="min-w-0 flex-1">
          <p className="font-medium text-gray-900 text-sm leading-snug line-clamp-2">{banner.name}</p>
          <div className="flex items-center gap-2 mt-1.5 flex-wrap">
            {banner.client && <span className={`badge ${clientCls}`}>{banner.client}</span>}
            {banner.dimensions && <span className="badge bg-gray-100 text-gray-600">{banner.dimensions}</span>}
            <span className={`badge ${banner.is_active ? 'bg-green-50 text-green-700' : 'bg-gray-100 text-gray-500'}`}>
              {banner.is_active ? 'active' : 'inactive'}
            </span>
          </div>
        </div>
      </div>

      <a href={banner.url} target="_blank" rel="noreferrer"
         className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-brand-600 transition-colors truncate">
        <ExternalLink size={11}/><span className="truncate">{banner.url}</span>
      </a>

      <div className="flex items-center gap-2 pt-1 border-t border-gray-50">
        <button className="btn-primary flex-1 justify-center py-1.5 text-xs" onClick={() => onRun(banner)}>
          <Play size={12}/>Run test
        </button>
        <button className="btn-secondary py-1.5 px-3 text-xs"
                onClick={() => { if (confirm('Delete this banner?')) remove() }}>
          <Trash2 size={12}/>
        </button>
      </div>
    </div>
  )
}
