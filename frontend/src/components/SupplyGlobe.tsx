import { useEffect, useRef, useCallback, useMemo } from 'react';
import GlobeGL from 'react-globe.gl';
import type { SupplyPoint, SupplyArc, SupplierResearch, RiskFactor, RiskSeverity } from '../types';
import { useAppContext } from '../context/AppContext';
import styles from './SupplyGlobe.module.css';

interface Props {
  supplyPoints: SupplyPoint[];
  headquartersLocation: { lat: number; lng: number } | null;
}

const ARC_COLORS: [string, string][] = [
  ['#6366f1', '#a855f7'],
  ['#8b5cf6', '#ec4899'],
  ['#3b82f6', '#22d3ee'],
  ['#6366f1', '#22d3ee'],
  ['#a855f7', '#f43f5e'],
];

const SUB_ARC_COLORS: [string, string][] = [
  ['#facc15', '#f97316'],
  ['#fb923c', '#f43f5e'],
];

const SEVERITY_COLORS: Record<RiskSeverity, string> = {
  low: '#22c55e',
  medium: '#f59e0b',
  high: '#f43f5e',
  critical: '#ef4444',
};

export default function SupplyGlobe({ supplyPoints, headquartersLocation }: Props) {
  const globeRef = useRef<any>(null);
  const { supplierResearch, streamedRisks } = useAppContext();

  useEffect(() => {
    const globe = globeRef.current;
    if (!globe) return;
    globe.controls().autoRotate = true;
    globe.controls().autoRotateSpeed = 0.5;
    globe.controls().enableZoom = true;
  }, []);

  useEffect(() => {
    if (headquartersLocation && globeRef.current) {
      globeRef.current.pointOfView(
        { lat: headquartersLocation.lat, lng: headquartersLocation.lng, altitude: 2 },
        1000,
      );
    }
  }, [headquartersLocation]);

  // Build a map of node_id → worst severity for colour coding
  const severityMap = useMemo(() => {
    const m = new Map<string, RiskSeverity>();
    const order: Record<RiskSeverity, number> = { low: 0, medium: 1, high: 2, critical: 3 };
    for (const r of streamedRisks) {
      const cur = m.get(r.node_id);
      if (!cur || order[r.severity] > order[cur]) m.set(r.node_id, r.severity);
    }
    return m;
  }, [streamedRisks]);

  // Sub-component points from research phase
  const subPoints = useMemo(() => {
    const pts: { lat: number; lng: number; size: number; color: string; label: string }[] = [];
    for (const res of supplierResearch) {
      for (const sc of res.sub_components) {
        if (!sc.lat && !sc.lng) continue;
        pts.push({
          lat: sc.lat,
          lng: sc.lng,
          size: 0.35,
          color: '#facc15',
          label: `${sc.component} — ${sc.source_company || sc.source_country}`,
        });
      }
    }
    return pts;
  }, [supplierResearch]);

  // Arcs: primary → HQ
  const primaryArcs: SupplyArc[] = headquartersLocation
    ? supplyPoints.map((pt, i) => ({
        startLat: pt.lat,
        startLng: pt.lng,
        endLat: headquartersLocation.lat,
        endLng: headquartersLocation.lng,
        color: ARC_COLORS[i % ARC_COLORS.length],
      }))
    : [];

  // Arcs: sub-component → parent supplier
  const subArcs = useMemo(() => {
    const arcs: SupplyArc[] = [];
    for (const res of supplierResearch) {
      const parent = supplyPoints.find(p => p.id === res.node_id);
      if (!parent) continue;
      for (const sc of res.sub_components) {
        if (!sc.lat && !sc.lng) continue;
        arcs.push({
          startLat: sc.lat,
          startLng: sc.lng,
          endLat: parent.lat,
          endLng: parent.lng,
          color: SUB_ARC_COLORS[arcs.length % SUB_ARC_COLORS.length],
        });
      }
    }
    return arcs;
  }, [supplierResearch, supplyPoints]);

  const arcsData = [...primaryArcs, ...subArcs];

  // Colour primary supply points by severity when available
  const pointsData = useMemo(() => [
    ...supplyPoints.map(pt => {
      const sev = severityMap.get(pt.id);
      return {
        lat: pt.lat,
        lng: pt.lng,
        size: 0.6,
        color: sev ? SEVERITY_COLORS[sev] : '#22d3ee',
        label: `${pt.name} — ${pt.material}${sev ? ` [${sev.toUpperCase()}]` : ''}`,
      };
    }),
    ...subPoints,
    ...(headquartersLocation
      ? [{
          lat: headquartersLocation.lat,
          lng: headquartersLocation.lng,
          size: 1,
          color: '#f43f5e',
          label: 'Headquarters',
        }]
      : []),
  ], [supplyPoints, subPoints, headquartersLocation, severityMap]);

  const ringsData = headquartersLocation
    ? [{ lat: headquartersLocation.lat, lng: headquartersLocation.lng, maxR: 5, propagationSpeed: 2, repeatPeriod: 800 }]
    : [];

  const handlePointLabel = useCallback((d: any) => {
    return `<div style="background: rgba(16,16,24,0.9); padding: 8px 12px; border-radius: 8px; font-size: 13px; color: #f0f0f5; border: 1px solid rgba(99,102,241,0.3); backdrop-filter: blur(8px);">${d.label}</div>`;
  }, []);

  return (
    <div className={styles.globeContainer}>
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
        // Arcs
        arcsData={arcsData}
        arcColor="color"
        arcDashLength={0.5}
        arcDashGap={0.3}
        arcDashAnimateTime={2000}
        arcStroke={0.5}
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
      <div className={styles.globeOverlay} />
    </div>
  );
}
