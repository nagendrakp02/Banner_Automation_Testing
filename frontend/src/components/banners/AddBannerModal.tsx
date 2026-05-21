import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { X, Plus } from 'lucide-react'
import { createBanner } from '@/lib/api'
import { Spinner } from '@/components/ui'

export function AddBannerModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient()
  const [form, setForm] = useState({ url_id:'', name:'', url:'', client:'', dimensions:'' })
  const { mutate, isPending, error } = useMutation({
    mutationFn: () => createBanner(form),
    onSuccess: () => { qc.invalidateQueries({ queryKey:['banners'] }); onClose() },
  })
  const f = (key: keyof typeof form, label: string, placeholder: string, required = false) => (
    <div>
      <label className="block text-xs font-medium text-gray-600 mb-1.5">
        {label}{required && <span className="text-red-500 ml-0.5">*</span>}
      </label>
      <input className="input" placeholder={placeholder} value={form[key]}
             onChange={e => setForm(p => ({...p, [key]: e.target.value}))} required={required}/>
    </div>
  )
  return (
    <div className="fixed inset-0 bg-black/30 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="card w-full max-w-md p-6">
        <div className="flex items-center justify-between mb-5">
          <h2 className="font-semibold text-gray-900">Add banner</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X size={18}/></button>
        </div>
        <div className="space-y-4 mb-6">
          {f('url_id','URL ID','e.g. 10',true)}
          {f('name','Name','e.g. Gilead · CFF 300x250',true)}
          {f('url','URL','https://…/index.html',true)}
          {f('client','Client','e.g. Gilead')}
          {f('dimensions','Dimensions','e.g. 300x250')}
        </div>
        {error && (
          <p className="text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2 mb-4">
            {(error as any)?.response?.data?.detail ?? 'Something went wrong'}
          </p>
        )}
        <div className="flex gap-2 justify-end">
          <button className="btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn-primary" disabled={!form.url_id||!form.name||!form.url||isPending}
                  onClick={() => mutate()}>
            {isPending ? <Spinner size={14}/> : <Plus size={14}/>}Add banner
          </button>
        </div>
      </div>
    </div>
  )
}
