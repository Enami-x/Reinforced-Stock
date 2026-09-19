import { useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { LayoutDashboard, TrendingUp, List, Settings } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { fetchStatus } from '../lib/api'

const NAV = [
  { to: '/dashboard', label: 'Dashboard',   Icon: LayoutDashboard },
  { to: '/stocks',    label: 'Stocks',       Icon: TrendingUp },
  { to: '/predictions', label: 'Predictions', Icon: List },
  { to: '/admin',     label: 'Admin',        Icon: Settings },
]

/* ─── Tooltip wrapper ─── */
function NavItem({ to, label, Icon }) {
  const [hovered, setHovered] = useState(false)

  return (
    <div style={{ position: 'relative' }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <NavLink
        to={to}
        style={({ isActive }) => ({
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: 40,
          height: 40,
          borderRadius: 10,
          color: isActive ? 'var(--primary)' : 'var(--muted-foreground)',
          background: isActive ? 'oklch(0.52 0.15 65 / 12%)' : 'transparent',
          border: isActive ? '1px solid oklch(0.52 0.15 65 / 20%)' : '1px solid transparent',
          transition: 'all 180ms cubic-bezier(0.22, 1, 0.36, 1)',
          outline: 'none',
          textDecoration: 'none',
        })}
        onMouseEnter={e => {
          const active = e.currentTarget.getAttribute('aria-current') === 'page'
          if (!active) {
            e.currentTarget.style.background = 'rgba(0,0,0,0.055)'
            e.currentTarget.style.color = 'var(--foreground)'
            e.currentTarget.style.borderColor = 'var(--border)'
          }
        }}
        onMouseLeave={e => {
          const active = e.currentTarget.getAttribute('aria-current') === 'page'
          if (!active) {
            e.currentTarget.style.background = 'transparent'
            e.currentTarget.style.color = 'var(--muted-foreground)'
            e.currentTarget.style.borderColor = 'transparent'
          }
        }}
      >
        <Icon size={17} strokeWidth={1.75} />
      </NavLink>

      {/* Floating tooltip */}
      <div style={{
        position: 'absolute',
        left: 'calc(100% + 12px)',
        top: '50%',
        transform: hovered ? 'translateY(-50%) translateX(0)' : 'translateY(-50%) translateX(-6px)',
        opacity: hovered ? 1 : 0,
        pointerEvents: 'none',
        transition: 'opacity 160ms ease, transform 180ms cubic-bezier(0.22, 1, 0.36, 1)',
        zIndex: 100,
        whiteSpace: 'nowrap',
      }}>
        {/* Arrow */}
        <div style={{
          position: 'absolute',
          left: -4,
          top: '50%',
          transform: 'translateY(-50%) rotate(45deg)',
          width: 7,
          height: 7,
          background: 'var(--foreground)',
          borderRadius: 1,
        }} />
        {/* Label */}
        <div style={{
          background: 'var(--foreground)',
          color: 'var(--background)',
          fontSize: 11,
          fontWeight: 600,
          fontFamily: "'Inter', sans-serif",
          letterSpacing: '0.01em',
          padding: '5px 10px',
          borderRadius: 6,
          boxShadow: '0 4px 16px rgba(0,0,0,0.14)',
        }}>
          {label}
        </div>
      </div>
    </div>
  )
}

/* ─── System status dot at bottom ─── */
function StatusDot() {
  const [hovered, setHovered] = useState(false)
  const { data } = useQuery({
    queryKey: ['status'],
    queryFn: fetchStatus,
    refetchInterval: 30_000,
  })

  const ok = data?.status === 'ready'
  const label = ok ? 'Systems ready' : data ? 'Degraded' : 'Connecting…'

  return (
    <div
      style={{ position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <span
        className={ok ? 'pulse-dot' : ''}
        style={{
          display: 'inline-block',
          width: 8,
          height: 8,
          borderRadius: '50%',
          background: ok ? 'var(--success)' : data ? 'var(--destructive)' : '#f59e0b',
          boxShadow: ok ? '0 0 8px oklch(0.52 0.17 145 / 50%)' : 'none',
          cursor: 'default',
        }}
      />
      {/* Tooltip */}
      <div style={{
        position: 'absolute',
        left: 'calc(100% + 12px)',
        top: '50%',
        transform: hovered ? 'translateY(-50%) translateX(0)' : 'translateY(-50%) translateX(-6px)',
        opacity: hovered ? 1 : 0,
        pointerEvents: 'none',
        transition: 'opacity 160ms ease, transform 180ms cubic-bezier(0.22, 1, 0.36, 1)',
        zIndex: 100,
        whiteSpace: 'nowrap',
      }}>
        <div style={{ position: 'absolute', left: -4, top: '50%', transform: 'translateY(-50%) rotate(45deg)', width: 7, height: 7, background: 'var(--foreground)', borderRadius: 1 }} />
        <div style={{
          background: 'var(--foreground)', color: 'var(--background)',
          fontSize: 11, fontWeight: 600, fontFamily: "'Inter', sans-serif",
          padding: '5px 10px', borderRadius: 6,
          boxShadow: '0 4px 16px rgba(0,0,0,0.14)',
        }}>{label}</div>
      </div>
    </div>
  )
}

/* ─── Layout ─── */
export default function Layout({ children }) {
  const location = useLocation()
  const isLanding = location.pathname === '/'

  if (isLanding) return <>{children}</>

  const SIDEBAR_W = 64

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      {/* Icon rail sidebar */}
      <aside style={{
        width: SIDEBAR_W,
        borderRight: '1px solid var(--glass-border)',
        background: 'var(--glass-bg)',
        backdropFilter: 'blur(28px)',
        WebkitBackdropFilter: 'blur(28px)',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        padding: '20px 0',
        position: 'fixed',
        top: 0,
        left: 0,
        height: '100vh',
        zIndex: 50,
        gap: 0,
      }}>
        {/* Logo mark */}
        <NavLink
          to="/"
          title="Stock Insight"
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            marginBottom: 28,
            width: 36,
            height: 36,
            borderRadius: 10,
            transition: 'transform 200ms ease',
            textDecoration: 'none',
          }}
          onMouseEnter={e => e.currentTarget.style.transform = 'scale(1.08)'}
          onMouseLeave={e => e.currentTarget.style.transform = 'scale(1)'}
        >
          <WaveformIcon />
        </NavLink>

        {/* Hairline divider */}
        <div style={{ width: 28, height: 1, background: 'var(--border)', marginBottom: 20 }} />

        {/* Nav icons */}
        <nav style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, flex: 1 }}>
          {NAV.map(({ to, label, Icon }) => (
            <NavItem key={to} to={to} label={label} Icon={Icon} />
          ))}
        </nav>

        {/* Hairline divider */}
        <div style={{ width: 28, height: 1, background: 'var(--border)', marginBottom: 16 }} />

        {/* Status dot */}
        <StatusDot />
      </aside>

      {/* Page content */}
      <main
        key={location.pathname}
        className="page-enter"
        style={{
          marginLeft: SIDEBAR_W,
          flex: 1,
          minWidth: 0,
        }}
      >
        {children}
      </main>
    </div>
  )
}

/* ─── Animated waveform logo mark ─── */
function WaveformIcon() {
  return (
    <svg width="32" height="32" viewBox="0 0 28 28" fill="none" className="waveform-motif">
      <path
        d="M2 14 Q5 8 8 14 Q11 20 14 14 Q17 8 20 14 Q23 20 26 14"
        stroke="var(--primary)" strokeWidth="2" fill="none" strokeLinecap="round"
      />
    </svg>
  )
}

/* ─── Page frame (content area header) ─── */
export function PageFrame({ eyebrow, title, description, children, action }) {
  return (
    <div className="page-enter" style={{ padding: '44px 44px 80px', maxWidth: 1200 }}>
      <div style={{
        display: 'flex',
        alignItems: 'flex-start',
        justifyContent: 'space-between',
        marginBottom: 36,
        paddingBottom: 28,
        borderBottom: '1px solid var(--border)',
        animation: 'fadeSlideIn 0.4s cubic-bezier(0.22, 1, 0.36, 1) both',
      }}>
        <div>
          {eyebrow && (
            <p style={{
              fontSize: 10,
              fontFamily: "'Inter', monospace",
              textTransform: 'uppercase',
              letterSpacing: '0.14em',
              color: 'var(--muted-foreground)',
              marginBottom: 10,
              fontWeight: 600,
            }}>
              {eyebrow}
            </p>
          )}
          <h1 style={{
            fontSize: 30,
            fontFamily: 'Georgia, serif',
            fontWeight: 500,
            letterSpacing: '-0.035em',
            lineHeight: 1.15,
            marginBottom: description ? 10 : 0,
            color: 'var(--foreground)',
          }}>
            {title}
          </h1>
          {description && (
            <p style={{
              fontSize: 13,
              color: 'var(--muted-foreground)',
              maxWidth: 560,
              lineHeight: 1.65,
            }}>
              {description}
            </p>
          )}
        </div>
        {action && <div>{action}</div>}
      </div>
      {children}
    </div>
  )
}
