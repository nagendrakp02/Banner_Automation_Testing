import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getBanners } from '@/lib/api'
import { PageHeader, Spinner, EmptyState } from '@/components/ui'
import { BannerCard } from '@/components/banners/BannerCard'
import { AddBannerModal } from '@/components/banners/AddBannerModal'
import { RunModal } from '@/components/runs/RunModal'
import type { Banner } from '@/types'
import { Plus, Image, Search } from 'lucide-react'

export default function BannersPage() {
  const { data: banners = [], isLoading } = useQuery({ queryKey:['banners'], queryFn:getBanners })
  const [showAdd, setShowAdd] = useState(false)
  const [runTarget, setRunTarget] = useState<Banner|null>(null)
  const [search, setSearch] = useState('')

  const filtered = banners.filter(b =>
    b.name.toLowerCase().includes(search.toLowerCase()) ||
    b.client?.toLowerCase().includes(search.toLowerCase()) ||
    b.dimensions?.includes(search)
  )

  return (
    <div>
      <PageHeader title="Banner registry" subtitle={`${banners.length} banners configured`}>
        <button className="btn-primary" onClick={() => setShowAdd(true)}>
          <Plus size={14}/>Add banner
        </button>
      </PageHeader>

      <div className="relative mb-6">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"/>
        <input className="input pl-8" placeholder="Search by name, client or dimensions…"
               value={search} onChange={e => setSearch(e.target.value)}/>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-16"><Spinner/></div>
      ) : filtered.length === 0 ? (
        <EmptyState icon={Image} title="No banners found" subtitle="Add banners to start testing"/>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map(b => <BannerCard key={b.id} banner={b} onRun={setRunTarget}/>)}
        </div>
      )}

      {showAdd && <AddBannerModal onClose={() => setShowAdd(false)}/>}
      {runTarget && <RunModal banner={runTarget} onClose={() => setRunTarget(null)}/>}
    </div>
  )
}
