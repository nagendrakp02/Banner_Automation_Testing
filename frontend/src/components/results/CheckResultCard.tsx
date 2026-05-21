import { useState } from 'react'
import { ChevronDown, ChevronUp, Brain, Image, Clock, X, AlertTriangle, CheckCircle, Info, XCircle } from 'lucide-react'
import type { CheckResult } from '@/types'
import { StatusBadge, AgentBadge } from '@/components/ui'
import clsx from 'clsx'

function Lightbox({ src, onClose }: { src: string; onClose: () => void }) {
  return (
    <div className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4"
         onClick={onClose}>
      <button className="absolute top-4 right-4 text-white hover:text-gray-300" onClick={onClose}>
        <X size={24}/>
      </button>
      <img src={src} alt="Evidence screenshot"
           className="max-w-full max-h-full rounded-lg shadow-2xl"
           onClick={e => e.stopPropagation()} />
    </div>
  )
}

/** Extract CONFIDENCE score from LLM reasoning text */
function extractConfidence(text?: string): number | null {
  if (!text) return null
  const m = text.match(/CONFIDENCE\s*:\s*(\d{1,3})/i)
  return m ? Math.min(100, parseInt(m[1])) : null
}

/** Extract a short summary of the verdict from LLM reasoning */
function extractVerdictSummary(reasoning?: string, status?: string): string | null {
  if (!reasoning) return null
  // Find the VERDICT line and a couple lines before it for context
  const lines = reasoning.split('\n').map(l => l.trim()).filter(Boolean)
  const vi = lines.findIndex(l => /^VERDICT\s*:/i.test(l))
  if (vi > 0) {
    // Return the line immediately before the VERDICT as the summary
    const prev = lines[vi - 1]
    if (prev && prev.length < 200 && !prev.startsWith('CONFIDENCE')) return prev
  }
  return null
}

const STATUS_ICON = {
  pass:           <CheckCircle size={15} className="text-green-500 shrink-0"/>,
  fail:           <XCircle     size={15} className="text-red-500 shrink-0"/>,
  error:          <AlertTriangle size={15} className="text-orange-500 shrink-0"/>,
  not_applicable: <Info        size={15} className="text-gray-400 shrink-0"/>,
  pending:        null,
  running:        null,
  skipped:        null,
}

export function CheckResultCard({ result }: { result: CheckResult }) {
  // Auto-expand failures so they're immediately visible
  const [expanded, setExpanded] = useState(result.status === 'fail' || result.status === 'error')
  const [lightbox, setLightbox]  = useState<string|null>(null)

  const screenshotUrl = result.screenshot_path
    ? `/screenshots/${result.screenshot_path.split(/[\\/]/).pop()}`
    : null

  const confidence = extractConfidence(result.llm_reasoning)
  const summary    = extractVerdictSummary(result.llm_reasoning, result.status)

  const borderColor = {
    pass:           'border-green-200',
    fail:           'border-red-300',
    error:          'border-orange-200',
    not_applicable: 'border-gray-200',
  }[result.status] ?? 'border-gray-200'

  const headerBg = {
    pass:           'bg-green-50/40',
    fail:           'bg-red-50/60',
    error:          'bg-orange-50/40',
    not_applicable: 'bg-gray-50',
  }[result.status] ?? 'bg-white'

  const isFail = result.status === 'fail' || result.status === 'error'

  return (
    <>
      {lightbox && <Lightbox src={lightbox} onClose={() => setLightbox(null)}/>}

      <div className={clsx('border-2 rounded-xl overflow-hidden transition-all', borderColor, isFail && 'shadow-sm')}>
        {/* Header */}
        <button
          className={clsx(
            'w-full flex items-center gap-3 px-4 py-3 transition-colors text-left',
            headerBg, 'hover:brightness-95'
          )}
          onClick={() => setExpanded(e => !e)}
        >
          {STATUS_ICON[result.status as keyof typeof STATUS_ICON]}
          <span className={clsx('flex-1 font-semibold text-sm', isFail ? 'text-red-800' : 'text-gray-800')}>
            {result.check_name}
          </span>
          <AgentBadge agent={result.agent_name}/>
          {confidence !== null && (
            <span className={clsx(
              'text-xs font-mono px-1.5 py-0.5 rounded-full',
              confidence >= 90 ? 'bg-gray-100 text-gray-600'
              : confidence >= 70 ? 'bg-yellow-100 text-yellow-700'
              : 'bg-red-100 text-red-700'
            )}>
              {confidence}%
            </span>
          )}
          {result.duration_ms && (
            <span className="flex items-center gap-1 text-xs text-gray-400">
              <Clock size={11}/>{Math.round(result.duration_ms / 1000)}s
            </span>
          )}
          {expanded ? <ChevronUp size={14} className="text-gray-400"/> : <ChevronDown size={14} className="text-gray-400"/>}
        </button>

        {/* Collapsed summary for failures */}
        {!expanded && isFail && summary && (
          <div className="px-4 py-2 bg-red-50 border-t border-red-100">
            <p className="text-xs text-red-700 italic">{summary}</p>
          </div>
        )}

        {expanded && (
          <div className="border-t border-gray-100 bg-gray-50 px-4 py-4 space-y-4">

            {/* Verdict banner for fails */}
            {isFail && (
              <div className="flex items-start gap-2 bg-red-100 border border-red-200 rounded-lg px-3 py-2">
                <XCircle size={14} className="text-red-600 mt-0.5 shrink-0"/>
                <div>
                  <p className="text-xs font-bold text-red-700 uppercase tracking-wide">
                    {result.status === 'error' ? 'Error' : 'Failed Check'}
                  </p>
                  {summary && <p className="text-xs text-red-700 mt-0.5">{summary}</p>}
                </div>
              </div>
            )}

            {/* Evidence Screenshot */}
            {screenshotUrl && (
              <div>
                <p className="flex items-center gap-1.5 text-xs font-medium text-gray-500 mb-2">
                  <Image size={12}/>Evidence screenshot (click to enlarge)
                </p>
                <img
                  src={screenshotUrl}
                  alt="Test evidence"
                  className="rounded-lg border border-gray-200 cursor-zoom-in max-h-48 object-contain bg-white"
                  onClick={() => setLightbox(screenshotUrl)}
                />
              </div>
            )}

            {/* LLM Reasoning */}
            {result.llm_reasoning && (
              <div>
                <p className="flex items-center gap-1.5 text-xs font-medium text-gray-500 mb-2">
                  <Brain size={12}/>Agent reasoning (Claude Vision)
                </p>
                <p className="text-sm text-gray-700 leading-relaxed bg-white border border-gray-100 rounded-lg px-3 py-3 whitespace-pre-wrap">
                  {result.llm_reasoning}
                </p>
              </div>
            )}

            {/* Error */}
            {result.error_message && (
              <div>
                <p className="text-xs font-medium text-red-500 mb-1">Error</p>
                <p className="text-xs font-mono text-red-700 bg-red-50 border border-red-100 rounded-lg px-3 py-2">
                  {result.error_message}
                </p>
              </div>
            )}

            {/* Raw data */}
            {result.raw_data && Object.keys(result.raw_data).length > 0 && (
              <details className="group">
                <summary className="text-xs font-medium text-gray-500 cursor-pointer hover:text-gray-700">
                  Raw DOM evidence ▾
                </summary>
                <pre className="mt-2 text-xs font-mono text-gray-700 bg-white border border-gray-100 rounded-lg px-3 py-3 overflow-x-auto">
                  {JSON.stringify(result.raw_data, null, 2)}
                </pre>
              </details>
            )}
          </div>
        )}
      </div>
    </>
  )
}
