import { useMemo, useState } from 'react';
import {
  ComposableMap,
  Geographies,
  Geography,
  Marker,
  Line,
  ZoomableGroup,
  Graticule,
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

  /** Offset overlapping arcs perpendicular to their direct path */
  const offsetArcs = useMemo(() => {
    return arcsData.map((arc) => {
      if (arc.groupSize <= 1) return arc;

      const dx = arc.endLng - arc.startLng;
      const dy = arc.endLat - arc.startLat;
      const len = Math.sqrt(dx * dx + dy * dy);
      if (len === 0) return arc;

      // Perpendicular unit vector
      const px = -dy / len;
      const py = dx / len;

      const spread = Math.min(1.5, len * 0.08);
      const center = (arc.groupSize - 1) / 2;
      const t =
        arc.groupSize > 1
          ? (arc.groupIndex - center) / Math.max(arc.groupSize - 1, 1)
          : 0;
      const offset = t * spread;

      return {
        ...arc,
        startLng: arc.startLng + px * offset * 0.5,
        startLat: arc.startLat + py * offset * 0.5,
        endLng: arc.endLng + px * offset,
        endLat: arc.endLat + py * offset,
      };
    });
  }, [arcsData]);

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
        <ZoomableGroup>
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

          {/* Supply-chain lines */}
          {offsetArcs.map((arc, i) => (
            <Line
              key={`arc-${i}`}
              from={[arc.startLng, arc.startLat]}
              to={[arc.endLng, arc.endLat]}
              stroke={arc.color[0]}
              strokeWidth={arc.stroke}
              strokeLinecap="round"
              strokeOpacity={0.75}
              fill="none"
              onClick={(e) => {
                e.stopPropagation();
                onArcClick(arc);
              }}
              onMouseEnter={(e) =>
                setTooltip({
                  x: (e as unknown as MouseEvent).clientX,
                  y: (e as unknown as MouseEvent).clientY,
                  text: arc.label,
                })
              }
              onMouseLeave={() => setTooltip(null)}
              style={{ cursor: 'pointer' }}
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
