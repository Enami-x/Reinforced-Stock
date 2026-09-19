import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { TrendingUp, Newspaper, Zap, Database } from 'lucide-react'
import { fetchSnapshot, fetchPredictions, fetchTickerAccuracy, analyzeTicker } from '../lib/api'
import { PageFrame } from '../components/Layout'
import SignalTag from '../components/SignalTag'
import LoadingSpinner from '../components/LoadingSpinner'
import { fmtPrice, fmtPct, fmt, fmtDate, fmtDateShort } from '../lib/utils'
import { useNavigate } from 'react-router-dom'

function IndicatorRow({ label, value, even }) {
  return (
    <div style={{
      display: 'flex',
      justifyContent: 'space-between',
      gap: 12,
      padding: '10px 0',
      borderBottom: '1px solid var(--border)',
      fontSize: 13,
      background: even ? 'rgba(0, 0, 0, 0.018)' : 'transparent',
      paddingLeft: even ? 8 : 0,
      paddingRight: even ? 8 : 0,
      borderRadius: even ? 3 : 0,
    }}>
      <dt style={{ color: 'var(--muted-foreground)', fontWeight: 500 }}>{label}</dt>
      <dd style={{ fontFamily: "'Inter', monospace", fontWeight: 700, textAlign: 'right', letterSpacing: '0.02em' }}>{value}</dd>
    </div>
  )
}

function AnalyzeButton({ ticker }) {
  const queryClient = useQueryClient()
  const [result, setResult] = useState(null)

  const mutation = useMutation({
    mutationFn: () => analyzeTicker(ticker),
    onSuccess: (data) => {
      setResult(data)
      // Invalidate predictions + accuracy so they refetch with new data
      queryClient.invalidateQueries({ queryKey: ['predictions', ticker] })
      queryClient.invalidateQueries({ queryKey: ['accuracy', ticker] })
      queryClient.invalidateQueries({ queryKey: ['accuracy'] })
    },
  })

  return (
    <div>
      <button
        onClick={() => mutation.mutate()}
        disabled={mutation.isPending}
        style={{
          background: 'var(--primary)',
          color: 'var(--primary-foreground)',
          border: 'none',
          padding: '10px 24px',
          fontSize: 13,
          fontWeight: 700,
          cursor: mutation.isPending ? 'not-allowed' : 'pointer',
          opacity: mutation.isPending ? 0.7 : 1,
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          transition: 'all 220ms cubic-bezier(0.22, 1, 0.36, 1)',
          borderRadius: 'var(--radius)',
          boxShadow: '0 2px 10px rgba(180, 120, 22, 0.2)',
        }}
      >
        {mutation.isPending ? <><LoadingSpinner size={14} /> Analyzing…</> : <><Zap size={14} /> Run Analysis</>}
      </button>

      {mutation.isError && (
        <p style={{ fontSize: 12, color: 'var(--destructive)', marginTop: 8, fontWeight: 500 }}>
          Error: {mutation.error?.message}
        </p>
      )}

      {result && (
        <div className="glass-card" style={{
          marginTop: 16,
          padding: 20,
          animation: 'fadeSlideIn 0.4s cubic-bezier(0.22, 1, 0.36, 1) both',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
            <SignalTag signal={result.signal} />
            <span style={{ fontFamily: 'Georgia, serif', fontSize: 24, fontWeight: 700, color: 'var(--primary)' }}>
              {Math.round(result.confidence * 100)}%
            </span>
            <span style={{ fontSize: 12, color: 'var(--muted-foreground)', fontWeight: 500 }}>confidence</span>
          </div>
          <p style={{ fontSize: 13, lineHeight: 1.7, color: 'var(--muted-foreground)', marginBottom: 12 }}>{result.reasoning}</p>
          {result.key_factors?.length > 0 && (
            <ul style={{ paddingLeft: 18, margin: 0 }}>
              {result.key_factors.map((f, i) => (
                <li key={i} style={{ fontSize: 12, color: 'var(--muted-foreground)', marginBottom: 5, lineHeight: 1.5 }}>{f}</li>
              ))}
            </ul>
          )}
          <p style={{ fontSize: 11, fontFamily: "'Inter', monospace", color: 'var(--muted-foreground)', marginTop: 12, fontWeight: 500 }}>
            Resolves after: {result.resolve_after ? fmtDateShort(result.resolve_after) : '—'} · {result.memory_count} memories used
          </p>
        </div>
      )}
    </div>
  )
}

export default function StockDetail() {
  const { ticker } = useParams()
  const navigate = useNavigate()
  const tUpper = ticker?.toUpperCase()

  const { data: snapshot, isLoading: snapLoading, error: snapError } = useQuery({
    queryKey: ['snapshot', tUpper],
    queryFn: () => fetchSnapshot(tUpper),
    refetchInterval: 60_000,
  })

  const { data: predictions, isLoading: predLoading } = useQuery({
    queryKey: ['predictions', tUpper],
    queryFn: () => fetchPredictions(tUpper, 10),
    enabled: !!tUpper,
  })

  const { data: accuracy } = useQuery({
    queryKey: ['accuracy', tUpper],
    queryFn: () => fetchTickerAccuracy(tUpper),
    retry: false,
  })

  const ind = snapshot?.price?.indicators

  return (
    <PageFrame
      eyebrow={`Stocks / ${tUpper}`}
      title={`${tUpper} — Analysis`}
      description="Live price snapshot, technical indicators, and AI-generated signal."
      action={tUpper && <AnalyzeButton ticker={tUpper} />}
    >
      {snapLoading && (
        <div style={{ display: 'flex', justifyContent: 'center', padding: 60 }}>
          <LoadingSpinner size={32} />
        </div>
      )}

      {snapError && (
        <div className="glass-card" style={{ padding: 20, color: 'var(--destructive)', fontSize: 13, borderColor: 'oklch(0.65 0.2 18 / 30%)' }}>
          Failed to load data for {tUpper}: {snapError.message}
        </div>
      )}

      {snapshot && (
        <div style={{ display: 'grid', gridTemplateColumns: '1.3fr 0.7fr', gap: 20, marginBottom: 36 }}>
          {/* Price panel — clean elevated light card */}
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
            {/* Subtle shimmer accent */}
            <div style={{
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              height: 2,
              background: 'linear-gradient(90deg, transparent, var(--primary), transparent)',
            }} />

            <p style={{
              fontSize: 10,
              fontFamily: "'Inter', monospace",
              textTransform: 'uppercase',
              letterSpacing: '0.14em',
              color: 'var(--muted-foreground)',
              fontWeight: 600,
            }}>
              Current price
            </p>
            <p style={{
              fontSize: 52,
              fontWeight: 700,
              letterSpacing: '-0.04em',
              lineHeight: 1,
              marginTop: 10,
              fontFamily: 'Georgia, serif',
            }}>
              {fmtPrice(snapshot.price.current_price)}
            </p>
            <div style={{ display: 'flex', gap: 28, marginTop: 20, paddingTop: 20, borderTop: '1px solid var(--border)' }}>
              {[
                ['Open', fmtPrice(snapshot.price.open_price)],
                ['High', fmtPrice(snapshot.price.high_price)],
                ['Low', fmtPrice(snapshot.price.low_price)],
                ['Volume', (snapshot.price.volume / 1e6).toFixed(1) + 'M'],
              ].map(([k, v]) => (
                <div key={k}>
                  <p style={{ fontSize: 10, fontFamily: "'Inter', monospace", color: 'var(--muted-foreground)', marginBottom: 5, fontWeight: 600 }}>{k}</p>
                  <p style={{ fontFamily: "'Inter', monospace", fontWeight: 700, fontSize: 14 }}>{v}</p>
                </div>
              ))}
            </div>
            {accuracy && (
              <div style={{ marginTop: 20, paddingTop: 18, borderTop: '1px solid var(--border)', display: 'flex', gap: 8, alignItems: 'center' }}>
                <span style={{ fontSize: 10, fontFamily: "'Inter', monospace", color: 'var(--muted-foreground)', textTransform: 'uppercase', letterSpacing: '0.12em', fontWeight: 600 }}>Model accuracy on {tUpper}:</span>
                <span style={{ fontFamily: 'Georgia, serif', fontWeight: 700, fontSize: 18, color: 'var(--primary)' }}>
                  {accuracy.overall_accuracy_pct != null ? `${accuracy.overall_accuracy_pct}%` : '—'}
                </span>
              </div>
            )}
          </article>

          {/* Indicators panel */}
          <div className="glass-card" style={{ padding: '22px 26px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <Database size={14} color="var(--primary)" />
              <h2 style={{ fontSize: 14, fontWeight: 600 }}>Technical indicators</h2>
            </div>
            <dl>
              {[
                ['RSI (14)', fmt(ind?.rsi_14)],
                ['MACD line', fmt(ind?.macd_line)],
                ['MACD signal', fmt(ind?.macd_signal)],
                ['BB upper', fmtPrice(ind?.bb_upper)],
                ['BB lower', fmtPrice(ind?.bb_lower)],
                ['%B', fmt(ind?.bb_pct_b)],
                ['SMA 50', fmtPrice(ind?.sma_50)],
                ['SMA 200', fmtPrice(ind?.sma_200)],
                ['Volume ratio', ind?.volume_ratio != null ? `${fmt(ind.volume_ratio)}×` : '—'],
                ['52W High', fmtPrice(ind?.week_52_high)],
                ['52W Low', fmtPrice(ind?.week_52_low)],
                ['ATR (14)', fmt(ind?.atr_14)],
              ].map(([label, value], i) => (
                <IndicatorRow key={label} label={label} value={value} even={i % 2 === 1} />
              ))}
            </dl>
          </div>
        </div>
      )}

      {/* News */}
      {snapshot?.news?.length > 0 && (
        <section style={{ marginBottom: 36 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 18 }}>
            <Newspaper size={14} color="var(--primary)" />
            <h2 style={{ fontSize: 14, fontWeight: 600 }}>Recent news ({snapshot.news.length})</h2>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {snapshot.news.slice(0, 6).map(item => (
              <a
                key={item.finnhub_id}
                href={item.url || '#'}
                target="_blank"
                rel="noopener noreferrer"
                className="glass-card"
                style={{
                  display: 'block',
                  padding: '16px 20px',
                }}
                onMouseEnter={e => {
                  e.currentTarget.style.borderColor = 'var(--primary)'
                  e.currentTarget.style.transform = 'translateY(-1px)'
                }}
                onMouseLeave={e => {
                  e.currentTarget.style.borderColor = 'var(--glass-border)'
                  e.currentTarget.style.transform = 'translateY(0)'
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
                  <p style={{ fontSize: 13, fontWeight: 600, lineHeight: 1.45 }}>{item.headline}</p>
                  {item.source && (
                    <span style={{ fontSize: 10, fontFamily: "'Inter', monospace", color: 'var(--muted-foreground)', whiteSpace: 'nowrap', fontWeight: 500 }}>{item.source}</span>
                  )}
                </div>
                {item.summary && (
                  <p style={{ fontSize: 12, color: 'var(--muted-foreground)', marginTop: 7, lineHeight: 1.55, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                    {item.summary}
                  </p>
                )}
              </a>
            ))}
          </div>
        </section>
      )}

      {/* Prediction history */}
      {(predictions?.length > 0 || predLoading) && (
        <section className="glass-card" style={{ overflow: 'hidden' }}>
          <div style={{ padding: '16px 22px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 8 }}>
            <TrendingUp size={14} color="var(--primary)" />
            <h2 style={{ fontSize: 14, fontWeight: 600 }}>Past predictions</h2>
          </div>
          {predLoading ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: 24 }}><LoadingSpinner /></div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Signal</th>
                  <th>Confidence</th>
                  <th>Outcome</th>
                  <th>% move</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {predictions.map(row => (
                  <tr key={row.prediction_id} onClick={() => navigate(`/predictions/${row.prediction_id}`)}>
                    <td><SignalTag signal={row.signal} /></td>
                    <td style={{ fontFamily: "'Inter', monospace", fontWeight: 600 }}>{fmtPct(row.confidence * 100, 0)}</td>
                    <td>
                      {row.correct == null
                        ? <span style={{ color: 'var(--muted-foreground)', fontSize: 12, fontWeight: 500 }}>Pending</span>
                        : <span style={{ color: row.correct ? 'var(--primary)' : 'var(--destructive)', fontWeight: 600 }}>
                          {row.correct ? '✓ Correct' : '✗ Incorrect'}
                        </span>
                      }
                    </td>
                    <td style={{ fontFamily: "'Inter', monospace", fontWeight: 600, color: row.outcome_pct > 0 ? 'var(--primary)' : row.outcome_pct < 0 ? 'var(--destructive)' : 'var(--muted-foreground)' }}>
                      {row.outcome_pct != null ? `${row.outcome_pct > 0 ? '+' : ''}${fmt(row.outcome_pct)}%` : '—'}
                    </td>
                    <td style={{ color: 'var(--muted-foreground)', fontSize: 12 }}>{fmtDate(row.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}
    </PageFrame>
  )
}
