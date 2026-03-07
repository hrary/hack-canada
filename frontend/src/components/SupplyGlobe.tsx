import { useEffect, useRef, useCallback, useMemo, useState } from 'react';
import GlobeGL from 'react-globe.gl';
import { Globe as GlobeIcon, Map as MapIcon } from 'lucide-react';
import type { SupplyPoint, RiskSeverity } from '../types';
import { useAppContext } from '../context/AppContext';
import SupplyMap2D from './SupplyMap2D';
import type { MapArc, MapPoint } from './SupplyMap2D';
import styles from './SupplyGlobe.module.css';

interface Props {
  supplyPoints: SupplyPoint[];
  headquartersLocation: { lat: number; lng: number } | null;
}

/* ── Severity colour scheme ─────────────────────────────────────────── *
 * high  = red,  medium = yellow/orange,  low = green,  critical = purple
 * Default (unanalysed) = cyan — avoids confusion with severity colours  */

const SEVERITY_ARC_COLORS: Record<RiskSeverity, [string, string]> = {
  low: ['#22c55e', '#4ade80'],
  medium: ['#f59e0b', '#fbbf24'],
  high: ['#ef4444', '#f87171'],
  critical: ['#a855f7', '#c084fc'],
};

const DEFAULT_ARC_COLOR: [string, string] = ['#06b6d4', '#22d3ee'];

const SEVERITY_COLORS: Record<RiskSeverity, string> = {
  low: '#22c55e',
  medium: '#f59e0b',
  high: '#ef4444',
  critical: '#a855f7',
};

/* ── Sector colour scheme (consistent with SupplyMap2D) ─────────── */
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
};

function getSectorColor(sector?: string): string {
  if (!sector) return '#06b6d4';
  if (SECTOR_COLORS[sector]) return SECTOR_COLORS[sector];
  for (const [key, color] of Object.entries(SECTOR_COLORS)) {
    if (sector.toLowerCase().includes(key.toLowerCase()) ||
        key.toLowerCase().includes(sector.toLowerCase())) return color;
  }
  return '#06b6d4';
}

function sectorToArcColor(sector?: string): [string, string] {
  const c = getSectorColor(sector);
  return [c, c];
}

/* ── Value → line thickness ─────────────────────────────────────────── */

/** Map monetary value to a 3D arc stroke width (0.3 – 2.0). */
function valueToStroke3D(value?: number): number {
  if (!value || value <= 0) return 0.5;
  const logVal = Math.log10(Math.max(value, 1_000_000));
  const t = Math.min(1, Math.max(0, (logVal - 6) / 2.3));
  return 0.3 + t * 1.7;
}

/** Map monetary value to a 2D SVG stroke width (0.6 – 3.5). */
function valueToStroke2D(value?: number): number {
  if (!value || value <= 0) return 0.8;
  const logVal = Math.log10(Math.max(value, 1_000_000));
  const t = Math.min(1, Math.max(0, (logVal - 6) / 2.3));
  return 0.6 + t * 2.9;
}

export default function SupplyGlobe({ supplyPoints, headquartersLocation }: Props) {
  const globeRef = useRef<any>(null);
  const { supplierResearch, streamedRisks, focusLocation } = useAppContext();
  const [selectedLabel, setSelectedLabel] = useState<string | null>(null);
  const [is3D, setIs3D] = useState(true);

  /* ── Globe initialisation (re-runs when toggling back to 3D) ───── */
  useEffect(() => {
    if (!is3D) return;
    const id = requestAnimationFrame(() => {
      const globe = globeRef.current;
      if (!globe) return;
      globe.controls().autoRotate = true;
      globe.controls().autoRotateSpeed = 0.5;
      globe.controls().enableZoom = true;
    });
    return () => cancelAnimationFrame(id);
  }, [is3D]);

  useEffect(() => {
    if (headquartersLocation && globeRef.current && is3D) {
      globeRef.current.pointOfView(
        { lat: headquartersLocation.lat, lng: headquartersLocation.lng, altitude: 2 },
        1000,
      );
    }
  }, [headquartersLocation, is3D]);

  /* ── Severity map (backend node_id → worst severity) ──────────── */
  const severityMap = useMemo(() => {
    const m = new Map<string, RiskSeverity>();
    const order: Record<RiskSeverity, number> = { low: 0, medium: 1, high: 2, critical: 3 };
    for (const r of streamedRisks) {
      const cur = m.get(r.node_id);
      if (!cur || order[r.severity] > order[cur]) m.set(r.node_id, r.severity);
    }
    return m;
  }, [streamedRisks]);

  /* ── Node ID → SupplyPoint matching by supplier name ──────────── */
  const nodeIdToPoint = useMemo(() => {
    const m = new Map<string, SupplyPoint>();
    for (const res of supplierResearch) {
      const pt = supplyPoints.find(
        p => p.supplier === res.supplier || p.name === res.supplier,
      );
      if (pt) m.set(res.node_id, pt);
    }
    return m;
  }, [supplierResearch, supplyPoints]);

  const pointSeverityMap = useMemo(() => {
    const m = new Map<string, RiskSeverity>();
    for (const [nid, pt] of nodeIdToPoint) {
      const sev = severityMap.get(nid);
      if (sev) m.set(pt.id, sev);
    }
    return m;
  }, [nodeIdToPoint, severityMap]);

  /* ── Sub-component points ─────────────────────────────────────── */
  const subPoints = useMemo(() => {
    const pts: MapPoint[] = [];
    for (const res of supplierResearch) {
      for (const sc of res.sub_components) {
        if (!sc.lat && !sc.lng) continue;
        pts.push({
          lat: sc.lat,
          lng: sc.lng,
          size: 0.7,
          color: '#facc15',
          label: `${sc.component} — ${sc.source_company || sc.source_country}`,
        });
      }
    }
    return pts;
  }, [supplierResearch]);

  /* ── Raw arcs (before overlap enrichment) ─────────────────────── */
  const rawPrimaryArcs = useMemo(() => {
    if (!headquartersLocation) return [];
    return supplyPoints.map(pt => {
      const sev = pointSeverityMap.get(pt.id);
      return {
        startLat: pt.lat,
        startLng: pt.lng,
        endLat: headquartersLocation.lat,
        endLng: headquartersLocation.lng,
        color: sev ? SEVERITY_ARC_COLORS[sev] : sectorToArcColor(pt.sector),
        label: `${pt.name} → Headquarters`,
        value: pt.value,
        sector: pt.sector,
      };
    });
  }, [supplyPoints, headquartersLocation, pointSeverityMap]);

  const rawSubArcs = useMemo(() => {
    const arcs: {
      startLat: number; startLng: number;
      endLat: number; endLng: number;
      color: [string, string]; label: string; value?: number; sector?: string;
    }[] = [];
    for (const res of supplierResearch) {
      const parent = nodeIdToPoint.get(res.node_id);
      if (!parent) continue;
      const sev = pointSeverityMap.get(parent.id);
      for (const sc of res.sub_components) {
        if (!sc.lat && !sc.lng) continue;
        arcs.push({
          startLat: sc.lat,
          startLng: sc.lng,
          endLat: parent.lat,
          endLng: parent.lng,
          color: sev ? SEVERITY_ARC_COLORS[sev] : sectorToArcColor(parent.sector),
          label: `${sc.component} (${sc.source_company || sc.source_country}) → ${parent.name}`,
          value: parent.value ? parent.value * 0.2 : undefined,
          sector: parent.sector,
        });
      }
    }
    return arcs;
  }, [supplierResearch, nodeIdToPoint, pointSeverityMap]);

  /* ── Assign overlap groups & compute stroke / altitude ────────── */
  const enrichedArcs = useMemo(() => {
    const all = [...rawPrimaryArcs, ...rawSubArcs];

    // Group arcs that share BOTH rounded start AND end (truly overlapping)
    const groups = new Map<string, number[]>();
    for (let i = 0; i < all.length; i++) {
      const a = all[i];
      const key = [
        a.startLat.toFixed(0), a.startLng.toFixed(0),
        a.endLat.toFixed(0), a.endLng.toFixed(0),
      ].join(',');
      const g = groups.get(key) || [];
      g.push(i);
      groups.set(key, g);
    }

    return all.map((arc, i) => {
      const a = arc;
      const key = [
        a.startLat.toFixed(0), a.startLng.toFixed(0),
        a.endLat.toFixed(0), a.endLng.toFixed(0),
      ].join(',');
      const group = groups.get(key)!;
      const groupIndex = group.indexOf(i);
      const groupSize = group.length;
      const altScale = groupSize > 1 ? 0.5 + groupIndex * 0.06 : 0.5;
      // Collect all sectors & values for arcs sharing the same endpoints
      const sectors = group.map(j => all[j].sector).filter(Boolean) as string[];
      const values  = group.map(j => all[j].value).filter(Boolean) as number[];
      return {
        ...arc,
        stroke3D: valueToStroke3D(arc.value),
        stroke2D: valueToStroke2D(arc.value),
        altitudeScale: altScale,
        groupIndex,
        groupSize,
        sectors,
        values,
      };
    });
  }, [rawPrimaryArcs, rawSubArcs]);

  /* ── 3D arc data (with stroke & altitude scale) ───────────────── */
  const arcsData3D = useMemo(
    () =>
      enrichedArcs.map(a => ({
        startLat: a.startLat,
        startLng: a.startLng,
        endLat: a.endLat,
        endLng: a.endLng,
        color: a.color,
        label: a.label,
        stroke: a.stroke3D,
        altitudeScale: a.altitudeScale,
      })),
    [enrichedArcs],
  );

  /* ── 2D arc data (with stroke, group metadata, sectors & values) ── */
  const arcsData2D: MapArc[] = useMemo(
    () =>
      enrichedArcs.map(a => ({
        startLat: a.startLat,
        startLng: a.startLng,
        endLat: a.endLat,
        endLng: a.endLng,
        color: a.color,
        label: a.label,
        stroke: a.stroke2D,
        groupIndex: a.groupIndex,
        groupSize: a.groupSize,
        sectors: a.sector ? [a.sector] : undefined,
        values: a.value  ? [a.value]  : undefined,
      })),
    [enrichedArcs],
  );

  /* ── Points data (shared between 2D & 3D) ────────────────────── */
  const pointsData: MapPoint[] = useMemo(
    () => [
      ...supplyPoints.map(pt => {
        const sev = pointSeverityMap.get(pt.id);
        return {
          lat: pt.lat,
          lng: pt.lng,
          size: 1.0,
          color: sev ? SEVERITY_COLORS[sev] : '#22d3ee',
          label: `${pt.name} — ${pt.material}${sev ? ` [${sev.toUpperCase()}]` : ''}`,
        };
      }),
      ...subPoints,
      ...(headquartersLocation
        ? [
            {
              lat: headquartersLocation.lat,
              lng: headquartersLocation.lng,
              size: 1.4,
              color: '#f43f5e',
              label: 'Headquarters',
            },
          ]
        : []),
    ],
    [supplyPoints, subPoints, headquartersLocation, pointSeverityMap],
  );

  /* ── Pan globe + pause spin when panel triggers focus ──────────── */
  useEffect(() => {
    if (!focusLocation) return;
    if (is3D && globeRef.current) {
      globeRef.current.controls().autoRotate = false;
      globeRef.current.pointOfView(
        { lat: focusLocation.lat, lng: focusLocation.lng, altitude: 1.5 },
        1000,
      );
    }
    const pt = pointsData.find(
      p =>
        Math.abs(p.lat - focusLocation.lat) < 0.5 &&
        Math.abs(p.lng - focusLocation.lng) < 0.5,
    );
    setSelectedLabel(pt?.label ?? null);
  }, [focusLocation, pointsData, is3D]);

  /* ── 3D click handlers ────────────────────────────────────────── */
  const handlePointClick3D = useCallback((point: any) => {
    const globe = globeRef.current;
    if (globe) {
      globe.controls().autoRotate = false;
      globe.pointOfView({ lat: point.lat, lng: point.lng, altitude: 1.5 }, 1000);
    }
    setSelectedLabel(point.label);
  }, []);

  const handleArcClick3D = useCallback((arc: any) => {
    const globe = globeRef.current;
    if (globe) {
      globe.controls().autoRotate = false;
      const midLat = (arc.startLat + arc.endLat) / 2;
      const midLng = (arc.startLng + arc.endLng) / 2;
      globe.pointOfView({ lat: midLat, lng: midLng, altitude: 1.8 }, 1000);
    }
    setSelectedLabel(arc.label || 'Supply Route');
  }, []);

  const handleDismiss = useCallback(() => {
    setSelectedLabel(null);
    if (is3D) {
      const globe = globeRef.current;
      if (globe) {
        globe.controls().autoRotate = true;
        globe.controls().autoRotateSpeed = 0.5;
      }
    }
  }, [is3D]);

  /* ── 2D click handlers ────────────────────────────────────────── */
  const handlePointClick2D = useCallback((point: MapPoint) => {
    setSelectedLabel(point.label);
  }, []);

  const handleArcClick2D = useCallback((arc: MapArc) => {
    setSelectedLabel(arc.label || 'Supply Route');
  }, []);

  /* ── Label renderers (3D hover tooltips) ──────────────────────── */
  const handlePointLabel = useCallback((d: any) => {
    return `<div style="background: rgba(16,16,24,0.9); padding: 8px 12px; border-radius: 8px; font-size: 13px; color: #f0f0f5; border: 1px solid rgba(99,102,241,0.3); backdrop-filter: blur(8px);">${d.label}</div>`;
  }, []);

  const handleArcLabel = useCallback((d: any) => {
    return `<div style="background: rgba(16,16,24,0.9); padding: 8px 12px; border-radius: 8px; font-size: 13px; color: #f0f0f5; border: 1px solid rgba(99,102,241,0.3); backdrop-filter: blur(8px);">${d.label}</div>`;
  }, []);

  const ringsData = headquartersLocation
    ? [{ lat: headquartersLocation.lat, lng: headquartersLocation.lng, maxR: 5, propagationSpeed: 2, repeatPeriod: 800 }]
    : [];

  return (
    <div className={styles.globeContainer}>
      {is3D ? (
        <>
          <GlobeGL
            ref={globeRef}
            globeImageUrl="//unpkg.com/three-globe/example/img/earth-blue-marble.jpg"
            bumpImageUrl="//unpkg.com/three-globe/example/img/earth-topology.png"
            backgroundColor="rgba(0,0,0,0)"
            atmosphereColor="#6366f1"
            atmosphereAltitude={0.25}
            // Points
            pointsData={pointsData}
            pointAltitude={0.01}
            pointRadius="size"
            pointColor="color"
            pointLabel={handlePointLabel}
            onPointClick={handlePointClick3D}
            // Arcs — stroke & altitude driven by datum
            arcsData={arcsData3D}
            arcColor="color"
            arcLabel={handleArcLabel}
            arcDashLength={0.5}
            arcDashGap={0.3}
            arcDashAnimateTime={2000}
            arcStroke="stroke"
            arcAltitudeAutoScale="altitudeScale"
            onArcClick={handleArcClick3D}
            // Globe background click
            onGlobeClick={handleDismiss}
            // Rings
            ringsData={ringsData}
            ringColor={() => '#f43f5e'}
            ringMaxRadius="maxR"
            ringPropagationSpeed="propagationSpeed"
            ringRepeatPeriod="repeatPeriod"
            // Settings
            width={undefined}
            height={undefined}
            animateIn={true}
          />
          {selectedLabel && (
            <div className={styles.infoBox}>
              <span>{selectedLabel}</span>
              <button className={styles.infoBoxClose} onClick={handleDismiss}>✕</button>
            </div>
          )}
        </>
      ) : (
        <SupplyMap2D
          arcsData={arcsData2D}
          pointsData={pointsData}
          selectedLabel={selectedLabel}
          onPointClick={handlePointClick2D}
          onArcClick={handleArcClick2D}
          onDismiss={handleDismiss}
        />
      )}

      {/* 2D / 3D toggle — bottom-left */}
      <button
        className={styles.viewToggle}
        onClick={() => {
          setSelectedLabel(null);
          setIs3D(v => !v);
        }}
      >
        {is3D ? <MapIcon size={16} /> : <GlobeIcon size={16} />}
        <span>{is3D ? '2D Map' : '3D Globe'}</span>
      </button>

      <div className={styles.globeOverlay} />
    </div>
  );
}
