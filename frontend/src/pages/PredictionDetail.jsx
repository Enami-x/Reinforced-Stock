import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Database, CheckCircle, XCircle, ArrowLeft, RefreshCw } from 'lucide-react'
import { fetchPredictionById, resolveOne } from '../lib/api'
import { PageFrame } from '../components/Layout'
import SignalTag from '../components/SignalTag'
import LoadingSpinner from '../components/LoadingSpinner'
import { fmtPrice, fmtPct, fmt, fmtDate, fmtDateShort } from '../lib/utils'

function IndicatorRow({ label, value, even }) {
  return (
    <div style={{
      display: 'flex',
      justifyContent: 'space-between',
      gap: 12,
      padding: '9px 0',
      borderBottom: '1px solid var(--border)',
      fontSize: 12,
      background: even ? 'rgba(0, 0, 0, 0.018)' : 'transparent',
      paddingLeft: even ? 8 : 0,
      paddingRight: even ? 8 : 0,
      borderRadius: even ? 3 : 0,
    }}>
      <dt style={{ color: 'var(--muted-foreground)', fontWeight: 500 }}>{label}</dt>
      <dd style={{ fontFamily: "'Inter', monospace", fontWeight: 700, letterSpacing: '0.02em' }}>{value}</dd>
    </div>
  )
}

export default function PredictionDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const { data, isLoading, error } = useQuery({
    queryKey: ['prediction', id],
    queryFn: () => fetchPredictionById(id),
    enabled: !!id,
  })

  const resolveMutation = useMutation({
    mutationFn: () => resolveOne(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['prediction', id] })
      queryClient.invalidateQueries({ queryKey: ['accuracy'] })
    },
  })

  if (isLoading) return (
    <PageFrame eyebrow="Predictions / …" title="Loading…">
      <div style={{ display: 'flex', justifyContent: 'center', padding: 60 }}><LoadingSpinner size={32} /></div>
    </PageFrame>
  )

  if (error) return (
    <PageFrame eyebrow="Predictions" title="Not found.">
      <div className="glass-card" style={{ padding: 20, color: 'var(--destructive)', fontSize: 13, borderColor: 'oklch(0.65 0.2 18 / 30%)', fontWeight: 500 }}>
        {error.message}
      </div>
    </PageFrame>
  )

  const snap = data?.data_snapshot || {}
  const ind = snap.indicators || {}

  return (
    <PageFrame
      eyebrow={`Predictions / ${data.ticker} / ${id?.slice(0, 8)}…`}
      title="Prediction detail."
      description="A transparent look at what the model saw, why it acted, and the outcome."
    >
      {/* Back button */}
      <button
        onClick={() => navigate(-1)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          fontSize: 12,
          color: 'var(--muted-foreground)',
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          marginBottom: 28,
          padding: 0,
          fontWeight: 600,
          transition: 'color 200ms ease',
        }}
        onMouseEnter={e => e.currentTarget.style.color = 'var(--primary)'}
        onMouseLeave={e => e.currentTarget.style.color = 'var(--muted-foreground)'}
      >
        <ArrowLeft size={13} /> Back
      </button>

      <div style={{ display: 'grid', gridTemplateColumns: '1.3fr 0.7fr', gap: 20, marginBottom: 36 }}>
        {/* Main reasoning card — clean elevated light card */}
        <article style={{
          border: '1px solid var(--border)',
          background: 'var(--card)',
          color: 'var(--foreground)',
          padding: '36px 40px',
          borderRadius: 'var(--radius)',
          position: 'relative',
          overflow: 'hidden',
          boxShadow: '0 1px 3px rgba(0, 0, 0, 0.04), 0 6px 16px -2px rgba(0, 0, 0, 0.03)',
        }}>
          {/* Top accent */}
          <div style={{
            position: 'absolute',
            top: 0, left: 0, right: 0,
            height: 2,
            background: 'linear-gradient(90deg, transparent, var(--primary), transparent)',
          }} />

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <SignalTag signal={data.signal} />
            <span style={{ fontFamily: "'Inter', monospace", fontSize: 11, color: 'var(--muted-foreground)', fontWeight: 500 }}>{id}</span>
          </div>

          <p style={{ marginTop: 28, fontSize: 14, lineHeight: 1.75, color: 'var(--foreground)' }}>{data.reasoning}</p>

          {data.key_factors?.length > 0 && (
            <ul style={{ marginTop: 18, paddingLeft: 18 }}>
              {data.key_factors.map((f, i) => (
                <li key={i} style={{ fontSize: 13, color: 'var(--muted-foreground)', marginBottom: 7, lineHeight: 1.55 }}>{f}</li>
              ))}
            </ul>
          )}

          <div style={{ display: 'flex', gap: 36, marginTop: 28, paddingTop: 24, borderTop: '1px solid var(--border)' }}>
            <div>
              <p style={{ fontSize: 10, fontFamily: "'Inter', monospace", textTransform: 'uppercase', letterSpacing: '0.12em', color: 'var(--muted-foreground)', fontWeight: 600 }}>Confidence</p>
              <p style={{
                marginTop: 6,
                fontSize: 40,
                fontWeight: 700,
                color: 'var(--primary)',
                lineHeight: 1,
                fontFamily: 'Georgia, serif',
              }}>
                {Math.round(data.confidence * 100)}%
              </p>
            </div>
            <div>
              <p style={{ fontSize: 10, fontFamily: "'Inter', monospace", textTransform: 'uppercase', letterSpacing: '0.12em', color: 'var(--muted-foreground)', fontWeight: 600 }}>Horizon</p>
              <p style={{ marginTop: 6, fontFamily: "'Inter', monospace", fontSize: 14, fontWeight: 600 }}>
                {data.resolve_after ? fmtDateShort(data.resolve_after) : '—'}
              </p>
            </div>
            <div>
              <p style={{ fontSize: 10, fontFamily: "'Inter', monospace", textTransform: 'uppercase', letterSpacing: '0.12em', color: 'var(--muted-foreground)', fontWeight: 600 }}>Outcome</p>
              {data.correct == null ? (
                <p style={{ marginTop: 6, fontFamily: "'Inter', monospace", fontSize: 14, color: 'var(--muted-foreground)', fontWeight: 500 }}>Pending</p>
              ) : (
                <div style={{ marginTop: 6, display: 'flex', alignItems: 'center', gap: 6, color: data.correct ? 'var(--primary)' : 'var(--destructive)' }}>
                  {data.correct ? <CheckCircle size={16} /> : <XCircle size={16} />}
                  <span style={{ fontWeight: 700 }}>{data.correct ? 'Correct' : 'Incorrect'}</span>
                  {data.outcome_pct != null && (
                    <span style={{ fontFamily: "'Inter', monospace", fontSize: 13, fontWeight: 600 }}>
                      ({data.outcome_pct > 0 ? '+' : ''}{fmt(data.outcome_pct)}%)
                    </span>
                  )}
                </div>
              )}
            </div>
          </div>
        </article>

        {/* Data snapshot sidebar */}
        <div className="glass-card" style={{ padding: '22px 26px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
            <Database size={14} color="var(--primary)" />
            <h2 style={{ fontSize: 14, fontWeight: 600 }}>At analysis time</h2>
          </div>
          <dl>
            {[
              ['Ticker', data.ticker],
              ['Price', fmtPrice(snap.current_price)],
              ['RSI (14)', fmt(ind.rsi_14)],
              ['MACD', fmt(ind.macd_line)],
              ['Volume ratio', ind.volume_ratio != null ? `${fmt(ind.volume_ratio)}×` : '—'],
              ['SMA 50', fmtPrice(ind.sma_50)],
              ['SMA 200', fmtPrice(ind.sma_200)],
              ['Created', fmtDate(data.created_at)],
              ['Memories used', data.memory_ids_used?.length ?? 0],
            ].map(([label, value], i) => (
              <IndicatorRow key={label} label={label} value={value} even={i % 2 === 1} />
            ))}
          </dl>

          {/* Force resolve */}
          {data.correct == null && (
            <div style={{ marginTop: 22, paddingTop: 18, borderTop: '1px solid var(--border)' }}>
              <button
                onClick={() => resolveMutation.mutate()}
                disabled={resolveMutation.isPending}
                style={{
                  width: '100%',
                  border: '1px solid var(--border)',
                  background: 'transparent',
                  padding: '9px 16px',
                  fontSize: 12,
                  cursor: resolveMutation.isPending ? 'not-allowed' : 'pointer',
                  color: 'var(--foreground)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 6,
                  transition: 'all 220ms cubic-bezier(0.22, 1, 0.36, 1)',
                  opacity: resolveMutation.isPending ? 0.6 : 1,
                  borderRadius: 'var(--radius)',
                  fontWeight: 600,
                }}
                onMouseEnter={e => {
                  if (!resolveMutation.isPending) {
                    e.currentTarget.style.borderColor = 'var(--primary)'
                    e.currentTarget.style.color = 'var(--primary)'
                  }
                }}
                onMouseLeave={e => {
                  e.currentTarget.style.borderColor = 'var(--border)'
                  e.currentTarget.style.color = 'var(--foreground)'
                }}
              >
                <RefreshCw size={12} />
                {resolveMutation.isPending ? 'Resolving…' : 'Force resolve now'}
              </button>
              {resolveMutation.isError && (
                <p style={{ fontSize: 11, color: 'var(--destructive)', marginTop: 8, fontWeight: 500 }}>{resolveMutation.error?.message}</p>
              )}
            </div>
          )}
        </div>
      </div>
    </PageFrame>
  )
}
