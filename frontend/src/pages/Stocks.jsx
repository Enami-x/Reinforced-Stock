import { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Search, TrendingUp, Plus, Minus, CheckCircle, LayoutGrid, List } from 'lucide-react'
import {
  fetchWatchlist,
  fetchAvailableTickers,
  addToWatchlist,
  removeFromWatchlist,
} from '../lib/api'
import { PageFrame } from '../components/Layout'
import LoadingSpinner from '../components/LoadingSpinner'

// ── Sector colors (Light Theme Palette) ──────────────────────────────────────
const SECTOR_COLORS = {
  Technology:     { bg: '#eff6ff', accent: '#2563eb', border: '#bfdbfe' },
  Automotive:     { bg: '#fffbeb', accent: '#b45309', border: '#fde68a' },
  Finance:        { bg: '#ecfdf5', accent: '#047857', border: '#a7f3d0' },
  Healthcare:     { bg: '#fef2f2', accent: '#b91c1c', border: '#fecaca' },
  Energy:         { bg: '#fff7ed', accent: '#c2410c', border: '#fed7aa' },
  Consumer:       { bg: '#fdf2f8', accent: '#be185d', border: '#fbcfe8' },
  ETF:            { bg: '#f5f3ff', accent: '#6d28d9', border: '#ddd6fe' },
  Semiconductors: { bg: '#ecfeff', accent: '#0e7490', border: '#a5f3fc' },
  Cloud:          { bg: '#f0f9ff', accent: '#0369a1', border: '#bae6fd' },
  Industrials:    { bg: '#f8fafc', accent: '#475569', border: '#cbd5e1' },
  Telecom:        { bg: '#faf5ff', accent: '#7c3aed', border: '#e9d5ff' },
  Custom:         { bg: 'oklch(0.52 0.15 65 / 8%)',  accent: 'var(--primary)', border: 'oklch(0.52 0.15 65 / 30%)' },
}

function TickerCard({ ticker, name, sector, market, inWatchlist, onAdd, onRemove, onView, isPending }) {
  const colors = SECTOR_COLORS[sector] || SECTOR_COLORS.Custom
  const [hovered, setHovered] = useState(false)
  const mkt = market || (ticker.endsWith('.NS') ? 'NSE' : ticker.endsWith('.BO') ? 'BSE' : 'US')

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        border: `1px solid ${inWatchlist ? (colors.border || colors.accent + '44') : hovered ? colors.accent + '55' : 'var(--border)'}`,
        background: inWatchlist ? colors.bg : 'var(--glass-bg)',
        backdropFilter: 'blur(12px)',
        padding: '18px',
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        transition: 'all 250ms cubic-bezier(0.22, 1, 0.36, 1)',
        cursor: 'default',
        position: 'relative',
        overflow: 'hidden',
        borderRadius: 'var(--radius)',
        transform: hovered ? 'translateY(-3px)' : 'translateY(0)',
        boxShadow: hovered ? '0 10px 25px -5px rgba(0, 0, 0, 0.08), 0 8px 10px -6px rgba(0, 0, 0, 0.03)' : '0 1px 3px rgba(0, 0, 0, 0.03)',
      }}
    >
      {/* sector accent line */}
      <div style={{
        position: 'absolute', top: 0, left: 0, right: 0, height: 2,
        background: `linear-gradient(90deg, transparent, ${colors.accent}, transparent)`,
        opacity: inWatchlist ? 0.8 : hovered ? 0.5 : 0,
        transition: 'opacity 250ms ease',
      }} />

      {/* header row */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <div style={{
            fontFamily: "'Inter', monospace",
            fontWeight: 800,
            fontSize: 17,
            color: 'var(--foreground)',
            letterSpacing: '0.05em',
          }}>
            {ticker}
          </div>
          <div style={{ fontSize: 11, color: 'var(--muted-foreground)', marginTop: 3, lineHeight: 1.3, fontWeight: 500 }}>
            {name}
          </div>
        </div>
        {inWatchlist && (
          <CheckCircle size={14} color={colors.accent} style={{ flexShrink: 0, marginTop: 2, opacity: 0.9 }} />
        )}
      </div>

      {/* badges row */}
      <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
        <div style={{
          fontSize: 9,
          fontWeight: 700,
          padding: '2px 7px',
          background: mkt === 'US' ? '#eff6ff' : mkt === 'NSE' ? '#fef3c7' : '#f3e8ff',
          color: mkt === 'US' ? '#1d4ed8' : mkt === 'NSE' ? '#b45309' : '#7e22ce',
          border: `1px solid ${mkt === 'US' ? '#bfdbfe' : mkt === 'NSE' ? '#fde68a' : '#e9d5ff'}`,
          borderRadius: 3,
          letterSpacing: '0.04em',
          display: 'inline-flex',
          alignItems: 'center',
          gap: 4,
        }}>
          {mkt === 'US' ? '🇺🇸 US' : mkt === 'NSE' ? '🇮🇳 NSE' : '🇮🇳 BSE'}
        </div>

        <div style={{
          fontSize: 9,
          fontWeight: 700,
          padding: '3px 8px',
          background: colors.accent + '15',
          color: colors.accent,
          letterSpacing: '0.05em',
          textTransform: 'uppercase',
          borderRadius: 3,
        }}>
          {sector}
        </div>
      </div>

      {/* action buttons */}
      <div style={{ display: 'flex', gap: 6, marginTop: 4 }}>
        <button
          onClick={() => onView(ticker)}
          style={{
            flex: 1,
            border: '1px solid var(--border)',
            background: 'transparent',
            color: 'var(--foreground)',
            fontSize: 11,
            fontWeight: 600,
            padding: '7px 0',
            cursor: 'pointer',
            transition: 'all 200ms cubic-bezier(0.22, 1, 0.36, 1)',
            borderRadius: 3,
          }}
          onMouseEnter={e => {
            e.currentTarget.style.background = 'rgba(0, 0, 0, 0.035)'
            e.currentTarget.style.borderColor = 'var(--border-hover)'
          }}
          onMouseLeave={e => {
            e.currentTarget.style.background = 'transparent'
            e.currentTarget.style.borderColor = 'var(--border)'
          }}
        >
          Analyze →
        </button>

        {inWatchlist ? (
          <button
            onClick={() => onRemove(ticker)}
            disabled={isPending}
            title="Remove from watchlist"
            style={{
              border: `1px solid ${colors.accent}55`,
              background: colors.accent + '18',
              color: colors.accent,
              padding: '7px 10px',
              cursor: isPending ? 'not-allowed' : 'pointer',
              opacity: isPending ? 0.5 : 1,
              display: 'flex', alignItems: 'center',
              transition: 'all 200ms ease',
              borderRadius: 3,
            }}
          >
            <Minus size={13} />
          </button>
        ) : (
          <button
            onClick={() => onAdd(ticker)}
            disabled={isPending}
            title="Add to watchlist"
            style={{
              border: '1px solid var(--border)',
              background: 'transparent',
              color: 'var(--muted-foreground)',
              padding: '7px 10px',
              cursor: isPending ? 'not-allowed' : 'pointer',
              opacity: isPending ? 0.5 : 1,
              display: 'flex', alignItems: 'center',
              transition: 'all 200ms cubic-bezier(0.22, 1, 0.36, 1)',
              borderRadius: 3,
            }}
            onMouseEnter={e => {
              e.currentTarget.style.borderColor = colors.accent
              e.currentTarget.style.color = colors.accent
            }}
            onMouseLeave={e => {
              e.currentTarget.style.borderColor = 'var(--border)'
              e.currentTarget.style.color = 'var(--muted-foreground)'
            }}
          >
            <Plus size={13} />
          </button>
        )}
      </div>
    </div>
  )
}

export default function Stocks() {
  const navigate = useNavigate()
  const qc = useQueryClient()

  const [search, setSearch] = useState('')
  const [activeMarket, setActiveMarket] = useState('All') // 'All' | 'US' | 'NSE' | 'BSE'
  const [activeSector, setActiveSector] = useState('All')
  const [tab, setTab] = useState('browse') // 'browse' | 'watchlist'
  const [customDraft, setCustomDraft] = useState('')

  // ── Queries ─────────────────────────────────────────────────────────────────
  const { data: watchlistData, isLoading: wlLoading } = useQuery({
    queryKey: ['watchlist'],
    queryFn: fetchWatchlist,
    refetchInterval: 30_000,
  })

  const { data: catalogData, isLoading: catLoading } = useQuery({
    queryKey: ['available-tickers'],
    queryFn: fetchAvailableTickers,
    staleTime: Infinity,   // catalog never changes at runtime
  })

  const watchlistSet = useMemo(
    () => new Set((watchlistData?.tickers) || []),
    [watchlistData]
  )

  // ── Mutations ────────────────────────────────────────────────────────────────
  const [pendingTicker, setPendingTicker] = useState(null)

  const addMutation = useMutation({
    mutationFn: addToWatchlist,
    onMutate: (t) => setPendingTicker(t),
    onSettled: () => { setPendingTicker(null); qc.invalidateQueries({ queryKey: ['watchlist'] }) },
  })

  const removeMutation = useMutation({
    mutationFn: removeFromWatchlist,
    onMutate: (t) => setPendingTicker(t),
    onSettled: () => { setPendingTicker(null); qc.invalidateQueries({ queryKey: ['watchlist'] }) },
  })

  // ── Catalog data ─────────────────────────────────────────────────────────────
  const sectors = catalogData ? Object.keys(catalogData.sectors) : []
  const allCatalogTickers = catalogData
    ? Object.entries(catalogData.sectors).flatMap(([sector, tickers]) =>
        tickers.map(t => ({
          ...t,
          sector,
          market: t.market || (t.ticker.endsWith('.NS') ? 'NSE' : t.ticker.endsWith('.BO') ? 'BSE' : 'US'),
        }))
      )
    : []

  const filtered = useMemo(() => {
    let list = allCatalogTickers
    if (activeMarket !== 'All') list = list.filter(t => t.market === activeMarket)
    if (activeSector !== 'All') list = list.filter(t => t.sector === activeSector)
    if (search.trim()) {
      const q = search.trim().toUpperCase()
      list = list.filter(
        t => t.ticker.includes(q) || t.name.toUpperCase().includes(q) || t.sector.toUpperCase().includes(q) || t.market.toUpperCase().includes(q)
      )
    }
    return list
  }, [allCatalogTickers, activeMarket, activeSector, search])

  // ── Custom ticker add ─────────────────────────────────────────────────────────
  const addCustom = () => {
    const t = customDraft.trim().toUpperCase()
    if (t) { addMutation.mutate(t); setCustomDraft('') }
  }

  // ── Watchlist tab content ─────────────────────────────────────────────────────
  const watchlistEnriched = watchlistData?.watchlist || []

  return (
    <PageFrame
      eyebrow="Stocks"
      title="Your Watchlist."
      description="Browse 280+ popular tickers across US (NYSE/NASDAQ), Indian NSE, and BSE markets to build your watchlist."
    >
      {/* ── Tabs ────────────────────────────────────────────────────────── */}
      <div style={{ display: 'flex', gap: 0, marginBottom: 30, borderBottom: '1px solid var(--border)', position: 'relative' }}>
        {[
          { key: 'browse', label: 'Browse catalog', Icon: LayoutGrid },
          { key: 'watchlist', label: `My watchlist (${watchlistData?.count ?? '…'})`, Icon: TrendingUp },
        ].map(({ key, label, Icon }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            style={{
              padding: '10px 22px',
              border: 'none',
              background: 'transparent',
              color: tab === key ? 'var(--primary)' : 'var(--muted-foreground)',
              fontWeight: 600,
              fontSize: 13,
              cursor: 'pointer',
              transition: 'all 220ms ease',
              letterSpacing: '0.01em',
              display: 'flex',
              alignItems: 'center',
              gap: 7,
              borderBottom: tab === key ? '2px solid var(--primary)' : '2px solid transparent',
              marginBottom: -1,
            }}
            onMouseEnter={e => {
              if (tab !== key) e.currentTarget.style.color = 'var(--foreground)'
            }}
            onMouseLeave={e => {
              if (tab !== key) e.currentTarget.style.color = 'var(--muted-foreground)'
            }}
          >
            <Icon size={13} />
            {label}
          </button>
        ))}
      </div>

      {/* ══════════════════════════════════════════════════════════════════════ */}
      {/* BROWSE TAB                                                            */}
      {/* ══════════════════════════════════════════════════════════════════════ */}
      {tab === 'browse' && (
        <>
          {/* Search + Market + Sector filters */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14, marginBottom: 22 }}>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
              <div style={{ position: 'relative', flex: '1 1 240px', maxWidth: 340 }}>
                <Search size={14} style={{ position: 'absolute', left: 14, top: '50%', transform: 'translateY(-50%)', color: 'var(--muted-foreground)' }} />
                <input
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  placeholder="Search ticker, company, or sector…"
                  style={{
                    width: '100%',
                    border: '1px solid var(--border)',
                    background: 'var(--input)',
                    padding: '10px 14px 10px 38px',
                    fontSize: 13,
                    outline: 'none',
                    color: 'var(--foreground)',
                    boxSizing: 'border-box',
                    borderRadius: 'var(--radius)',
                    transition: 'all 200ms ease',
                  }}
                />
              </div>

              {/* Market filter tabs/pills */}
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                {[
                  { key: 'All', label: 'All Markets', flag: '🌐' },
                  { key: 'US', label: 'US (NYSE/NASDAQ)', flag: '🇺🇸' },
                  { key: 'NSE', label: 'India (NSE)', flag: '🇮🇳' },
                  { key: 'BSE', label: 'India (BSE)', flag: '🇮🇳' },
                ].map(m => (
                  <button
                    key={m.key}
                    onClick={() => setActiveMarket(m.key)}
                    style={{
                      padding: '7px 14px',
                      fontSize: 11,
                      fontWeight: 700,
                      border: '1px solid',
                      borderColor: activeMarket === m.key ? 'var(--primary)' : 'var(--border)',
                      background: activeMarket === m.key ? 'var(--primary)' : 'var(--glass-bg)',
                      color: activeMarket === m.key ? 'var(--primary-foreground)' : 'var(--foreground)',
                      cursor: 'pointer',
                      borderRadius: 'var(--radius)',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 6,
                      transition: 'all 200ms ease',
                    }}
                  >
                    <span>{m.flag}</span>
                    <span>{m.label}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Sector filter pills */}
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
              <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--muted-foreground)', marginRight: 4 }}>Sector:</span>
              {['All', ...sectors].map(s => (
                <button
                  key={s}
                  onClick={() => setActiveSector(s)}
                  style={{
                    padding: '5px 12px',
                    fontSize: 10,
                    fontWeight: 600,
                    border: '1px solid var(--border)',
                    background: activeSector === s ? 'var(--primary)' : 'transparent',
                    color: activeSector === s ? 'var(--primary-foreground)' : 'var(--muted-foreground)',
                    cursor: 'pointer',
                    transition: 'all 200ms cubic-bezier(0.22, 1, 0.36, 1)',
                    letterSpacing: '0.04em',
                    textTransform: 'uppercase',
                    borderRadius: 3,
                    borderColor: activeSector === s ? 'var(--primary)' : 'var(--border)',
                  }}
                  onMouseEnter={e => {
                    if (activeSector !== s) {
                      e.currentTarget.style.borderColor = 'var(--border-hover)'
                      e.currentTarget.style.color = 'var(--foreground)'
                    }
                  }}
                  onMouseLeave={e => {
                    if (activeSector !== s) {
                      e.currentTarget.style.borderColor = 'var(--border)'
                      e.currentTarget.style.color = 'var(--muted-foreground)'
                    }
                  }}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>

          {/* Results count */}
          <div style={{ fontSize: 12, color: 'var(--muted-foreground)', marginBottom: 16, fontWeight: 500 }}>
            {filtered.length} tickers
            {activeMarket !== 'All' && ` in ${activeMarket === 'US' ? 'US Markets' : activeMarket === 'NSE' ? 'Indian NSE' : 'Indian BSE'}`}
            {activeSector !== 'All' && ` • ${activeSector}`}
            {search && ` matching "${search}"`}
          </div>

          {/* Grid */}
          {catLoading ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: 60 }}>
              <LoadingSpinner />
            </div>
          ) : (
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(210px, 1fr))',
              gap: 12,
            }}>
              {filtered.map(item => (
                <TickerCard
                  key={item.ticker}
                  ticker={item.ticker}
                  name={item.name}
                  sector={item.sector}
                  market={item.market}
                  inWatchlist={watchlistSet.has(item.ticker)}
                  isPending={pendingTicker === item.ticker}
                  onView={t => navigate(`/stocks/${t}`)}
                  onAdd={t => addMutation.mutate(t)}
                  onRemove={t => removeMutation.mutate(t)}
                />
              ))}
              {filtered.length === 0 && (
                <div style={{ gridColumn: '1/-1', textAlign: 'center', padding: 48, color: 'var(--muted-foreground)', fontSize: 14, fontWeight: 500 }}>
                  No tickers match your search.
                </div>
              )}
            </div>
          )}

          {/* Custom ticker add */}
          <div style={{ marginTop: 40, borderTop: '1px solid var(--border)', paddingTop: 28 }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>Add a custom ticker</div>
            <div style={{ display: 'flex', gap: 8 }}>
              <input
                value={customDraft}
                onChange={e => setCustomDraft(e.target.value.toUpperCase())}
                onKeyDown={e => e.key === 'Enter' && addCustom()}
                placeholder="e.g. BABA, RELIANCE.NS, TCS.BO…"
                style={{
                  border: '1px solid var(--border)',
                  background: 'var(--input)',
                  padding: '10px 16px',
                  fontSize: 13,
                  fontFamily: "'Inter', monospace",
                  fontWeight: 700,
                  outline: 'none',
                  color: 'var(--foreground)',
                  width: 260,
                  borderRadius: 'var(--radius)',
                  transition: 'all 200ms ease',
                  letterSpacing: '0.04em',
                }}
              />
              <button
                onClick={addCustom}
                disabled={!customDraft.trim() || addMutation.isPending}
                style={{
                  background: 'var(--primary)',
                  color: 'var(--primary-foreground)',
                  border: 'none',
                  padding: '10px 24px',
                  fontSize: 13,
                  fontWeight: 700,
                  cursor: customDraft.trim() ? 'pointer' : 'not-allowed',
                  opacity: !customDraft.trim() ? 0.5 : 1,
                  display: 'flex', alignItems: 'center', gap: 6,
                  transition: 'all 200ms cubic-bezier(0.22, 1, 0.36, 1)',
                  borderRadius: 'var(--radius)',
                }}
              >
                <Plus size={14} />
                Add to watchlist
              </button>
            </div>
            {addMutation.isError && (
              <p style={{ fontSize: 11, color: 'var(--destructive)', marginTop: 8, fontWeight: 500 }}>
                {addMutation.error?.message}
              </p>
            )}
          </div>
        </>
      )}

      {/* ══════════════════════════════════════════════════════════════════════ */}
      {/* WATCHLIST TAB                                                         */}
      {/* ══════════════════════════════════════════════════════════════════════ */}
      {tab === 'watchlist' && (
        <>
          {wlLoading ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: 60 }}>
              <LoadingSpinner />
            </div>
          ) : watchlistEnriched.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 60 }}>
              <TrendingUp size={36} color="var(--muted-foreground)" style={{ marginBottom: 16, opacity: 0.5 }} />
              <p style={{ color: 'var(--muted-foreground)', fontSize: 14, fontWeight: 500 }}>
                Your watchlist is empty.
              </p>
              <button
                onClick={() => setTab('browse')}
                style={{
                  marginTop: 20,
                  background: 'var(--primary)',
                  color: 'var(--primary-foreground)',
                  border: 'none',
                  padding: '11px 28px',
                  fontWeight: 700,
                  cursor: 'pointer',
                  fontSize: 13,
                  borderRadius: 'var(--radius)',
                  transition: 'all 200ms ease',
                }}
              >
                Browse catalog →
              </button>
            </div>
          ) : (
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(210px, 1fr))',
              gap: 12,
            }}>
              {watchlistEnriched.map(item => (
                <TickerCard
                  key={item.ticker}
                  ticker={item.ticker}
                  name={item.name}
                  sector={item.sector}
                  market={item.market}
                  inWatchlist={true}
                  isPending={pendingTicker === item.ticker}
                  onView={t => navigate(`/stocks/${t}`)}
                  onAdd={t => addMutation.mutate(t)}
                  onRemove={t => removeMutation.mutate(t)}
                />
              ))}
            </div>
          )}
        </>
      )}
    </PageFrame>
  )
}
