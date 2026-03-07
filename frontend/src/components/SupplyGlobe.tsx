import { useEffect, useRef, useCallback, useMemo, useState } from 'react';
import GlobeGL from 'react-globe.gl';
import type { SupplyPoint, RiskSeverity } from '../types';
import { useAppContext } from '../context/AppContext';
import styles from './SupplyGlobe.module.css';

interface Props {
  supplyPoints: SupplyPoint[];
  headquartersLocation: { lat: number; lng: number } | null;
}

const SEVERITY_ARC_COLORS: Record<RiskSeverity, [string, string]> = {
  low: ['#22c55e', '#4ade80'],
  medium: ['#f59e0b', '#fbbf24'],
  high: ['#f43f5e', '#fb7185'],
  critical: ['#ef4444', '#f87171'],
};

const DEFAULT_ARC_COLOR: [string, string] = ['#6366f1', '#a855f7'];

const SEVERITY_COLORS: Record<RiskSeverity, string> = {
  low: '#22c55e',
  medium: '#f59e0b',
  high: '#f43f5e',
  critical: '#ef4444',
};

export default function SupplyGlobe({ supplyPoints, headquartersLocation }: Props) {
  const globeRef = useRef<any>(null);
  const { supplierResearch, streamedRisks, focusLocation } = useAppContext();
  const [selectedLabel, setSelectedLabel] = useState<string | null>(null);

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

  // Map backend node_id → frontend SupplyPoint by matching supplier name
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

  // Translate to frontend point.id → severity
  const pointSeverityMap = useMemo(() => {
    const m = new Map<string, RiskSeverity>();
    for (const [nid, pt] of nodeIdToPoint) {
      const sev = severityMap.get(nid);
      if (sev) m.set(pt.id, sev);
    }
    return m;
  }, [nodeIdToPoint, severityMap]);

  // Sub-component points from research phase
  const subPoints = useMemo(() => {
    const pts: { lat: number; lng: number; size: number; color: string; label: string }[] = [];
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

  // Arcs: primary → HQ (color by severity)
  const primaryArcs = useMemo(() => {
    if (!headquartersLocation) return [];
    return supplyPoints.map(pt => {
      const sev = pointSeverityMap.get(pt.id);
      return {
        startLat: pt.lat,
        startLng: pt.lng,
        endLat: headquartersLocation.lat,
        endLng: headquartersLocation.lng,
        color: sev ? SEVERITY_ARC_COLORS[sev] : DEFAULT_ARC_COLOR,
        label: `${pt.name} → Headquarters`,
      };
    });
  }, [supplyPoints, headquartersLocation, pointSeverityMap]);

  // Arcs: sub-component → parent supplier (color by parent severity)
  const subArcs = useMemo(() => {
    const arcs: { startLat: number; startLng: number; endLat: number; endLng: number; color: [string, string]; label: string }[] = [];
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
          color: sev ? SEVERITY_ARC_COLORS[sev] : DEFAULT_ARC_COLOR,
          label: `${sc.component} (${sc.source_company || sc.source_country}) → ${parent.name}`,
        });
      }
    }
    return arcs;
  }, [supplierResearch, nodeIdToPoint, pointSeverityMap]);

  const arcsData = useMemo(() => [...primaryArcs, ...subArcs], [primaryArcs, subArcs]);

  // Colour primary supply points by severity when available
  const pointsData = useMemo(() => [
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
      ? [{
          lat: headquartersLocation.lat,
          lng: headquartersLocation.lng,
          size: 1.4,
          color: '#f43f5e',
          label: 'Headquarters',
        }]
      : []),
  ], [supplyPoints, subPoints, headquartersLocation, pointSeverityMap]);

  // Pan globe + pause spin when panel triggers focus
  useEffect(() => {
    if (focusLocation && globeRef.current) {
      globeRef.current.controls().autoRotate = false;
      globeRef.current.pointOfView(
        { lat: focusLocation.lat, lng: focusLocation.lng, altitude: 1.5 },
        1000,
      );
      const pt = pointsData.find(
        p => Math.abs(p.lat - focusLocation.lat) < 0.5 &&
             Math.abs(p.lng - focusLocation.lng) < 0.5,
      );
      setSelectedLabel(pt?.label ?? null);
    }
  }, [focusLocation, pointsData]);

  // ── Click handlers ─────────────────────────────────────────────
  const handlePointClick = useCallback((point: any) => {
    const globe = globeRef.current;
    if (globe) {
      globe.controls().autoRotate = false;
      globe.pointOfView({ lat: point.lat, lng: point.lng, altitude: 1.5 }, 1000);
    }
    setSelectedLabel(point.label);
  }, []);

  const handleArcClick = useCallback((arc: any) => {
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
    const globe = globeRef.current;
    if (globe) {
      globe.controls().autoRotate = true;
      globe.controls().autoRotateSpeed = 0.5;
    }
  }, []);

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
        onPointClick={handlePointClick}
        // Arcs
        arcsData={arcsData}
        arcColor="color"
        arcLabel={handleArcLabel}
        arcDashLength={0.5}
        arcDashGap={0.3}
        arcDashAnimateTime={2000}
        arcStroke={0.8}
        onArcClick={handleArcClick}
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
      <div className={styles.globeOverlay} />
    </div>
  );
}
