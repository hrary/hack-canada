import { useMemo, useState, useCallback, useRef, useEffect } from 'react';
import {
  ComposableMap,
  Geographies,
  Geography,
  Marker,
  Graticule,
} from 'react-simple-maps';
import { geoNaturalEarth1 } from 'd3-geo';
import styles from './SupplyMap2D.module.css';

const GEO_URL = 'https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json';

export interface ArcSegment {
  startLng: number;
  startLat: number;
  endLng: number;
  endLat: number;
  color: string;
  stroke: number;
  sector?: string;
}

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
  sectors?: string[]; // sectors involved in this arc
  values?: number[]; // trade value per sector
}

export interface MapPoint {
  lat: number;
  lng: number;
  size: number;
  color: string;
  label: string;
}

// Sector-based color mapping (consistent across app)
const SECTOR_COLORS: Record<string, string> = {
  'Electronics': '#3b82f6',
  'Automotive': '#ef4444',
  'Textiles': '#ec4899',
  'Chemicals': '#8b5cf6',
  'Machinery': '#f97316',
  'Pharmaceuticals': '#10b981',
  'Metals': '#6b7280',
  'Energy': '#eab308',
  'Agriculture': '#059669',
  'Aerospace': '#06b6d4',
  'Default': '#06b6d4',
};

function getSectorColor(sector?: string): string {
  if (!sector) return SECTOR_COLORS['Default'];
  // Try exact match first
  if (SECTOR_COLORS[sector]) return SECTOR_COLORS[sector];
  // Try partial match
  for (const [key, color] of Object.entries(SECTOR_COLORS)) {
    if (sector.toLowerCase().includes(key.toLowerCase()) || key.toLowerCase().includes(sector.toLowerCase())) {
      return color;
    }
  }
  return SECTOR_COLORS['Default'];
}

interface Props {
  arcsData: MapArc[];
  pointsData: MapPoint[];
  selectedLabel: string | null;
  onPointClick: (point: MapPoint) => void;
  onArcClick: (arc: MapArc) => void;
  onDismiss: () => void;
}

// Map dimensions & projection config (must match <ComposableMap>)
const MAP_WIDTH = 960;
const MAP_HEIGHT = 500;
const MAP_CENTER: [number, number] = [10, 10];
const MAP_SCALE = 160;

/** Shared projection instance matching the ComposableMap config */
const projection = geoNaturalEarth1()
  .scale(MAP_SCALE)
  .center(MAP_CENTER)
  .translate([MAP_WIDTH / 2, MAP_HEIGHT / 2]);

/**
 * Project [lng, lat] → [x, y] pixel coordinates.
 * Returns null if the point can't be projected.
 */
function project(lng: number, lat: number): [number, number] | null {
  return projection([lng, lat]) as [number, number] | null;
}

/**
 * Build an SVG quadratic bezier "arc" path between two projected points.
 * The control point is offset upward (negative Y) proportional to the
 * distance, giving a nice curved arc effect.
 */
function arcPath(
  x1: number, y1: number,
  x2: number, y2: number,
): string {
  const mx = (x1 + x2) / 2;
  const my = (y1 + y2) / 2;
  const dist = Math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2);
  // Bulge upward; scale with distance so short arcs don't over-curve
  const bulge = Math.min(dist * 0.25, 60);
  return `M${x1},${y1} Q${mx},${my - bulge} ${x2},${y2}`;
}

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

  // Custom zoom state — clamped between 1× and 6×
  const MIN_ZOOM = 1;
  const MAX_ZOOM = 6;
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState<[number, number]>([0, 0]);
  const isPanning = useRef(false);
  const lastMouse = useRef<[number, number]>([0, 0]);
  const containerRef = useRef<HTMLDivElement>(null);

  // Attach native wheel listener with { passive: false } so preventDefault works
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setZoom(z => {
        const next = z * (e.deltaY < 0 ? 1.12 : 0.89);
        return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, next));
      });
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, []);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (zoom <= 1) return; // no panning at default zoom
    isPanning.current = true;
    lastMouse.current = [e.clientX, e.clientY];
  }, [zoom]);

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (!isPanning.current) return;
    const dx = e.clientX - lastMouse.current[0];
    const dy = e.clientY - lastMouse.current[1];
    lastMouse.current = [e.clientX, e.clientY];
    setPan(p => [p[0] + dx, p[1] + dy]);
  }, []);

  const handleMouseUp = useCallback(() => {
    isPanning.current = false;
  }, []);

  /**
   * Build one ArcSegment per sector per arc.
   * Multi-sector arcs are offset perpendicular to the arc direction.
   * No splitting — each arc stays as a single continuous segment.
   */
  const segmentedArcs = useMemo(() => {
    const segments: (ArcSegment & { arc: MapArc; index: number })[] = [];

    arcsData.forEach((arc) => {
      if (!arc.sectors || arc.sectors.length === 0) {
        segments.push({
          startLng: arc.startLng, startLat: arc.startLat,
          endLng: arc.endLng, endLat: arc.endLat,
          color: arc.color[0],
          stroke: arc.stroke,
          sector: undefined,
          arc, index: 0,
        });
        return;
      }

      // Perpendicular offset from the OVERALL arc direction
      let dx = arc.endLng - arc.startLng;
      if (Math.abs(dx) > 180) dx = dx > 0 ? dx - 360 : dx + 360;
      const dy = arc.endLat - arc.startLat;
      const distance = Math.sqrt(dx * dx + dy * dy);

      if (distance === 0) {
        arc.sectors.forEach((sector, si) => {
          segments.push({
            startLng: arc.startLng, startLat: arc.startLat,
            endLng: arc.endLng, endLat: arc.endLat,
            color: getSectorColor(sector),
            stroke: arc.values?.[si] || arc.stroke,
            sector, arc, index: si,
          });
        });
        return;
      }

      const perpX = -dy / distance;
      const perpY = dx / distance;
      const maxSpread = Math.min(3.0, distance * 0.12);
      const numSectors = arc.sectors.length;
      const center = (numSectors - 1) / 2;

      arc.sectors.forEach((sector, si) => {
        const off = numSectors > 1
          ? ((si - center) / Math.max(numSectors - 1, 1)) * maxSpread
          : 0;

        segments.push({
          startLng: arc.startLng + perpX * off,
          startLat: arc.startLat + perpY * off,
          endLng: arc.endLng + perpX * off,
          endLat: arc.endLat + perpY * off,
          color: getSectorColor(sector),
          stroke: arc.values?.[si] || arc.stroke,
          sector, arc, index: si,
        });
      });
    });

    return segments;
  }, [arcsData]);

  // Max stroke for normalized thickness
  const maxStrokeValue = useMemo(() => {
    if (segmentedArcs.length === 0) return 1;
    return Math.max(...segmentedArcs.map(s => s.stroke), 1);
  }, [segmentedArcs]);

  // Pre-project all arcs to pixel-space SVG paths
  const projectedArcs = useMemo(() => {
    return segmentedArcs.map((seg) => {
      const p1 = project(seg.startLng, seg.startLat);
      const p2 = project(seg.endLng, seg.endLat);
      if (!p1 || !p2) return null;
      return {
        d: arcPath(p1[0], p1[1], p2[0], p2[1]),
        ...seg,
      };
    }).filter(Boolean) as (ArcSegment & { arc: MapArc; index: number; d: string })[];
  }, [segmentedArcs]);

  return (
    <div
      ref={containerRef}
      className={styles.mapContainer}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
    >
      <ComposableMap
        projection="geoNaturalEarth1"
        projectionConfig={{ scale: MAP_SCALE, center: MAP_CENTER }}
        width={MAP_WIDTH}
        height={MAP_HEIGHT}
        style={{ width: '100%', height: '100%' }}
        onClick={onDismiss}
      >
        <g transform={`translate(${MAP_WIDTH / 2 + pan[0] / (MAP_WIDTH / 960)}, ${MAP_HEIGHT / 2 + pan[1] / (MAP_HEIGHT / 500)}) scale(${zoom}) translate(${-MAP_WIDTH / 2}, ${-MAP_HEIGHT / 2})`}>
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

          {/* Smooth bezier arcs drawn in pixel-space */}
          {projectedArcs.map((seg, i) => (
            <path
              key={`arc-${i}`}
              d={seg.d}
              stroke={seg.color}
              strokeWidth={Math.max(1.2, (seg.stroke / maxStrokeValue) * 6.5) / zoom}
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeOpacity={0.85}
              fill="none"
              onClick={(e) => {
                e.stopPropagation();
                onArcClick(seg.arc);
              }}
              onMouseEnter={(e) => {
                const sectorLabel = seg.sector ? ` [${seg.sector}]` : '';
                setTooltip({
                  x: (e as unknown as MouseEvent).clientX,
                  y: (e as unknown as MouseEvent).clientY,
                  text: seg.arc.label + sectorLabel,
                });
              }}
              onMouseLeave={() => setTooltip(null)}
              style={{ cursor: 'pointer', filter: 'drop-shadow(0 0 3px rgba(0,0,0,0.6))' }}
            />
          ))}

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
                r={(pt.size * 3.5) / zoom}
                fill={pt.color}
                stroke="rgba(255,255,255,0.4)"
                strokeWidth={0.5 / zoom}
                opacity={0.9}
                style={{ cursor: 'pointer' }}
              />
            </Marker>
          ))}
        </g>
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

      <div className={styles.sectorLegend}>
        <div className={styles.legendTitle}>Sectors</div>
        {Object.entries(SECTOR_COLORS).map(([sector, color]) => (
          sector !== 'Default' && (
            <div key={sector} className={styles.legendItem}>
              <div className={styles.legendColor} style={{ backgroundColor: color }} />
              <span>{sector}</span>
            </div>
          )
        ))}
      </div>
    </div>
  );
}
