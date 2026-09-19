import { useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'

// ── Math & Easing Helpers ───────────────────────────────────────────────────
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v))
const lerp = (a, b, t) => a + (b - a) * t
const invlerp = (a, b, v) => clamp((v - a) / (b - a), 0, 1)
const easeInOut = (t) => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2)
const easeOutQuad = (t) => 1 - (1 - t) * (1 - t)
const easeInQuad = (t) => t * t

// ── Precise Mountain Ridgeline Path (in 1024x731 artwork coordinates) ─────────
// Traced exactly along the artwork's snow-capped peaks and ridges
const MOUNTAIN_SVG_PATH =
  'M -40,410 L 40,390 L 110,370 L 165,376 L 228,314 L 285,354 L 345,318 ' +
  'L 426,223 L 452,245 L 498,191 L 532,241 L 570,311 L 653,289 L 700,322 ' +
  'L 778,296 L 830,329 L 886,300 L 947,344 L 1060,387'

// Peak beacons positioned on summits
const PEAK_BEACONS = [
  { cx: 228, cy: 314, threshold: 0.18, label: 'Initiation' },
  { cx: 426, cy: 223, threshold: 0.44, label: 'Momentum' },
  { cx: 498, cy: 191, threshold: 0.54, label: 'Apex Summit' },
  { cx: 653, cy: 289, threshold: 0.71, label: 'Convergence' },
  { cx: 778, cy: 296, threshold: 0.83, label: 'Target' },
  { cx: 886, cy: 300, threshold: 0.94, label: 'Resolution' },
]

export default function Landing() {
  const navigate = useNavigate()
  const wrapRef = useRef(null)
  const heroScrollRef = useRef(null)
  const stickyRef = useRef(null)
  const svgSceneRef = useRef(null)
  const heroTextRef = useRef(null)
  const captionRef = useRef(null)
  const graphGroupRef = useRef(null)
  const pathRef = useRef(null)
  const haloPathRef = useRef(null)
  const beaconRefs = useRef([])
  const treesContainerRef = useRef(null)
  const forestWipeRef = useRef(null)
  const scrollHintRef = useRef(null)
  const rafRef = useRef(null)

  const prefersReduced =
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches

  // ── Scroll progression frame handler ─────────────────────────────────────────
  const updateScroll = useCallback(() => {
    const heroScroll = heroScrollRef.current
    if (!heroScroll) return

    const scrollY = window.scrollY
    const stickyDistance = heroScroll.offsetHeight - window.innerHeight
    if (stickyDistance <= 0) return

    // Normalized progress 0.00 → 1.00 over the sticky span
    const prog = clamp(scrollY / stickyDistance, 0, 1)

    // ── DYNAMIC CAMERA VIEWBOX (Unified Artwork + Mountain Lock) ─────────────
    // Artwork size is 1024 x 731.
    // In ultra-wide screens, visible height in artwork units is 1024 / aspect.
    const winW = window.innerWidth || 1280
    const winH = window.innerHeight || 720
    const aspect = winW / winH

    let baseViewH = 731
    let yBottomAlign = 0
    let yTopAlign = 0

    if (aspect > 1024 / 731) {
      // Screen is wider than image: width fits, height is sliced
      baseViewH = clamp(1024 / aspect, 320, 731)
      yBottomAlign = 731 - baseViewH // Show bottom (character, flowers, meadow)
      yTopAlign = clamp(191 - baseViewH * 0.22, 0, yBottomAlign) // Frame summits
    } else {
      // Screen is taller than image: height fits, width is sliced
      baseViewH = 731
      yBottomAlign = 0
      yTopAlign = 0
    }

    if (svgSceneRef.current && !prefersReduced) {
      // Camera tilt:
      // Stage 1 - 3 (0.00 → 0.55): Framed to showcase the traveler, dog, and wildflowers
      // Stage 4 (0.58 → 0.85): Smoothly tilts up to frame the majestic peaks as line draws
      const tiltProg = easeInOut(invlerp(0.56, 0.72, prog))
      const curViewY = lerp(yBottomAlign, yTopAlign, tiltProg)
      svgSceneRef.current.setAttribute('viewBox', `0 ${curViewY} 1024 ${baseViewH}`)
    }

    // ── SCROLL PROMPT HINT (Fades out immediately upon scrolling) ────────────
    if (scrollHintRef.current) {
      const hintOp = 1 - invlerp(0.01, 0.08, prog)
      scrollHintRef.current.style.opacity = hintOp
      scrollHintRef.current.style.pointerEvents = hintOp > 0.05 ? 'auto' : 'none'
    }

    // ── STAGE 2: HERO TEXT (0.16 → 0.44) ─────────────────────────────────────
    if (heroTextRef.current) {
      const inP = easeInOut(invlerp(0.16, 0.26, prog))
      const outP = easeInOut(invlerp(0.36, 0.45, prog))
      const op = clamp(inP - outP, 0, 1)
      const ty = prefersReduced ? 0 : lerp(28, 0, inP) + lerp(0, -20, outP)
      heroTextRef.current.style.opacity = op
      heroTextRef.current.style.transform = `translate3d(0, ${ty}px, 0)`
      heroTextRef.current.style.pointerEvents = op > 0.1 ? 'auto' : 'none'
    }

    // ── STAGE 3: UNDERSTATED CAPTION (0.47 → 0.63) ───────────────────────────
    if (captionRef.current) {
      const inP = easeInOut(invlerp(0.47, 0.54, prog))
      const outP = easeInOut(invlerp(0.59, 0.65, prog))
      const op = clamp(inP - outP, 0, 1)
      const ty = prefersReduced ? 0 : lerp(16, 0, inP) + lerp(0, -14, outP)
      captionRef.current.style.opacity = op
      captionRef.current.style.transform = `translate3d(-50%, ${ty}px, 0)`
      captionRef.current.style.pointerEvents = 'none'
    }

    // ── STAGE 4: GLOWING MOUNTAIN GRAPH LINE (0.64 → 0.85) ───────────────────
    if (pathRef.current && !prefersReduced) {
      const totalLen = pathRef.current.getTotalLength?.() || 1200
      const lineProg = invlerp(0.64, 0.84, prog)
      const drawnOffset = totalLen * (1 - easeInOut(lineProg))

      pathRef.current.style.strokeDashoffset = drawnOffset
      if (haloPathRef.current) {
        haloPathRef.current.style.strokeDashoffset = drawnOffset
      }

      // Summit peak beacons ignite when line arrives
      beaconRefs.current.forEach((el, idx) => {
        if (!el) return
        const beacon = PEAK_BEACONS[idx]
        const beaconP = invlerp(beacon.threshold - 0.025, beacon.threshold + 0.025, lineProg)
        const bEase = easeOutQuad(beaconP)
        el.style.opacity = bEase
        el.style.transform = `scale(${lerp(0.2, 1.0, bEase)})`
      })
    }

    // Graph group visibility (fades in cleanly at 0.63, fades out into forest at 0.86)
    if (graphGroupRef.current) {
      const graphIn = invlerp(0.63, 0.66, prog)
      const graphOut = invlerp(0.85, 0.90, prog)
      const op = clamp(graphIn - graphOut, 0, 1)
      graphGroupRef.current.style.opacity = op
    }

    // ── STAGE 5: FOREST & TREE TRANSITION (0.83 → 1.00) ──────────────────────
    if (treesContainerRef.current && !prefersReduced) {
      const treeProg = invlerp(0.83, 0.96, prog)
      treesContainerRef.current.style.opacity = treeProg > 0.01 ? 1 : 0

      // Natural camera dollies into the forest
      const treeElements = treesContainerRef.current.querySelectorAll('.tree-node')
      treeElements.forEach((el) => {
        const speed = parseFloat(el.dataset.speed || '1.0')
        const startX = parseFloat(el.dataset.startX || '0')
        const endX = parseFloat(el.dataset.endX || '0')
        const startY = parseFloat(el.dataset.startY || '0')
        const endY = parseFloat(el.dataset.endY || '0')
        const baseScale = parseFloat(el.dataset.baseScale || '1.0')
        const targetScale = parseFloat(el.dataset.targetScale || '3.0')

        const localT = easeInOut(clamp(treeProg * speed, 0, 1))
        const curX = lerp(startX, endX, localT)
        const curY = lerp(startY, endY, localT)
        const curScale = lerp(baseScale, targetScale, localT)

        el.style.transform = `translate3d(${curX}px, ${curY}px, 0) scale(${curScale})`
      })
    }

    // Pure black forest canopy fill: fully covers viewport from 0.94 → 1.00
    if (forestWipeRef.current) {
      const wipeProg = easeInQuad(invlerp(0.91, 0.96, prog))
      forestWipeRef.current.style.opacity = wipeProg
    }
  }, [prefersReduced])

  useEffect(() => {
    if (pathRef.current) {
      const len = pathRef.current.getTotalLength?.() || 1200
      pathRef.current.style.strokeDasharray = len
      pathRef.current.style.strokeDashoffset = len
      if (haloPathRef.current) {
        haloPathRef.current.style.strokeDasharray = len
        haloPathRef.current.style.strokeDashoffset = len
      }
    }

    const onScroll = () => {
      cancelAnimationFrame(rafRef.current)
      rafRef.current = requestAnimationFrame(updateScroll)
    }

    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll, { passive: true })
    updateScroll()

    return () => {
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', onScroll)
      cancelAnimationFrame(rafRef.current)
    }
  }, [updateScroll])

  if (prefersReduced) {
    return <AccessibleLanding navigate={navigate} />
  }

  return (
    <div ref={wrapRef} style={{ position: 'relative', background: '#f8faf9' }}>
      {/* ── CINEMATIC STICKY CONTAINER (560vh scroll span) ────────────────── */}
      <div ref={heroScrollRef} style={{ height: '560vh', position: 'relative' }}>
        <div
          ref={stickyRef}
          style={{
            position: 'sticky',
            top: 0,
            width: '100%',
            height: '100vh',
            overflow: 'hidden',
            background: '#f8faf9',
          }}
        >
          {/* ── TOP NAV BAR ──────────────────────────────────────────────── */}
          <nav
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              zIndex: 35,
              padding: '24px 36px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              background: 'linear-gradient(to bottom, rgba(0,0,0,0.4), transparent)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <svg width="24" height="24" viewBox="0 0 28 28" fill="none">
                <path
                  d="M2 14 Q5 8 8 14 Q11 20 14 14 Q17 8 20 14 Q23 20 26 14"
                  stroke="white"
                  strokeWidth="2.4"
                  fill="none"
                  strokeLinecap="round"
                />
              </svg>
              <span
                style={{
                  fontFamily: 'Georgia, serif',
                  fontSize: 16,
                  fontWeight: 600,
                  color: 'white',
                  letterSpacing: '-0.01em',
                  textShadow: '0 2px 10px rgba(0,0,0,0.6)',
                }}
              >
                Stock Insight Agent
              </span>
            </div>

            <div style={{ display: 'flex', gap: 14 }}>
              <button
                onClick={() => navigate('/stocks')}
                style={{
                  background: 'rgba(255,255,255,0.12)',
                  border: '1px solid rgba(255,255,255,0.4)',
                  backdropFilter: 'blur(8px)',
                  padding: '8px 18px',
                  fontSize: 12,
                  fontWeight: 600,
                  cursor: 'pointer',
                  color: 'white',
                  borderRadius: 4,
                  letterSpacing: '0.03em',
                  transition: 'all 200ms',
                }}
                onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(255,255,255,0.22)')}
                onMouseLeave={(e) => (e.currentTarget.style.background = 'rgba(255,255,255,0.12)')}
              >
                Catalog
              </button>
              <button
                onClick={() => navigate('/dashboard')}
                style={{
                  background: 'white',
                  border: 'none',
                  padding: '8px 20px',
                  fontSize: 12,
                  fontWeight: 700,
                  cursor: 'pointer',
                  color: '#111b11',
                  borderRadius: 4,
                  boxShadow: '0 2px 14px rgba(0,0,0,0.25)',
                  letterSpacing: '0.02em',
                  transition: 'all 200ms',
                }}
                onMouseEnter={(e) => (e.currentTarget.style.transform = 'translateY(-1px)')}
                onMouseLeave={(e) => (e.currentTarget.style.transform = 'translateY(0)')}
              >
                Open Dashboard →
              </button>
            </div>
          </nav>

          {/* ── UNIFIED SVG VIEWPORT (Artwork + Mountain Line in Identical DOM) ── */}
          <svg
            ref={svgSceneRef}
            viewBox="0 0 1024 731"
            preserveAspectRatio="xMidYMid slice"
            style={{
              position: 'absolute',
              inset: 0,
              width: '100%',
              height: '100%',
              userSelect: 'none',
            }}
          >
            <defs>
              {/* Soft warm gold bloom filter */}
              <filter id="gold-bloom" x="-30%" y="-30%" width="160%" height="160%">
                <feGaussianBlur stdDeviation="3.2" result="blur1" />
                <feGaussianBlur stdDeviation="1.0" result="blur2" />
                <feMerge>
                  <feMergeNode in="blur1" />
                  <feMergeNode in="blur2" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>

              {/* Summit node beacon halo */}
              <filter id="beacon-glow" x="-80%" y="-80%" width="260%" height="260%">
                <feGaussianBlur stdDeviation="4.0" result="flare" />
                <feMerge>
                  <feMergeNode in="flare" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
            </defs>

            {/* BASE ARTWORK: Exactly 1024x731 in SVG coordinates */}
            <image
              href="/hero.jpg"
              x="0"
              y="0"
              width="1024"
              height="731"
              preserveAspectRatio="none"
            />

            {/* ── STAGE 4: GLOWING MOUNTAIN GRAPH LINE ─────────────────────── */}
            <g ref={graphGroupRef} style={{ opacity: 0, willChange: 'opacity' }}>
              {/* Understated warm halo track */}
              <path
                ref={haloPathRef}
                d={MOUNTAIN_SVG_PATH}
                stroke="rgba(255, 230, 140, 0.35)"
                strokeWidth="7"
                strokeLinecap="round"
                strokeLinejoin="round"
                fill="none"
                style={{ filter: 'blur(3px)', willChange: 'stroke-dashoffset' }}
              />

              {/* Primary glowing ridge line */}
              <path
                ref={pathRef}
                d={MOUNTAIN_SVG_PATH}
                stroke="rgba(255, 252, 240, 0.95)"
                strokeWidth="2.6"
                strokeLinecap="round"
                strokeLinejoin="round"
                fill="none"
                filter="url(#gold-bloom)"
                style={{ willChange: 'stroke-dashoffset' }}
              />

              {/* Summit Peak Beacons */}
              {PEAK_BEACONS.map((beacon, idx) => (
                <g
                  key={beacon.threshold}
                  ref={(el) => (beaconRefs.current[idx] = el)}
                  style={{
                    transformOrigin: `${beacon.cx}px ${beacon.cy}px`,
                    opacity: 0,
                    willChange: 'transform, opacity',
                  }}
                >
                  <circle
                    cx={beacon.cx}
                    cy={beacon.cy}
                    r="11"
                    fill="rgba(255, 235, 160, 0.22)"
                    filter="url(#beacon-glow)"
                  />
                  <circle
                    cx={beacon.cx}
                    cy={beacon.cy}
                    r="5"
                    fill="rgba(255, 245, 200, 0.8)"
                  />
                  <circle
                    cx={beacon.cx}
                    cy={beacon.cy}
                    r="2.6"
                    fill="#ffffff"
                  />
                </g>
              ))}
            </g>
          </svg>

          {/* Subtle atmospheric vignette */}
          <div
            style={{
              position: 'absolute',
              inset: 0,
              pointerEvents: 'none',
              background:
                'radial-gradient(ellipse at 50% 50%, transparent 62%, rgba(10,25,20,0.22) 100%)',
            }}
          />

          {/* ── STAGE 2: HERO TEXT (Left Slope Breathing Room) ───────────── */}
          <div
            ref={heroTextRef}
            style={{
              position: 'absolute',
              left: 'clamp(32px, 8vw, 110px)',
              top: 'clamp(20%, 28vh, 34%)',
              maxWidth: 540,
              opacity: 0,
              willChange: 'opacity, transform',
              zIndex: 20,
              pointerEvents: 'none',
            }}
          >
            <div
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 8,
                padding: '5px 12px',
                borderRadius: 20,
                background: 'rgba(255,255,255,0.18)',
                backdropFilter: 'blur(10px)',
                border: '1px solid rgba(255,255,255,0.3)',
                marginBottom: 16,
              }}
            >
              <span
                style={{
                  width: 6,
                  height: 6,
                  borderRadius: '50%',
                  background: '#a3f3a7',
                  boxShadow: '0 0 8px #a3f3a7',
                }}
              />
              <span
                style={{
                  fontFamily: 'monospace',
                  fontSize: 10,
                  letterSpacing: '0.14em',
                  textTransform: 'uppercase',
                  color: 'rgba(255,255,255,0.95)',
                  fontWeight: 600,
                }}
              >
                Self-Improving Financial AI
              </span>
            </div>

            <h1
              style={{
                fontFamily: 'Georgia, serif',
                fontSize: 'clamp(38px, 5.2vw, 64px)',
                fontWeight: 500,
                lineHeight: 1.12,
                color: '#ffffff',
                letterSpacing: '-0.03em',
                margin: '0 0 18px 0',
                textShadow:
                  '0 2px 28px rgba(10,25,15,0.65), 0 1px 4px rgba(0,0,0,0.5)',
              }}
            >
              Predict.
              <br />
              Learn.
              <br />
              Outperform.
            </h1>

            <p
              style={{
                fontFamily: 'system-ui, sans-serif',
                fontSize: 'clamp(14px, 1.4vw, 17px)',
                fontWeight: 400,
                lineHeight: 1.65,
                color: 'rgba(255,255,255,0.92)',
                margin: '0 0 28px 0',
                maxWidth: 420,
                textShadow: '0 1px 16px rgba(0,0,0,0.55)',
              }}
            >
              An intelligent stock analysis agent that generates high-conviction
              signals, audits its predictions after 5 trading days, and continually
              refines its strategy.
            </p>

            <div style={{ display: 'flex', gap: 14, alignItems: 'center' }}>
              <button
                onClick={() => navigate('/dashboard')}
                style={{
                  background: '#ffffff',
                  color: '#132115',
                  border: 'none',
                  padding: '12px 28px',
                  fontSize: 13,
                  fontWeight: 700,
                  borderRadius: 4,
                  cursor: 'pointer',
                  letterSpacing: '0.02em',
                  boxShadow: '0 4px 20px rgba(0,0,0,0.3)',
                  transition: 'all 200ms',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.transform = 'translateY(-2px)'
                  e.currentTarget.style.boxShadow = '0 6px 28px rgba(0,0,0,0.4)'
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.transform = 'translateY(0)'
                  e.currentTarget.style.boxShadow = '0 4px 20px rgba(0,0,0,0.3)'
                }}
              >
                View Dashboard →
              </button>

              <button
                onClick={() => navigate('/stocks')}
                style={{
                  background: 'rgba(255,255,255,0.15)',
                  border: '1px solid rgba(255,255,255,0.4)',
                  backdropFilter: 'blur(8px)',
                  color: 'white',
                  padding: '12px 22px',
                  fontSize: 13,
                  fontWeight: 600,
                  borderRadius: 4,
                  cursor: 'pointer',
                  transition: 'all 200ms',
                }}
                onMouseEnter={(e) =>
                  (e.currentTarget.style.background = 'rgba(255,255,255,0.25)')
                }
                onMouseLeave={(e) =>
                  (e.currentTarget.style.background = 'rgba(255,255,255,0.15)')
                }
              >
                Browse Tickers
              </button>
            </div>
          </div>

          {/* ── STAGE 3: UNDERSTATED CAPTION (Above Traveler & Companion) ─── */}
          <div
            ref={captionRef}
            style={{
              position: 'absolute',
              bottom: 'clamp(14%, 20vh, 25%)',
              left: '50%',
              transform: 'translateX(-50%)',
              textAlign: 'center',
              opacity: 0,
              willChange: 'opacity, transform',
              zIndex: 20,
              pointerEvents: 'none',
              width: '90%',
              maxWidth: 520,
            }}
          >
            <p
              style={{
                fontFamily: 'Georgia, serif',
                fontSize: 'clamp(17px, 2.2vw, 24px)',
                fontStyle: 'italic',
                fontWeight: 400,
                color: '#ffffff',
                letterSpacing: '0.01em',
                lineHeight: 1.5,
                margin: 0,
                textShadow:
                  '0 2px 24px rgba(5,15,10,0.9), 0 1px 4px rgba(0,0,0,0.6)',
              }}
            >
              "Every journey starts with a single step."
            </p>
            <div
              style={{
                width: 42,
                height: 1.5,
                background:
                  'linear-gradient(to right, transparent, rgba(255,245,210,0.8), transparent)',
                margin: '14px auto 0',
              }}
            />
          </div>

          {/* ── STAGE 5: CINEMATIC FOREST & TREE WIPE ─────────────────────── */}
          <div
            ref={treesContainerRef}
            style={{
              position: 'absolute',
              inset: 0,
              zIndex: 25,
              pointerEvents: 'none',
              opacity: 0,
              overflow: 'hidden',
            }}
          >
            {/* Background trees */}
            <div
              className="tree-node"
              data-speed="0.75"
              data-start-x="-120"
              data-end-x="60"
              data-start-y="80"
              data-end-y="-30"
              data-base-scale="0.85"
              data-target-scale="2.0"
              style={{
                position: 'absolute',
                bottom: 0,
                left: '8%',
                width: 170,
                height: 400,
                opacity: 0.88,
              }}
            >
              <StorybookPine color="#1c3820" trunk="#19130d" />
            </div>

            <div
              className="tree-node"
              data-speed="0.8"
              data-start-x="140"
              data-end-x="-50"
              data-start-y="90"
              data-end-y="-40"
              data-base-scale="0.9"
              data-target-scale="2.2"
              style={{
                position: 'absolute',
                bottom: 0,
                right: '12%',
                width: 180,
                height: 420,
                opacity: 0.9,
              }}
            >
              <StorybookPine color="#16311a" trunk="#19130d" />
            </div>

            {/* Midground trees panning across */}
            <div
              className="tree-node"
              data-speed="1.1"
              data-start-x="-220"
              data-end-x="220"
              data-start-y="100"
              data-end-y="-60"
              data-base-scale="1.15"
              data-target-scale="3.2"
              style={{
                position: 'absolute',
                bottom: 0,
                left: '22%',
                width: 230,
                height: 540,
              }}
            >
              <StorybookPine color="#122715" trunk="#140f0a" />
            </div>

            <div
              className="tree-node"
              data-speed="1.15"
              data-start-x="240"
              data-end-x="-200"
              data-start-y="100"
              data-end-y="-70"
              data-base-scale="1.2"
              data-target-scale="3.4"
              style={{
                position: 'absolute',
                bottom: 0,
                right: '20%',
                width: 220,
                height: 520,
              }}
            >
              <StorybookPine color="#0e2211" trunk="#140f0a" />
            </div>

            {/* Massive Foreground Trees Rushing Past Left & Right */}
            <div
              className="tree-node"
              data-speed="1.3"
              data-start-x="-340"
              data-end-x="160"
              data-start-y="120"
              data-end-y="-100"
              data-base-scale="1.5"
              data-target-scale="5.2"
              style={{
                position: 'absolute',
                bottom: -50,
                left: '-4%',
                width: 350,
                height: 760,
              }}
            >
              <StorybookPine color="#0a1a0c" trunk="#100b07" />
            </div>

            <div
              className="tree-node"
              data-speed="1.35"
              data-start-x="360"
              data-end-x="-140"
              data-start-y="120"
              data-end-y="-110"
              data-base-scale="1.6"
              data-target-scale="5.5"
              style={{
                position: 'absolute',
                bottom: -60,
                right: '-6%',
                width: 360,
                height: 800,
              }}
            >
              <StorybookPine color="#08160a" trunk="#100b07" />
            </div>

            {/* Center Giant Pine (Engulfs screen center at wipe climax) */}
            <div
              className="tree-node"
              data-speed="1.45"
              data-start-x="0"
              data-end-x="0"
              data-start-y="300"
              data-end-y="-50"
              data-base-scale="2.0"
              data-target-scale="6.5"
              style={{
                position: 'absolute',
                bottom: -120,
                left: 'calc(50% - 220px)',
                width: 440,
                height: 900,
              }}
            >
              <StorybookPine color="#061208" trunk="#0d0905" />
            </div>

            {/* Top Canopy Boughs */}
            <div
              className="tree-node"
              data-speed="1.25"
              data-start-x="0"
              data-end-x="0"
              data-start-y="-240"
              data-end-y="60"
              data-base-scale="1.2"
              data-target-scale="2.6"
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                right: 0,
                height: 360,
              }}
            >
              <TopCanopyBoughs />
            </div>
          </div>

          {/* Deep Forest Canopy Overlay (Light theme wipe) */}
          <div
            ref={forestWipeRef}
            style={{
              position: 'absolute',
              inset: 0,
              zIndex: 28,
              background: '#f8faf9',
              opacity: 0,
              pointerEvents: 'none',
              willChange: 'opacity',
            }}
          />

          {/* ── SCROLL PROMPT HINT ────────────────────────────────────────── */}
          <div
            ref={scrollHintRef}
            style={{
              position: 'absolute',
              bottom: 26,
              left: '50%',
              transform: 'translateX(-50%)',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: 6,
              zIndex: 22,
              pointerEvents: 'none',
              transition: 'opacity 300ms ease',
            }}
          >
            <span
              style={{
                fontFamily: 'monospace',
                fontSize: 9,
                letterSpacing: '0.22em',
                textTransform: 'uppercase',
                color: 'rgba(255,255,255,0.7)',
                textShadow: '0 1px 8px rgba(0,0,0,0.6)',
                fontWeight: 600,
              }}
            >
              Scroll to explore
            </span>
            <div
              style={{
                width: 1.5,
                height: 30,
                background:
                  'linear-gradient(to bottom, rgba(255,255,255,0.8), transparent)',
                animation: 'pulseBar 2s ease-in-out infinite',
              }}
            />
          </div>
        </div>
      </div>

      {/* ── NEXT SECTION: CONTINUOUS MARKET INTELLIGENCE ──────────────────── */}
      <NextSection navigate={navigate} />

      {/* ── CSS KEYFRAMES ─────────────────────────────────────────────────── */}
      <style>{`
        @keyframes pulseBar {
          0%, 100% { opacity: 0.35; transform: scaleY(0.85); }
          50% { opacity: 0.95; transform: scaleY(1.0); }
        }
      `}</style>
    </div>
  )
}

// ── Storybook Painterly Pine Tree SVG ─────────────────────────────────────────
function StorybookPine({ color = '#0f2412', trunk = '#1b140e' }) {
  return (
    <svg viewBox="0 0 160 480" fill="none" style={{ width: '100%', height: '100%' }}>
      {/* Tree Trunk with bark taper */}
      <path
        d="M 76 260 L 71 480 Q 80 475 89 480 L 84 260 Z"
        fill={trunk}
        opacity="0.95"
      />

      {/* Tier 5 (Base foliage) */}
      <path
        d="M 80 220 C 50 250, 10 330, 0 380 C 35 365, 60 375, 80 365 C 100 375, 125 365, 160 380 C 150 330, 110 250, 80 220 Z"
        fill={color}
        opacity="0.98"
      />

      {/* Tier 4 */}
      <path
        d="M 80 160 C 55 190, 20 270, 12 305 C 45 290, 65 300, 80 292 C 95 300, 115 290, 148 305 C 140 270, 105 190, 80 160 Z"
        fill={color}
        opacity="0.95"
      />

      {/* Tier 3 */}
      <path
        d="M 80 100 C 60 130, 32 205, 25 235 C 50 222, 68 230, 80 224 C 92 230, 110 222, 135 235 C 128 205, 100 130, 80 100 Z"
        fill={color}
        opacity="0.92"
      />

      {/* Tier 2 */}
      <path
        d="M 80 45 C 65 75, 42 140, 38 165 C 58 152, 70 160, 80 154 C 90 160, 102 152, 122 165 C 118 140, 95 75, 80 45 Z"
        fill={color}
        opacity="0.90"
      />

      {/* Tier 1 (Alpine crown spire) */}
      <path
        d="M 80 0 C 72 25, 54 80, 50 95 C 65 85, 74 90, 80 86 C 86 90, 95 85, 110 95 C 106 80, 88 25, 80 0 Z"
        fill={color}
        opacity="0.88"
      />
    </svg>
  )
}

// ── Overhanging Top Canopy Boughs ─────────────────────────────────────────────
function TopCanopyBoughs() {
  return (
    <svg
      viewBox="0 0 1200 300"
      preserveAspectRatio="none"
      fill="none"
      style={{ width: '100%', height: '100%' }}
    >
      {/* Left canopy bough */}
      <path
        d="M -50 -20 Q 200 40 450 180 C 350 170 280 220 180 250 C 100 180 20 160 -50 190 Z"
        fill="#061208"
        opacity="0.97"
      />
      {/* Right canopy bough */}
      <path
        d="M 1250 -20 Q 1000 50 750 190 C 850 175 920 230 1020 260 C 1100 180 1180 160 1250 190 Z"
        fill="#07140a"
        opacity="0.97"
      />
      {/* Center drop canopy */}
      <path
        d="M 350 -40 Q 600 120 850 -40 C 780 80 680 150 600 160 C 520 150 420 80 350 -40 Z"
        fill="#050e06"
        opacity="0.99"
      />
    </svg>
  )
}

// ── Next Section (Follows the Forest Journey — Light Theme) ─────────────────
function NextSection({ navigate }) {
  return (
    <section
      style={{
        background: '#f8faf9',
        color: '#0f172a',
        minHeight: '100vh',
        position: 'relative',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '110px 32px 80px',
        overflow: 'hidden',
      }}
    >
      {/* Subtle warm amber/emerald ambient aura */}
      <div
        style={{
          position: 'absolute',
          top: 0,
          left: '50%',
          transform: 'translateX(-50%)',
          width: '900px',
          height: '600px',
          background:
            'radial-gradient(ellipse 55% 45% at 50% 15%, rgba(180, 120, 22, 0.08), transparent 70%)',
          pointerEvents: 'none',
        }}
      />

      <div style={{ position: 'relative', zIndex: 2, maxWidth: 840, textAlign: 'center' }}>
        <p
          style={{
            fontFamily: 'monospace',
            fontSize: 11,
            letterSpacing: '0.22em',
            textTransform: 'uppercase',
            color: '#059669',
            marginBottom: 20,
            fontWeight: 700,
          }}
        >
          Continuous Market Intelligence
        </p>

        <h2
          style={{
            fontFamily: 'Georgia, serif',
            fontSize: 'clamp(32px, 5vw, 56px)',
            fontWeight: 500,
            lineHeight: 1.16,
            letterSpacing: '-0.03em',
            color: '#0f172a',
            margin: '0 0 24px 0',
          }}
        >
          Your AI analyst that gets
          <br />
          smarter every single day.
        </h2>

        <p
          style={{
            fontFamily: 'system-ui, sans-serif',
            fontSize: 'clamp(15px, 1.4vw, 18px)',
            color: '#475569',
            lineHeight: 1.8,
            maxWidth: 580,
            margin: '0 auto 52px',
          }}
        >
          Autonomous BUY, HOLD, and SELL signals powered by deep technical analysis,
          sentiment processing, and self-evaluating vector memory.
        </p>

        {/* Feature Cards */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
            gap: 24,
            marginBottom: 56,
            textAlign: 'left',
          }}
        >
          {[
            {
              icon: '⚡',
              tag: 'Real-Time Evaluation',
              title: 'Multi-Factor Signals',
              desc: 'RSI, MACD, Bollinger Bands, Moving Averages, and live sentiment synthesized into clear trading recommendations with transparent reasoning.',
            },
            {
              icon: '🧠',
              tag: 'Self-Improving',
              title: 'Episodic Memory',
              desc: 'Retrieves similar historical market regimes and past signals from pgvector to continuously improve accuracy and eliminate recurring errors.',
            },
            {
              icon: '🎯',
              tag: 'Strict Accountability',
              title: '5-Day Automated Audit',
              desc: 'Every single prediction is logged and automatically verified after 5 trading days. Live win rate and trade outcomes are fully public.',
            },
          ].map((item) => (
            <div
              key={item.title}
              style={{
                padding: '28px 24px',
                borderRadius: 8,
                border: '1px solid rgba(0, 0, 0, 0.08)',
                background: '#ffffff',
                boxShadow: '0 4px 20px -2px rgba(0, 0, 0, 0.05)',
                display: 'flex',
                flexDirection: 'column',
                gap: 12,
                transition: 'all 220ms ease',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = 'rgba(5, 150, 105, 0.4)'
                e.currentTarget.style.transform = 'translateY(-3px)'
                e.currentTarget.style.boxShadow = '0 12px 28px -4px rgba(0, 0, 0, 0.08)'
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = 'rgba(0, 0, 0, 0.08)'
                e.currentTarget.style.transform = 'translateY(0)'
                e.currentTarget.style.boxShadow = '0 4px 20px -2px rgba(0, 0, 0, 0.05)'
              }}
            >
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                }}
              >
                <span style={{ fontSize: 24 }}>{item.icon}</span>
                <span
                  style={{
                    fontFamily: 'monospace',
                    fontSize: 9,
                    letterSpacing: '0.12em',
                    textTransform: 'uppercase',
                    color: '#059669',
                    fontWeight: 700,
                  }}
                >
                  {item.tag}
                </span>
              </div>
              <h3
                style={{
                  fontFamily: 'Georgia, serif',
                  fontSize: 18,
                  fontWeight: 500,
                  margin: 0,
                  color: '#0f172a',
                }}
              >
                {item.title}
              </h3>
              <p
                style={{
                  fontSize: 13,
                  color: '#64748b',
                  lineHeight: 1.65,
                  margin: 0,
                }}
              >
                {item.desc}
              </p>
            </div>
          ))}
        </div>

        {/* Action Buttons */}
        <div
          style={{
            display: 'flex',
            gap: 16,
            justifyContent: 'center',
            flexWrap: 'wrap',
          }}
        >
          <button
            onClick={() => navigate('/dashboard')}
            style={{
              background: '#0f172a',
              color: '#ffffff',
              border: 'none',
              padding: '14px 34px',
              fontSize: 14,
              fontWeight: 700,
              borderRadius: 4,
              cursor: 'pointer',
              boxShadow: '0 2px 10px rgba(15, 23, 42, 0.2)',
              transition: 'all 200ms',
            }}
            onMouseEnter={(e) => (e.currentTarget.style.opacity = '0.9')}
            onMouseLeave={(e) => (e.currentTarget.style.opacity = '1')}
          >
            Launch Dashboard →
          </button>
          <button
            onClick={() => navigate('/stocks')}
            style={{
              background: '#ffffff',
              color: '#0f172a',
              border: '1px solid #cbd5e1',
              padding: '14px 32px',
              fontSize: 14,
              fontWeight: 600,
              borderRadius: 4,
              cursor: 'pointer',
              transition: 'all 200ms',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.borderColor = '#0f172a'
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = '#cbd5e1'
            }}
          >
            Explore Available Stocks
          </button>
        </div>
      </div>

      <footer
        style={{
          marginTop: 100,
          textAlign: 'center',
          fontFamily: 'monospace',
          fontSize: 11,
          letterSpacing: '0.12em',
          textTransform: 'uppercase',
          color: '#94a3b8',
        }}
      >
        Stock Insight Agent · AI Trading Intelligence · Not Financial Advice
      </footer>
    </section>
  )
}

// ── Accessible / Reduced Motion Static Landing ────────────────────────────────
function AccessibleLanding({ navigate }) {
  return (
    <div
      style={{
        minHeight: '100vh',
        position: 'relative',
        background: '#f8faf9',
        overflow: 'hidden',
      }}
    >
      <svg
        viewBox="0 0 1024 731"
        preserveAspectRatio="xMidYMid slice"
        style={{
          position: 'absolute',
          inset: 0,
          width: '100%',
          height: '100%',
        }}
      >
        <image href="/hero.jpg" x="0" y="0" width="1024" height="731" />
      </svg>
      <div
        style={{
          position: 'absolute',
          inset: 0,
          background:
            'radial-gradient(ellipse at center, rgba(0,0,0,0.1), rgba(0,0,0,0.45) 100%)',
        }}
      />
      <div style={{ position: 'relative', zIndex: 10, padding: '24px 36px' }}>
        <nav
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <span
            style={{
              color: 'white',
              fontFamily: 'Georgia, serif',
              fontSize: 18,
              fontWeight: 600,
              textShadow: '0 2px 8px rgba(0,0,0,0.6)',
            }}
          >
            Stock Insight Agent
          </span>
          <button
            onClick={() => navigate('/dashboard')}
            style={{
              background: 'white',
              border: 'none',
              color: '#111b11',
              padding: '8px 18px',
              fontSize: 12,
              fontWeight: 700,
              cursor: 'pointer',
              borderRadius: 4,
            }}
          >
            Dashboard →
          </button>
        </nav>

        <div style={{ marginTop: '16vh', maxWidth: 520 }}>
          <h1
            style={{
              fontFamily: 'Georgia, serif',
              fontSize: 48,
              color: 'white',
              lineHeight: 1.15,
              textShadow: '0 2px 20px rgba(0,0,0,0.6)',
            }}
          >
            Predict.
            <br />
            Learn.
            <br />
            Outperform.
          </h1>
          <p
            style={{
              color: 'rgba(255,255,255,0.9)',
              fontSize: 16,
              lineHeight: 1.7,
              margin: '20px 0 28px',
              textShadow: '0 1px 12px rgba(0,0,0,0.5)',
            }}
          >
            Autonomous AI agent that generates buy, hold &amp; sell signals, audits
            its predictions after 5 trading days, and continually refines its
            strategy.
          </p>
          <button
            onClick={() => navigate('/dashboard')}
            style={{
              background: 'white',
              color: '#111b11',
              border: 'none',
              padding: '12px 28px',
              fontSize: 14,
              fontWeight: 700,
              cursor: 'pointer',
              borderRadius: 4,
            }}
          >
            Explore Dashboard →
          </button>
        </div>
      </div>
      <NextSection navigate={navigate} />
    </div>
  )
}
