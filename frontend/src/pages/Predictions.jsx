import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { CheckCircle, XCircle, Search } from 'lucide-react'
import { fetchPredictions } from '../lib/api'
import { PageFrame } from '../components/Layout'
import SignalTag from '../components/SignalTag'
import LoadingSpinner from '../components/LoadingSpinner'
import { fmtPct, fmtDate, fmt } from '../lib/utils'

function SearchBar({ ticker, setTicker }) {
  const [draft, setDraft] = useState(ticker || '')
  const navigate = useNavigate()

  const go = () => {
    const t = draft.trim().toUpperCase()
    if (t) navigate(`/predictions/${t}`)
  }

  return (
    <div style={{ display: 'flex', gap: 8 }}>
      <input
        value={draft}
        onChange={e => setDraft(e.target.value.toUpperCase())}
        onKeyDown={e => e.key === 'Enter' && go()}
        placeholder="Ticker (e.g. AAPL)"
        style={{
          border: '1px solid var(--border)',
          background: 'var(--input)',
          padding: '9px 14px',
          fontSize: 13,
          fontFamily: "'Inter', monospace",
          fontWeight: 700,
          outline: 'none',
          width: 150,
          color: 'var(--foreground)',
          borderRadius: 'var(--radius)',
          transition: 'all 200ms ease',
          letterSpacing: '0.04em',
        }}
      />
      <button
        onClick={go}
        style={{
          border: 'none',
          background: 'var(--primary)',
          color: 'var(--primary-foreground)',
          padding: '9px 18px',
          cursor: 'pointer',
          fontSize: 13,
          fontWeight: 700,
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          borderRadius: 'var(--radius)',
          transition: 'all 200ms cubic-bezier(0.22, 1, 0.36, 1)',
          boxShadow: '0 2px 10px rgba(180, 120, 22, 0.2)',
        }}
      >
        <Search size={13} /> Search
      </button>
    </div>
  )
}

export default function Predictions() {
  const { ticker } = useParams()
  const navigate = useNavigate()
  const [resolvedOnly, setResolvedOnly] = useState(false)
  const [limit, setLimit] = useState(20)

  const tUpper = ticker?.toUpperCase()

  const { data, isLoading, error } = useQuery({
    queryKey: ['predictions', tUpper, resolvedOnly, limit],
    queryFn: () => fetchPredictions(tUpper, limit, resolvedOnly),
    enabled: !!tUpper,
  })

  return (
    <PageFrame
      eyebrow="Predictions"
      title={tUpper ? `${tUpper} — Signal history.` : 'Search predictions.'}
      description="Browse past AI signals, outcomes, and reasoning for any ticker."
      action={<SearchBar ticker={tUpper} />}
    >
      {!tUpper && (
        <div className="glass-card" style={{ padding: 48, textAlign: 'center', color: 'var(--muted-foreground)' }}>
          <p style={{ fontSize: 14, fontWeight: 500 }}>Enter a ticker symbol above to view its prediction history.</p>
        </div>
      )}

      {tUpper && (
        <>
          {/* Filters */}
          <div style={{ display: 'flex', gap: 16, alignItems: 'center', marginBottom: 18 }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 13, cursor: 'pointer', fontWeight: 500 }}>
              <input
                type="checkbox"
                checked={resolvedOnly}
                onChange={e => setResolvedOnly(e.target.checked)}
                style={{ accentColor: 'var(--primary)' }}
              />
              Resolved only
            </label>
            <select
              value={limit}
              onChange={e => setLimit(Number(e.target.value))}
              style={{
                border: '1px solid var(--border)',
                background: 'var(--input)',
                padding: '5px 10px',
                fontSize: 12,
                color: 'var(--foreground)',
                cursor: 'pointer',
                borderRadius: 'var(--radius)',
                fontWeight: 500,
              }}
            >
              {[10, 20, 50, 100].map(n => <option key={n} value={n}>Last {n}</option>)}
            </select>
          </div>

          {/* Table */}
          {isLoading ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: 60 }}><LoadingSpinner size={32} /></div>
          ) : error ? (
            <div className="glass-card" style={{ padding: 20, color: 'var(--destructive)', fontSize: 13, borderColor: 'oklch(0.65 0.2 18 / 30%)', fontWeight: 500 }}>
              {error.message}
            </div>
          ) : !data?.length ? (
            <div className="glass-card" style={{ padding: 48, textAlign: 'center', color: 'var(--muted-foreground)' }}>
              <p style={{ fontSize: 14, fontWeight: 500 }}>No predictions found for {tUpper}.</p>
            </div>
          ) : (
            <div className="glass-card" style={{ overflow: 'hidden' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Signal</th>
                    <th>Confidence</th>
                    <th>Reasoning</th>
                    <th>Outcome</th>
                    <th>% move</th>
                    <th>Created</th>
                    <th>Resolves</th>
                  </tr>
                </thead>
                <tbody>
                  {data.map(row => (
                    <tr key={row.prediction_id} onClick={() => navigate(`/predictions/${row.prediction_id}`)}>
                      <td><SignalTag signal={row.signal} /></td>
                      <td style={{ fontFamily: "'Inter', monospace", fontWeight: 600 }}>{fmtPct(row.confidence * 100, 0)}</td>
                      <td style={{ maxWidth: 280, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--muted-foreground)', fontSize: 12, fontWeight: 500 }}>
                        {row.reasoning}
                      </td>
                      <td>
                        {row.correct == null ? (
                          <span style={{ color: 'var(--muted-foreground)', fontSize: 12, fontWeight: 500 }}>Pending</span>
                        ) : row.correct ? (
                          <span style={{ color: 'var(--primary)', display: 'flex', alignItems: 'center', gap: 5, fontWeight: 600 }}><CheckCircle size={12} /> Correct</span>
                        ) : (
                          <span style={{ color: 'var(--destructive)', display: 'flex', alignItems: 'center', gap: 5, fontWeight: 600 }}><XCircle size={12} /> Incorrect</span>
                        )}
                      </td>
                      <td style={{ fontFamily: "'Inter', monospace", fontWeight: 600, color: row.outcome_pct > 0 ? 'var(--primary)' : row.outcome_pct < 0 ? 'var(--destructive)' : 'var(--muted-foreground)' }}>
                        {row.outcome_pct != null ? `${row.outcome_pct > 0 ? '+' : ''}${fmt(row.outcome_pct)}%` : '—'}
                      </td>
                      <td style={{ fontSize: 12, color: 'var(--muted-foreground)' }}>{fmtDate(row.created_at)}</td>
                      <td style={{ fontSize: 12, color: 'var(--muted-foreground)' }}>{fmtDate(row.resolve_after)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </PageFrame>
  )
}
