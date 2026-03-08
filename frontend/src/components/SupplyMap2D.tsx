import { useMemo, useState } from 'react';
import {
  ComposableMap,
  Geographies,
  Geography,
  Marker,
  ZoomableGroup,
  Graticule,
  useMapContext,
} from 'react-simple-maps';
import styles from './SupplyMap2D.module.css';

const GEO_URL = 'https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json';

export interface MapArc {
  startLat: number;
  startLng: number;
  endLat: number;
  endLng: number;
  color: [string, string];
  label: string;
  stroke: number;
  groupIndex: number;
  groupSize: number;
}

export interface MapPoint {
  lat: number;
  lng: number;
  size: number;
  color: string;
  label: string;
}

interface Props {
  arcsData: MapArc[];
  pointsData: MapPoint[];
  selectedLabel: string | null;
  onPointClick: (point: MapPoint) => void;
  onArcClick: (arc: MapArc) => void;
  onDismiss: () => void;
}

/* ── Projected curve arcs (rendered inside ComposableMap context) ──── */

function CurveArcs({
  arcs,
  onArcClick,
  setTooltip,
}: {
  arcs: MapArc[];
  onArcClick: (arc: MapArc) => void;
  setTooltip: (t: { x: number; y: number; text: string } | null) => void;
}) {
  const { projection } = useMapContext();

  const paths = useMemo(() => {
    return arcs.map((arc) => {
      const from = projection([arc.startLng, arc.startLat]);
      const to = projection([arc.endLng, arc.endLat]);
      if (!from || !to) return null;

      const [x1, y1] = from;
      const [x2, y2] = to;

      // Midpoint
      const mx = (x1 + x2) / 2;
      const my = (y1 + y2) / 2;

      // Distance between endpoints in SVG space
      const dx = x2 - x1;
      const dy = y2 - y1;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist < 0.5) return null;

      // Perpendicular unit vector (always curve "upward" on screen)
      const px = -dy / dist;
      const py = dx / dist;

      // Base curvature: proportional to distance, capped
      const baseBulge = Math.min(dist * 0.25, 60);

      // Overlap offset: spread grouped arcs apart
      let groupOffset = 0;
      if (arc.groupSize > 1) {
        const center = (arc.groupSize - 1) / 2;
        const t = (arc.groupIndex - center) / Math.max(arc.groupSize - 1, 1);
        groupOffset = t * Math.min(dist * 0.15, 30);
      }

      // Always curve upward (negative Y in SVG) + group spread
      const sign = py < 0 ? 1 : -1;
      const totalBulge = baseBulge * sign + groupOffset;

      const cx = mx + px * totalBulge;
      const cy = my + py * totalBulge;

      const d = `M ${x1} ${y1} Q ${cx} ${cy} ${x2} ${y2}`;

      // Dash length for animation
      const pathLen = dist * 1.3; // approximate quadratic arc length

      return { arc, d, pathLen };
    });
  }, [arcs, projection]);

  return (
    <g>
      {/* Gradient definitions for each unique color pair */}
      <defs>
        {arcs.map((arc, i) => (
          <linearGradient key={`grad-${i}`} id={`arc-grad-${i}`}>
            <stop offset="0%" stopColor={arc.color[0]} />
            <stop offset="100%" stopColor={arc.color[1]} />
          </linearGradient>
        ))}
      </defs>
      {paths.map((p, i) => {
        if (!p) return null;
        return (
          <path
            key={`arc-${i}`}
            d={p.d}
            fill="none"
            stroke={`url(#arc-grad-${i})`}
            strokeWidth={p.arc.stroke}
            strokeLinecap="round"
            opacity={0.8}
            strokeDasharray={`${p.pathLen * 0.08} ${p.pathLen * 0.04}`}
            className={styles.animatedArc}
            onClick={(e) => {
              e.stopPropagation();
              onArcClick(p.arc);
            }}
            onMouseEnter={(e) =>
              setTooltip({
                x: e.clientX,
                y: e.clientY,
                text: p.arc.label,
              })
            }
            onMouseLeave={() => setTooltip(null)}
            style={{ cursor: 'pointer' }}
          />
        );
      })}
    </g>
  );
}

/* ── Main component ─────────────────────────────────────────────────── */

export default function SupplyMap2D({
  arcsData,
  pointsData,
  selectedLabel,
  onPointClick,
  onArcClick,
  onDismiss,
}: Props) {
  const [tooltip, setTooltip] = useState<{
    x: number;
    y: number;
    text: string;
  } | null>(null);

  return (
    <div className={styles.mapContainer}>
      <ComposableMap
        projection="geoNaturalEarth1"
        projectionConfig={{ scale: 160, center: [10, 10] }}
        width={960}
        height={500}
        style={{ width: '100%', height: '100%' }}
        onClick={onDismiss}
      >
        <ZoomableGroup
          translateExtent={[[-100, -50], [1060, 550]]}
          minZoom={1}
          maxZoom={8}
        >
          <Graticule stroke="rgba(255,255,255,0.05)" strokeWidth={0.3} />
          <Geographies geography={GEO_URL}>
            {({ geographies }: any) =>
              geographies.map((geo: any) => (
                <Geography
                  key={geo.rsmKey}
                  geography={geo}
                  fill="#1a2236"
                  stroke="#2a3a52"
                  strokeWidth={0.4}
                  style={{
                    default: { outline: 'none' },
                    hover: { fill: '#243044', outline: 'none' },
                    pressed: { outline: 'none' },
                  }}
                />
              ))
            }
          </Geographies>

          {/* Supply-chain curved arcs */}
          <CurveArcs
            arcs={arcsData}
            onArcClick={onArcClick}
            setTooltip={setTooltip}
          />

          {/* Supply-chain nodes */}
          {pointsData.map((pt, i) => (
            <Marker
              key={`pt-${i}`}
              coordinates={[pt.lng, pt.lat]}
              onClick={(e) => {
                e.stopPropagation();
                onPointClick(pt);
              }}
              onMouseEnter={(e) =>
                setTooltip({
                  x: (e as unknown as MouseEvent).clientX,
                  y: (e as unknown as MouseEvent).clientY,
                  text: pt.label,
                })
              }
              onMouseLeave={() => setTooltip(null)}
            >
              <circle
                r={pt.size * 3.5}
                fill={pt.color}
                stroke="rgba(255,255,255,0.4)"
                strokeWidth={0.5}
                opacity={0.9}
                style={{ cursor: 'pointer' }}
              />
            </Marker>
          ))}
        </ZoomableGroup>
      </ComposableMap>

      {tooltip && (
        <div
          className={styles.tooltip}
          style={{ left: tooltip.x + 12, top: tooltip.y - 24 }}
        >
          {tooltip.text}
        </div>
      )}

      {selectedLabel && (
        <div className={styles.infoBox}>
          <span>{selectedLabel}</span>
          <button
            className={styles.infoBoxClose}
            onClick={(e) => {
              e.stopPropagation();
              onDismiss();
            }}
          >
            ✕
          </button>
        </div>
      )}
    </div>
  );
}
