import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { Play, ShieldCheck, Radio, Database, Zap, RefreshCw } from 'lucide-react'
import { fetchStatus, fetchSchedulerStatus, fetchRecentLogs, triggerScan, resolveOne } from '../lib/api'
import { PageFrame } from '../components/Layout'
import LoadingSpinner from '../components/LoadingSpinner'
import { fmtDate } from '../lib/utils'

function LogEntry({ log }) {
  const isSuccess = log.message?.toLowerCase().includes('correct') ||
    log.message?.toLowerCase().includes('success') ||
    log.message?.toLowerCase().includes('completed')

  return (
    <div style={{
      borderBottom: '1px solid rgba(0, 0, 0, 0.05)',
      padding: '11px 0',
      fontSize: 12,
      fontFamily: "'Inter', monospace",
      color: '#334155',
      display: 'flex',
      gap: 12,
      transition: 'background 200ms ease',
    }}>
      <span style={{ color: isSuccess ? 'var(--success)' : '#94a3b8', userSelect: 'none', fontSize: 10, marginTop: 1 }}>▶</span>
      <span style={{ lineHeight: 1.5 }}>
        <span style={{ color: '#94a3b8', marginRight: 10, fontSize: 11 }}>
          {log.timestamp ? new Date(log.timestamp).toLocaleTimeString() : '—'}
        </span>
        <span style={{ color: '#475569', marginRight: 10, fontWeight: 600 }}>{log.name || 'app'}</span>
        <span style={{ color: isSuccess ? 'var(--success)' : '#1e293b' }}>{log.message}</span>
      </span>
    </div>
  )
}

export default function Admin() {
  const [resolveId, setResolveId] = useState('')
  const [resolveResult, setResolveResult] = useState(null)

  const { data: status } = useQuery({ queryKey: ['status'], queryFn: fetchStatus, refetchInterval: 30_000 })
  const { data: scheduler } = useQuery({ queryKey: ['scheduler'], queryFn: fetchSchedulerStatus, refetchInterval: 15_000 })
  const { data: logs, refetch: refetchLogs } = useQuery({
    queryKey: ['logs'],
    queryFn: () => fetchRecentLogs(50),
    refetchInterval: 30_000,
  })

  const scanMutation = useMutation({ mutationFn: triggerScan })

  const resolveMutation = useMutation({
    mutationFn: () => resolveOne(resolveId.trim()),
    onSuccess: (data) => {
      setResolveResult(data)
      setResolveId('')
    },
  })

  const dbOk = status?.checks?.database === 'ok'
  const nimOk = status?.checks?.nim_api_key === 'configured'
  const finnhubOk = status?.checks?.finnhub_api_key === 'configured'

  return (
    <PageFrame
      eyebrow="System / Admin"
      title="Control room."
      description="Operational visibility for the prediction engine and its learning loop."
    >
      {/* Status cards */}
      <div className="stagger-children" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(185px, 1fr))', gap: 12, marginBottom: 32 }}>
        {[
          { label: 'Database', ok: dbOk, meta: status?.checks?.database || 'unknown', Icon: Database },
          { label: 'NVIDIA NIM API', ok: nimOk, meta: status?.checks?.nim_api_key || 'unknown', Icon: Zap },
          { label: 'Finnhub API', ok: finnhubOk, meta: status?.checks?.finnhub_api_key || 'unknown', Icon: Radio },
          { label: 'Scheduler', ok: scheduler?.running, meta: scheduler?.market_hours_open ? 'Market open' : 'Market closed', Icon: Play },
        ].map(({ label, ok, meta, Icon }) => (
          <div key={label} className="glass-card" style={{ padding: 22 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 18 }}>
              <span style={{ fontSize: 13, fontWeight: 600 }}>{label}</span>
              <Icon size={15} color="var(--primary)" strokeWidth={1.8} />
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, fontWeight: 700, color: ok ? 'var(--primary)' : 'var(--destructive)' }}>
              <span
                className={ok ? 'pulse-dot' : ''}
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: '50%',
                  background: ok ? 'var(--primary)' : 'var(--destructive)',
                  display: 'inline-block',
                  boxShadow: ok ? '0 0 8px var(--primary-glow)' : 'none',
                }}
              />
              {ok ? 'Healthy' : 'Issue'}
            </div>
            <p style={{ fontSize: 11, fontFamily: "'Inter', monospace", color: 'var(--muted-foreground)', marginTop: 6, fontWeight: 500 }}>{meta}</p>
          </div>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 0.6fr', gap: 20, marginBottom: 32 }}>
        {/* Live log stream */}
        <section style={{
          border: '1px solid var(--border)',
          background: '#ffffff',
          borderRadius: 'var(--radius)',
          overflow: 'hidden',
          position: 'relative',
          boxShadow: '0 1px 3px rgba(0, 0, 0, 0.04)',
        }}>
          {/* Top accent */}
          <div style={{
            position: 'absolute',
            top: 0, left: 0, right: 0,
            height: 2,
            background: 'linear-gradient(90deg, transparent, var(--primary), transparent)',
          }} />

          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '16px 22px',
            borderBottom: '1px solid var(--border)',
            background: '#f8fafc',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Radio size={14} color="var(--primary)" />
              <h2 style={{ fontSize: 14, fontWeight: 600, color: 'var(--foreground)' }}>Live event stream</h2>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <span style={{ fontSize: 10, fontFamily: "'Inter', monospace", color: 'var(--muted-foreground)', textTransform: 'uppercase', letterSpacing: '0.1em', fontWeight: 600 }}>
                AUTO-REFRESH 30S
              </span>
              <button
                onClick={() => refetchLogs()}
                style={{
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  color: 'var(--muted-foreground)',
                  display: 'flex',
                  padding: 4,
                  borderRadius: 3,
                  transition: 'all 200ms ease',
                }}
                onMouseEnter={e => {
                  e.currentTarget.style.color = 'var(--primary)'
                  e.currentTarget.style.background = 'rgba(0, 0, 0, 0.04)'
                }}
                onMouseLeave={e => {
                  e.currentTarget.style.color = 'var(--muted-foreground)'
                  e.currentTarget.style.background = 'none'
                }}
              >
                <RefreshCw size={13} />
              </button>
            </div>
          </div>
          <div style={{ height: 380, overflowY: 'auto', padding: '4px 22px' }}>
            {!logs ? (
              <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}><LoadingSpinner /></div>
            ) : logs.length === 0 ? (
              <p style={{ fontSize: 12, fontFamily: "'Inter', monospace", color: 'var(--muted-foreground)', padding: '20px 0', fontWeight: 500 }}>No recent logs.</p>
            ) : (
              [...logs].reverse().map((log, i) => <LogEntry key={i} log={log} />)
            )}
          </div>
        </section>

        {/* Actions panel */}
        <section style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Manual scan */}
          <div className="glass-card" style={{ padding: 26 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
              <Play size={15} color="var(--secondary)" />
              <h2 style={{ fontSize: 14, fontWeight: 600 }}>Manual scan</h2>
            </div>
            <p style={{ fontSize: 12, color: 'var(--muted-foreground)', lineHeight: 1.55, marginBottom: 18, fontWeight: 500 }}>
              Run a prediction cycle across your entire active watchlist.
            </p>
            <button
              onClick={() => scanMutation.mutate()}
              disabled={scanMutation.isPending}
              style={{
                width: '100%',
                background: 'var(--primary)',
                color: 'var(--primary-foreground)',
                border: 'none',
                padding: '11px 18px',
                fontSize: 13,
                fontWeight: 700,
                cursor: scanMutation.isPending ? 'not-allowed' : 'pointer',
                opacity: scanMutation.isPending ? 0.7 : 1,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 6,
                borderRadius: 'var(--radius)',
                transition: 'all 220ms cubic-bezier(0.22, 1, 0.36, 1)',
                boxShadow: '0 2px 10px rgba(180, 120, 22, 0.2)',
              }}
            >
              {scanMutation.isPending ? <><LoadingSpinner size={14} /> Scanning…</> : 'Trigger watchlist scan'}
            </button>
            {scanMutation.isSuccess && (
              <p style={{ fontSize: 11, color: 'var(--primary)', marginTop: 10, fontWeight: 600 }}>✓ Scan completed.</p>
            )}
            {scanMutation.isError && (
              <p style={{ fontSize: 11, color: 'var(--destructive)', marginTop: 10, fontWeight: 500 }}>{scanMutation.error?.message}</p>
            )}
          </div>

          {/* Force resolve */}
          <div className="glass-card" style={{ padding: 26 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
              <ShieldCheck size={15} color="var(--primary)" />
              <h2 style={{ fontSize: 14, fontWeight: 600 }}>Force resolve</h2>
            </div>
            <p style={{ fontSize: 12, color: 'var(--muted-foreground)', lineHeight: 1.55, marginBottom: 14, fontWeight: 500 }}>
              Resolve a prediction by its UUID immediately.
            </p>
            <input
              value={resolveId}
              onChange={e => setResolveId(e.target.value)}
              placeholder="Prediction UUID"
              style={{
                width: '100%',
                border: '1px solid var(--border)',
                background: 'var(--input)',
                padding: '9px 14px',
                fontSize: 12,
                fontFamily: "'Inter', monospace",
                outline: 'none',
                color: 'var(--foreground)',
                marginBottom: 10,
                boxSizing: 'border-box',
                borderRadius: 'var(--radius)',
                transition: 'all 200ms ease',
                fontWeight: 600,
              }}
            />
            <button
              onClick={() => resolveMutation.mutate()}
              disabled={!resolveId.trim() || resolveMutation.isPending}
              style={{
                width: '100%',
                border: '1px solid var(--border)',
                background: 'transparent',
                padding: '9px 16px',
                fontSize: 12,
                cursor: resolveId.trim() && !resolveMutation.isPending ? 'pointer' : 'not-allowed',
                color: 'var(--foreground)',
                transition: 'all 220ms cubic-bezier(0.22, 1, 0.36, 1)',
                opacity: !resolveId.trim() ? 0.5 : 1,
                borderRadius: 'var(--radius)',
                fontWeight: 600,
              }}
              onMouseEnter={e => {
                if (resolveId.trim()) {
                  e.currentTarget.style.borderColor = 'var(--primary)'
                  e.currentTarget.style.color = 'var(--primary)'
                }
              }}
              onMouseLeave={e => {
                e.currentTarget.style.borderColor = 'var(--border)'
                e.currentTarget.style.color = 'var(--foreground)'
              }}
            >
              {resolveMutation.isPending ? 'Resolving…' : 'Resolve prediction'}
            </button>
            {resolveResult && (
              <div style={{
                marginTop: 12,
                padding: 12,
                background: 'oklch(0.52 0.15 65 / 8%)',
                fontSize: 11,
                fontFamily: "'Inter', monospace",
                borderRadius: 'var(--radius)',
                border: '1px solid oklch(0.52 0.15 65 / 25%)',
              }}>
                <p style={{ color: 'var(--primary)', fontWeight: 700 }}>✓ Resolved</p>
                {resolveResult.outcome_pct != null && <p style={{ marginTop: 4, fontWeight: 600 }}>Outcome: {resolveResult.outcome_pct > 0 ? '+' : ''}{resolveResult.outcome_pct?.toFixed(2)}%</p>}
                <p style={{ marginTop: 2, fontWeight: 600 }}>Correct: {resolveResult.correct ? 'Yes' : 'No'}</p>
              </div>
            )}
            {resolveMutation.isError && (
              <p style={{ fontSize: 11, color: 'var(--destructive)', marginTop: 8, fontWeight: 500 }}>{resolveMutation.error?.message}</p>
            )}
          </div>

          {/* Config summary */}
          {status?.config && (
            <div className="glass-card" style={{ padding: 26 }}>
              <h2 style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>Agent config</h2>
              {[
                ['Watchlist', status.config.watchlist?.join(', ')],
                ['Scan interval', `${status.config.scan_interval_minutes}m`],
                ['News poll', `${status.config.news_poll_interval_minutes}m`],
                ['Resolution horizon', `${status.config.resolution_horizon_days}d`],
                ['Correctness threshold', `${status.config.correctness_threshold_pct}%`],
                ['Memory top-k', status.config.memory_top_k],
              ].map(([k, v], i) => (
                <div key={k} style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  padding: '7px 0',
                  borderBottom: '1px solid var(--border)',
                  fontSize: 12,
                  background: i % 2 === 1 ? 'rgba(0, 0, 0, 0.018)' : 'transparent',
                  paddingLeft: i % 2 === 1 ? 8 : 0,
                  paddingRight: i % 2 === 1 ? 8 : 0,
                  borderRadius: i % 2 === 1 ? 3 : 0,
                }}>
                  <span style={{ color: 'var(--muted-foreground)', fontWeight: 500 }}>{k}</span>
                  <span style={{ fontFamily: "'Inter', monospace", fontWeight: 700, letterSpacing: '0.02em' }}>{v}</span>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </PageFrame>
  )
}
