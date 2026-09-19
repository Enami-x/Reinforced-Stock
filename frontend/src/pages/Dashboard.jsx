import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  TrendingUp, TrendingDown, Clock, CheckCircle, XCircle,
  Activity, BarChart2, Target, Zap, ChevronRight, RefreshCw,
  Circle, ArrowUpRight, Minus
} from 'lucide-react'
import { fetchAccuracy, fetchStatus, fetchSchedulerStatus, fetchPredictions } from '../lib/api'
import { PageFrame } from '../components/Layout'
import SignalTag from '../components/SignalTag'
import LoadingSpinner from '../components/LoadingSpinner'
import { fmtPct, fmtDate, fmt } from '../lib/utils'

/* ─── Accuracy Ring (SVG gauge) ─── */
function AccuracyRing({ pct, size = 130 }) {
  const r = (size - 18) / 2
  const circ = 2 * Math.PI * r
  const filled = pct != null ? (pct / 100) * circ : 0
  const cx = size / 2
  const cy = size / 2

  return (
    <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="var(--muted)" strokeWidth={12} />
      <circle
        cx={cx} cy={cy} r={r} fill="none"
        stroke="var(--primary)" strokeWidth={12}
        strokeDasharray={`${filled} ${circ}`}
        strokeLinecap="round"
        style={{ transition: 'stroke-dasharray 1.2s cubic-bezier(0.22, 1, 0.36, 1)' }}
      />
    </svg>
  )
}

/* ─── KPI Card ─── */
function KpiCard({ label, value, sub, color, icon: Icon, trend, delay = 0 }) {
  const trendColor = trend === 'up' ? 'var(--success)' : trend === 'down' ? 'var(--destructive)' : 'var(--muted-foreground)'
  const TrendIcon = trend === 'up' ? TrendingUp : trend === 'down' ? TrendingDown : Minus
  return (
    <div
      className="stat-widget"
      style={{ animationDelay: `${delay}ms`, padding: '22px 22px 18px', display: 'flex', flexDirection: 'column', gap: 0 }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <p style={{
          fontSize: 10,
          fontFamily: "'Inter', monospace",
          textTransform: 'uppercase',
          letterSpacing: '0.12em',
          color: 'var(--muted-foreground)',
          fontWeight: 600,
        }}>{label}</p>
        {Icon && (
          <span style={{
            width: 28, height: 28, borderRadius: 6,
            background: color ? `${color}14` : 'var(--muted)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <Icon size={13} color={color || 'var(--muted-foreground)'} strokeWidth={2} />
          </span>
        )}
      </div>
      <p style={{
        fontSize: 34,
        fontWeight: 700,
        color: color || 'var(--foreground)',
        lineHeight: 1,
        letterSpacing: '-0.03em',
        fontFamily: 'Georgia, serif',
        marginBottom: 10,
      }}>{value}</p>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        {trend && <TrendIcon size={11} color={trendColor} />}
        {sub && <p style={{ fontSize: 11, color: 'var(--muted-foreground)', fontWeight: 500 }}>{sub}</p>}
      </div>
    </div>
  )
}

/* ─── Win Rate Gauge Card ─── */
function WinRateCard({ accuracy, delay = 0 }) {
  const pct = accuracy?.overall_accuracy_pct
  return (
    <div
      className="stat-widget"
      style={{
        animationDelay: `${delay}ms`,
        padding: '22px',
        display: 'flex',
        alignItems: 'center',
        gap: 20,
        gridColumn: 'span 2',
      }}
    >
      <div style={{ position: 'relative', flexShrink: 0, width: 130, height: 130 }}>
        <AccuracyRing pct={pct ?? 0} />
        <div style={{
          position: 'absolute', inset: 0,
          display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center',
          gap: 3,
        }}>
          <p style={{
            fontSize: 24,
            fontWeight: 700,
            fontFamily: 'Georgia, serif',
            letterSpacing: '-0.03em',
            color: 'var(--primary)',
            lineHeight: 1,
          }}>
            {pct != null ? `${pct}%` : '—'}
          </p>
          <p style={{ fontSize: 8, color: 'var(--muted-foreground)', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', whiteSpace: 'nowrap' }}>Win Rate</p>
        </div>
      </div>
      <div style={{ flex: 1 }}>
        <p style={{ fontSize: 10, fontFamily: "'Inter', monospace", textTransform: 'uppercase', letterSpacing: '0.12em', color: 'var(--muted-foreground)', fontWeight: 600, marginBottom: 6 }}>Overall accuracy</p>
        <div style={{ display: 'flex', gap: 18, marginTop: 8 }}>
          <div>
            <p style={{ fontSize: 22, fontWeight: 700, fontFamily: 'Georgia, serif', color: 'var(--success)', letterSpacing: '-0.03em' }}>{accuracy?.correct ?? '—'}</p>
            <p style={{ fontSize: 10, color: 'var(--muted-foreground)', fontWeight: 500, marginTop: 2 }}>Correct</p>
          </div>
          <div style={{ width: 1, background: 'var(--border)', alignSelf: 'stretch' }} />
          <div>
            <p style={{ fontSize: 22, fontWeight: 700, fontFamily: 'Georgia, serif', color: 'var(--destructive)', letterSpacing: '-0.03em' }}>{accuracy?.incorrect ?? '—'}</p>
            <p style={{ fontSize: 10, color: 'var(--muted-foreground)', fontWeight: 500, marginTop: 2 }}>Incorrect</p>
          </div>
          <div style={{ width: 1, background: 'var(--border)', alignSelf: 'stretch' }} />
          <div>
            <p style={{ fontSize: 22, fontWeight: 700, fontFamily: 'Georgia, serif', color: 'var(--muted-foreground)', letterSpacing: '-0.03em' }}>{accuracy?.pending ?? '—'}</p>
            <p style={{ fontSize: 10, color: 'var(--muted-foreground)', fontWeight: 500, marginTop: 2 }}>Pending</p>
          </div>
        </div>
        <div style={{ marginTop: 14 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
            <span style={{ fontSize: 10, color: 'var(--muted-foreground)', fontWeight: 500 }}>Resolution rate</span>
            <span style={{ fontSize: 10, fontWeight: 700, color: 'var(--foreground)' }}>
              {accuracy?.total_predictions ? Math.round((accuracy.resolved / accuracy.total_predictions) * 100) : 0}%
            </span>
          </div>
          <div style={{ height: 4, background: 'var(--muted)', borderRadius: 99, overflow: 'hidden' }}>
            <div style={{
              height: '100%',
              background: 'linear-gradient(90deg, var(--primary), oklch(0.62 0.12 65))',
              borderRadius: 99,
              width: accuracy?.total_predictions ? `${Math.round((accuracy.resolved / accuracy.total_predictions) * 100)}%` : '0%',
              transition: 'width 1s cubic-bezier(0.22, 1, 0.36, 1)',
            }} />
          </div>
        </div>
      </div>
    </div>
  )
}

/* ─── Signal Breakdown with bar charts ─── */
function SignalBreakdown({ bySignal }) {
  if (!bySignal) return (
    <div style={{ padding: '32px 0', textAlign: 'center' }}>
      <p style={{ fontSize: 12, color: 'var(--muted-foreground)' }}>No resolved predictions yet.</p>
    </div>
  )

  const signals = Object.entries(bySignal)
  const signalColors = { BUY: 'var(--success)', SELL: 'var(--destructive)', HOLD: 'var(--muted-foreground)' }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18, marginTop: 20 }}>
      {signals.map(([signal, stats]) => {
        const pct = stats.accuracy_pct ?? 0
        const color = signalColors[signal] || 'var(--primary)'
        return (
          <div key={signal}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <SignalTag signal={signal} />
                <span style={{ fontSize: 11, color: 'var(--muted-foreground)', fontWeight: 500 }}>
                  {stats.correct}/{stats.resolved} correct
                </span>
              </div>
              <span style={{
                fontSize: 16,
                fontWeight: 700,
                fontFamily: 'Georgia, serif',
                color,
                letterSpacing: '-0.02em',
              }}>{pct != null ? `${pct}%` : '—'}</span>
            </div>
            <div style={{ height: 5, background: 'var(--muted)', borderRadius: 99, overflow: 'hidden' }}>
              <div style={{
                height: '100%',
                background: color,
                borderRadius: 99,
                width: `${pct}%`,
                opacity: 0.85,
                transition: 'width 1s cubic-bezier(0.22, 1, 0.36, 1)',
              }} />
            </div>
          </div>
        )
      })}
    </div>
  )
}

/* ─── Scheduler Jobs Panel ─── */
function SchedulerPanel({ scheduler }) {
  if (!scheduler) return <div style={{ display: 'flex', justifyContent: 'center', padding: 24 }}><LoadingSpinner /></div>

  const statusColor = scheduler.running ? 'var(--success)' : 'var(--destructive)'
  const mktColor = scheduler.market_hours_open ? 'var(--success)' : 'var(--muted-foreground)'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
      {/* Status row */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '0 0 16px',
        borderBottom: '1px solid var(--border)',
        marginBottom: 16,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{
            width: 8, height: 8, borderRadius: '50%',
            background: statusColor,
            display: 'inline-block',
            boxShadow: scheduler.running ? '0 0 0 3px oklch(0.52 0.17 145 / 20%)' : 'none',
          }} className={scheduler.running ? 'pulse-dot' : ''} />
          <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--foreground)' }}>
            {scheduler.running ? 'Running' : 'Stopped'}
          </span>
        </div>
        <span style={{
          fontSize: 10, fontWeight: 700,
          color: mktColor,
          background: scheduler.market_hours_open ? 'oklch(0.52 0.17 145 / 10%)' : 'var(--muted)',
          border: `1px solid ${scheduler.market_hours_open ? 'oklch(0.52 0.17 145 / 25%)' : 'var(--border)'}`,
          padding: '2px 8px',
          borderRadius: 4,
          letterSpacing: '0.06em',
          textTransform: 'uppercase',
          fontFamily: "'Inter', monospace",
        }}>
          Market {scheduler.market_hours_open ? 'Open' : 'Closed'}
        </span>
      </div>

      {/* Jobs */}
      {scheduler.jobs && Object.entries(scheduler.jobs).map(([name, info], i) => (
        <div key={name} style={{
          display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
          padding: '10px 0',
          borderBottom: i < Object.entries(scheduler.jobs).length - 1 ? '1px solid var(--border)' : 'none',
        }}>
          <div>
            <p style={{
              fontSize: 11,
              fontFamily: "'Inter', monospace",
              fontWeight: 700,
              letterSpacing: '0.03em',
              color: 'var(--foreground)',
              marginBottom: 2,
            }}>{name}</p>
            <p style={{ fontSize: 10, color: 'var(--muted-foreground)', fontWeight: 500 }}>
              Next run
            </p>
          </div>
          <p style={{ fontSize: 11, color: 'var(--muted-foreground)', fontWeight: 500, textAlign: 'right' }}>
            {info.next_run ? fmtDate(info.next_run) : '—'}
          </p>
        </div>
      ))}
    </div>
  )
}

/* ─── Watchlist Ticker Card ─── */
function TickerCard({ ticker, navigate }) {
  return (
    <button
      onClick={() => navigate(`/stocks/${ticker}`)}
      style={{
        border: '1px solid var(--border)',
        background: 'var(--glass-bg)',
        backdropFilter: 'blur(12px)',
        padding: '14px 18px',
        borderRadius: 'var(--radius)',
        cursor: 'pointer',
        color: 'var(--foreground)',
        transition: 'all 220ms cubic-bezier(0.22, 1, 0.36, 1)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        width: '100%',
        textAlign: 'left',
        boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
      }}
      onMouseEnter={e => {
        e.currentTarget.style.borderColor = 'var(--primary)'
        e.currentTarget.style.transform = 'translateY(-2px)'
        e.currentTarget.style.boxShadow = '0 6px 20px rgba(0,0,0,0.08)'
      }}
      onMouseLeave={e => {
        e.currentTarget.style.borderColor = 'var(--border)'
        e.currentTarget.style.transform = 'translateY(0)'
        e.currentTarget.style.boxShadow = '0 1px 3px rgba(0,0,0,0.04)'
      }}
    >
      <div>
        <p style={{
          fontSize: 14,
          fontFamily: "'Inter', monospace",
          fontWeight: 800,
          letterSpacing: '0.06em',
          color: 'var(--foreground)',
          textTransform: 'uppercase',
        }}>{ticker}</p>
        <p style={{ fontSize: 10, color: 'var(--muted-foreground)', fontWeight: 500, marginTop: 2 }}>View details</p>
      </div>
      <ArrowUpRight size={14} color="var(--muted-foreground)" />
    </button>
  )
}

/* ─── Recent Predictions Table ─── */
function RecentPredictionsTable({ tickers }) {
  const navigate = useNavigate()
  const ticker = tickers?.[0]
  const { data, isLoading } = useQuery({
    queryKey: ['predictions', ticker],
    queryFn: () => fetchPredictions(ticker, 10),
    enabled: !!ticker,
  })

  if (!ticker) return null
  if (isLoading) return <div style={{ display: 'flex', justifyContent: 'center', padding: 32 }}><LoadingSpinner /></div>

  const rows = data || []

  if (rows.length === 0) {
    return (
      <div style={{ padding: '40px 24px', textAlign: 'center' }}>
        <BarChart2 size={24} color="var(--muted-foreground)" style={{ margin: '0 auto 10px' }} />
        <p style={{ fontSize: 13, color: 'var(--muted-foreground)' }}>No predictions yet for {ticker}.</p>
      </div>
    )
  }

  return (
    <table className="data-table">
      <thead>
        <tr>
          <th>Ticker</th>
          <th>Signal</th>
          <th>Confidence</th>
          <th>Outcome</th>
          <th>Created</th>
          <th style={{ width: 32 }}></th>
        </tr>
      </thead>
      <tbody>
        {rows.map(row => (
          <tr key={row.prediction_id} onClick={() => navigate(`/predictions/${row.prediction_id}`)}>
            <td>
              <span style={{
                fontFamily: "'Inter', monospace",
                fontWeight: 800,
                letterSpacing: '0.05em',
                fontSize: 12,
                color: 'var(--foreground)',
              }}>{row.ticker}</span>
            </td>
            <td><SignalTag signal={row.signal} /></td>
            <td>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div style={{ width: 40, height: 3, background: 'var(--muted)', borderRadius: 99, overflow: 'hidden' }}>
                  <div style={{
                    height: '100%',
                    width: `${(row.confidence || 0) * 100}%`,
                    background: 'var(--primary)',
                    borderRadius: 99,
                  }} />
                </div>
                <span style={{ fontFamily: "'Inter', monospace", fontWeight: 600, fontSize: 12 }}>
                  {fmtPct(row.confidence * 100, 0)}
                </span>
              </div>
            </td>
            <td>
              {row.correct == null
                ? <span style={{ color: 'var(--muted-foreground)', fontSize: 11, fontWeight: 600, background: 'var(--muted)', padding: '2px 8px', borderRadius: 4 }}>Pending</span>
                : row.correct
                  ? <span style={{ color: 'var(--success)', display: 'flex', alignItems: 'center', gap: 5 }}><CheckCircle size={12} /><span style={{ fontSize: 12, fontWeight: 600 }}>Correct</span></span>
                  : <span style={{ color: 'var(--destructive)', display: 'flex', alignItems: 'center', gap: 5 }}><XCircle size={12} /><span style={{ fontSize: 12, fontWeight: 600 }}>Incorrect</span></span>
              }
            </td>
            <td style={{ color: 'var(--muted-foreground)', fontSize: 11, fontWeight: 500 }}>{fmtDate(row.created_at)}</td>
            <td><ChevronRight size={12} color="var(--muted-foreground)" /></td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

/* ─── Section Header ─── */
function SectionHeader({ icon: Icon, title, subtitle, action }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
      marginBottom: 20,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={{
          width: 30, height: 30, borderRadius: 7,
          background: 'oklch(0.52 0.15 65 / 10%)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
        }}>
          <Icon size={14} color="var(--primary)" strokeWidth={2} />
        </span>
        <div>
          <h2 style={{ fontSize: 14, fontWeight: 700, color: 'var(--foreground)', letterSpacing: '-0.01em' }}>{title}</h2>
          {subtitle && <p style={{ fontSize: 11, color: 'var(--muted-foreground)', fontWeight: 500, marginTop: 1 }}>{subtitle}</p>}
        </div>
      </div>
      {action}
    </div>
  )
}

/* ─── Live pulse badge ─── */
function LiveBadge() {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      fontSize: 9, fontWeight: 700, letterSpacing: '0.1em',
      textTransform: 'uppercase',
      fontFamily: "'Inter', monospace",
      color: 'var(--success)',
      background: 'oklch(0.52 0.17 145 / 10%)',
      border: '1px solid oklch(0.52 0.17 145 / 22%)',
      padding: '2px 8px', borderRadius: 99,
    }}>
      <span style={{
        width: 5, height: 5, borderRadius: '50%',
        background: 'var(--success)',
        display: 'inline-block',
      }} className="pulse-dot" />
      Live
    </span>
  )
}

/* ─── Dashboard Page ─── */
export default function Dashboard() {
  const navigate = useNavigate()

  const { data: accuracy, isLoading: accLoading } = useQuery({
    queryKey: ['accuracy'],
    queryFn: fetchAccuracy,
    refetchInterval: 60_000,
  })

  const { data: status } = useQuery({
    queryKey: ['status'],
    queryFn: fetchStatus,
    refetchInterval: 30_000,
  })

  const { data: scheduler } = useQuery({
    queryKey: ['scheduler'],
    queryFn: fetchSchedulerStatus,
    refetchInterval: 30_000,
  })

  const watchlist = status?.config?.watchlist || []

  return (
    <PageFrame
      eyebrow="Overview"
      title="Intelligence dashboard."
      description="Live accuracy metrics, signal performance, and system state — at a glance."
      action={<LiveBadge />}
    >
      {/* ── KPI Row ── */}
      <div className="stagger-children" style={{
        display: 'grid',
        gridTemplateColumns: '2fr 1fr 1fr 1fr',
        gap: 14,
        marginBottom: 28,
      }}>
        {accLoading ? (
          <div style={{ gridColumn: '1/-1', display: 'flex', justifyContent: 'center', padding: 40 }}>
            <LoadingSpinner />
          </div>
        ) : (
          <>
            {/* Gauge card spans 2 */}
            <WinRateCard accuracy={accuracy} delay={0} />
            <KpiCard
              label="Total predictions"
              value={accuracy?.total_predictions ?? '—'}
              sub={`${accuracy?.resolved ?? 0} resolved`}
              icon={BarChart2}
              delay={60}
            />
            <KpiCard
              label="Watchlist"
              value={watchlist.length || '—'}
              sub={watchlist.length > 0 ? `${watchlist.slice(0, 2).join(', ')}${watchlist.length > 2 ? ` +${watchlist.length - 2}` : ''}` : 'No tickers tracked'}
              icon={Target}
              delay={120}
            />
          </>
        )}
      </div>

      {/* ── Middle row: Signal breakdown + Scheduler ── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr', gap: 16, marginBottom: 28 }}>
        {/* Signal accuracy breakdown */}
        <section className="glass-card" style={{ padding: 26 }}>
          <SectionHeader
            icon={Activity}
            title="Signal performance"
            subtitle="Accuracy rate per prediction category"
          />
          <SignalBreakdown bySignal={accuracy?.by_signal} />
        </section>

        {/* Scheduler panel */}
        <section className="glass-card" style={{ padding: 26 }}>
          <SectionHeader
            icon={Clock}
            title="Scheduler"
            subtitle="Background job status"
          />
          <SchedulerPanel scheduler={scheduler} />
        </section>
      </div>

      {/* ── Watchlist ── */}
      {watchlist.length > 0 && (
        <section style={{ marginBottom: 28 }}>
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            marginBottom: 14,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <h2 style={{ fontSize: 13, fontWeight: 700, letterSpacing: '-0.01em' }}>Watchlist</h2>
              <span style={{
                fontSize: 10, fontWeight: 700,
                color: 'var(--muted-foreground)',
                background: 'var(--muted)',
                padding: '1px 7px', borderRadius: 99,
                fontFamily: "'Inter', monospace",
              }}>{watchlist.length}</span>
            </div>
            <button
              onClick={() => navigate('/stocks')}
              style={{
                fontSize: 11, color: 'var(--muted-foreground)', background: 'none',
                border: 'none', cursor: 'pointer', fontWeight: 600,
                display: 'flex', alignItems: 'center', gap: 4,
                transition: 'color 200ms ease',
              }}
              onMouseEnter={e => e.currentTarget.style.color = 'var(--primary)'}
              onMouseLeave={e => e.currentTarget.style.color = 'var(--muted-foreground)'}
            >
              Manage <ChevronRight size={11} />
            </button>
          </div>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))',
            gap: 10,
          }}>
            {watchlist.map(ticker => (
              <TickerCard key={ticker} ticker={ticker} navigate={navigate} />
            ))}
          </div>
        </section>
      )}

      {/* ── Recent Predictions Table ── */}
      {watchlist.length > 0 && (
        <section className="glass-card" style={{ overflow: 'hidden' }}>
          <div style={{
            padding: '18px 24px',
            borderBottom: '1px solid var(--border)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}>
            <SectionHeader
              icon={TrendingUp}
              title={`Recent predictions — ${watchlist[0]}`}
              subtitle="Last 10 signals for leading ticker"
            />
            <button
              onClick={() => navigate(`/predictions`)}
              style={{
                fontSize: 11, color: 'var(--muted-foreground)', background: 'none',
                border: 'none', cursor: 'pointer', fontWeight: 600,
                display: 'flex', alignItems: 'center', gap: 4,
                transition: 'color 200ms ease',
                flexShrink: 0,
                marginBottom: 20,
              }}
              onMouseEnter={e => e.currentTarget.style.color = 'var(--primary)'}
              onMouseLeave={e => e.currentTarget.style.color = 'var(--muted-foreground)'}
            >
              View all <ChevronRight size={11} />
            </button>
          </div>
          <RecentPredictionsTable tickers={watchlist} />
        </section>
      )}

      {/* ── Empty state when no watchlist ── */}
      {watchlist.length === 0 && !accLoading && (
        <div className="glass-card" style={{
          padding: '48px 32px',
          textAlign: 'center',
          marginTop: 8,
        }}>
          <Target size={28} color="var(--muted-foreground)" style={{ margin: '0 auto 12px' }} />
          <p style={{ fontSize: 14, fontWeight: 600, color: 'var(--foreground)', marginBottom: 6 }}>No tickers on watchlist</p>
          <p style={{ fontSize: 12, color: 'var(--muted-foreground)', marginBottom: 20 }}>Add stocks to your watchlist to see predictions and signals here.</p>
          <button
            onClick={() => navigate('/stocks')}
            style={{
              padding: '9px 20px',
              background: 'var(--primary)',
              color: 'var(--primary-foreground)',
              border: 'none',
              borderRadius: 'var(--radius)',
              fontSize: 12,
              fontWeight: 600,
              cursor: 'pointer',
              transition: 'opacity 200ms ease',
            }}
            onMouseEnter={e => e.currentTarget.style.opacity = '0.85'}
            onMouseLeave={e => e.currentTarget.style.opacity = '1'}
          >
            Browse stocks →
          </button>
        </div>
      )}
    </PageFrame>
  )
}
