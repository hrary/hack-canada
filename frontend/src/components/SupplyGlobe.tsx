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
  const { supplierResearch, streamedRisks, focusLocation, simulationImpactMap, analysisPhase } = useAppContext();
  const [selectedLabel, setSelectedLabel] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<SupplyPoint | null>(null);
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

  /* ── Node ID → SupplyPoint matching ─────────────────────────── */
  const nodeIdToPoint = useMemo(() => {
    const m = new Map<string, SupplyPoint>();
    // Direct mapping: supply points already carry backend node IDs
    for (const pt of supplyPoints) {
      m.set(pt.id, pt);
    }
    // Also map from supplier research (covers cases where IDs differ)
    for (const res of supplierResearch) {
      if (!m.has(res.node_id)) {
        const pt = supplyPoints.find(
          p => p.supplier === res.supplier || p.name === res.supplier,
        );
        if (pt) m.set(res.node_id, pt);
      }
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

  /* ── Simulation impact → frontend point ID ────────────────────── */
  const simPointSeverityMap = useMemo(() => {
    const m = new Map<string, string>();
    if (simulationImpactMap.size === 0) return m;
    for (const [nid, pt] of nodeIdToPoint) {
      const sev = simulationImpactMap.get(nid);
      if (sev) m.set(pt.id, sev);
    }
    return m;
  }, [nodeIdToPoint, simulationImpactMap]);

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
  const SIM_COLORS: Record<string, [string, string]> = {
    low: ['#22c55e', '#4ade80'],
    medium: ['#f59e0b', '#fbbf24'],
    high: ['#ef4444', '#f87171'],
    critical: ['#a855f7', '#c084fc'],
  };

  const rawPrimaryArcs = useMemo(() => {
    if (!headquartersLocation) return [];
    const hasSim = simulationImpactMap.size > 0;
    return supplyPoints.map(pt => {
      const sev = pointSeverityMap.get(pt.id);
      const simSev = simPointSeverityMap.get(pt.id);
      // During simulation: affected arcs use sim severity colors, unaffected dim to grey
      let color: [string, string];
      if (hasSim) {
        color = simSev
          ? (SIM_COLORS[simSev] ?? SIM_COLORS.medium)
          : ['#374151', '#4b5563']; // dim grey for unaffected
      } else {
        color = sev ? SEVERITY_ARC_COLORS[sev] : DEFAULT_ARC_COLOR;
      }
      return {
        startLat: pt.lat,
        startLng: pt.lng,
        endLat: headquartersLocation.lat,
        endLng: headquartersLocation.lng,
        color,
        label: `${pt.name} → Headquarters${simSev ? ` [SIM: ${simSev.toUpperCase()}]` : ''}`,
        value: pt.value,
        isSub: false,
      };
    });
  }, [supplyPoints, headquartersLocation, pointSeverityMap, simPointSeverityMap, simulationImpactMap]);

  const rawSubArcs = useMemo(() => {
    const arcs: {
      startLat: number; startLng: number;
      endLat: number; endLng: number;
      color: [string, string]; label: string; value?: number; isSub: boolean;
    }[] = [];
    const hasSim = simulationImpactMap.size > 0;
    for (const res of supplierResearch) {
      const parent = nodeIdToPoint.get(res.node_id);
      if (!parent) continue;
      const sev = pointSeverityMap.get(parent.id);
      const simSev = simPointSeverityMap.get(parent.id);
      let color: [string, string];
      if (hasSim) {
        color = simSev
          ? (SIM_COLORS[simSev] ?? SIM_COLORS.medium)
          : ['#374151', '#4b5563'];
      } else {
        color = sev ? SEVERITY_ARC_COLORS[sev] : DEFAULT_ARC_COLOR;
      }
      for (const sc of res.sub_components) {
        if (!sc.lat && !sc.lng) continue;
        arcs.push({
          startLat: sc.lat,
          startLng: sc.lng,
          endLat: parent.lat,
          endLng: parent.lng,
          color,
          label: `${sc.component} (${sc.source_company || sc.source_country}) → ${parent.name}`,
          value: parent.value ? parent.value * 0.2 : undefined,
          isSub: true,
        });
      }
    }
    return arcs;
  }, [supplierResearch, nodeIdToPoint, pointSeverityMap, simPointSeverityMap, simulationImpactMap]);

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
      // Subtle altitude bump only for truly overlapping arcs
      // groupIndex 0 → baseline 0.5, each extra → +0.06 (barely visible)
      const altScale = groupSize > 1 ? 0.5 + groupIndex * 0.06 : 0.5;
      // Sub-component edges get thinner strokes
      const subScale = arc.isSub ? 0.45 : 1;
      return {
        ...arc,
        stroke3D: valueToStroke3D(arc.value) * subScale,
        stroke2D: valueToStroke2D(arc.value) * subScale,
        altitudeScale: altScale,
        groupIndex,
        groupSize,
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

  /* ── 2D arc data (with stroke & group metadata for offset) ────── */
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
      })),
    [enrichedArcs],
  );

  /* ── Points data (shared between 2D & 3D) ────────────────────── */
  const SIM_NODE_COLORS: Record<string, string> = {
    low: '#22c55e',
    medium: '#f59e0b',
    high: '#ef4444',
    critical: '#a855f7',
  };

  const pointsData: MapPoint[] = useMemo(() => {
    const hasSim = simulationImpactMap.size > 0;
    return [
      ...supplyPoints.map(pt => {
        const sev = pointSeverityMap.get(pt.id);
        const simSev = simPointSeverityMap.get(pt.id);
        let color: string;
        let size: number;
        if (hasSim) {
          color = simSev ? (SIM_NODE_COLORS[simSev] ?? '#f59e0b') : '#374151';
          size = simSev ? 1.5 : 0.6; // affected nodes bigger, unaffected shrink
        } else {
          color = sev ? SEVERITY_COLORS[sev] : '#22d3ee';
          size = 1.0;
        }
        return {
          lat: pt.lat,
          lng: pt.lng,
          size,
          color,
          label: `${pt.name} — ${pt.material}${simSev ? ` [SIM: ${simSev.toUpperCase()}]` : sev ? ` [${sev.toUpperCase()}]` : ''}`,
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
    ];
  }, [supplyPoints, subPoints, headquartersLocation, pointSeverityMap, simPointSeverityMap, simulationImpactMap]);

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
  const findSupplyPoint = useCallback((lat: number, lng: number) => {
    return supplyPoints.find(
      p => Math.abs(p.lat - lat) < 0.01 && Math.abs(p.lng - lng) < 0.01,
    ) ?? null;
  }, [supplyPoints]);

  const handlePointClick3D = useCallback((point: any) => {
    const globe = globeRef.current;
    if (globe) {
      globe.controls().autoRotate = false;
      globe.pointOfView({ lat: point.lat, lng: point.lng, altitude: 1.5 }, 1000);
    }
    setSelectedLabel(point.label);
    setSelectedNode(findSupplyPoint(point.lat, point.lng));
  }, [findSupplyPoint]);

  const handleArcClick3D = useCallback((arc: any) => {
    const globe = globeRef.current;
    if (globe) {
      globe.controls().autoRotate = false;
      const midLat = (arc.startLat + arc.endLat) / 2;
      const midLng = (arc.startLng + arc.endLng) / 2;
      globe.pointOfView({ lat: midLat, lng: midLng, altitude: 1.8 }, 1000);
    }
    setSelectedLabel(arc.label || 'Supply Route');
    setSelectedNode(null);
  }, []);

  const handleDismiss = useCallback(() => {
    setSelectedLabel(null);
    setSelectedNode(null);
    if (is3D) {
      const globe = globeRef.current;
      if (globe) {
        globe.controls().autoRotate = true;
        globe.controls().autoRotateSpeed = 0.5;
      }
    }
  }, [is3D]);

  /* ── Lookup helpers for selected node details ──────────────────── */
  const selectedResearch = useMemo(() => {
    if (!selectedNode) return null;
    return supplierResearch.find(
      r => r.supplier === selectedNode.supplier || r.supplier === selectedNode.name,
    ) ?? null;
  }, [selectedNode, supplierResearch]);

  const selectedRisks = useMemo(() => {
    if (!selectedResearch) return [];
    return streamedRisks.filter(r => r.node_id === selectedResearch.node_id);
  }, [selectedResearch, streamedRisks]);

  const worstSeverity = useMemo(() => {
    if (selectedRisks.length === 0) return null;
    const order: Record<string, number> = { low: 0, medium: 1, high: 2, critical: 3 };
    let worst = selectedRisks[0];
    for (const r of selectedRisks) {
      if ((order[r.severity] ?? 0) > (order[worst.severity] ?? 0)) worst = r;
    }
    return worst.severity;
  }, [selectedRisks]);

  /* ── 2D click handlers ────────────────────────────────────────── */
  const handlePointClick2D = useCallback((point: MapPoint) => {
    setSelectedLabel(point.label);
    setSelectedNode(findSupplyPoint(point.lat, point.lng));
  }, [findSupplyPoint]);

  const handleArcClick2D = useCallback((arc: MapArc) => {
    setSelectedLabel(arc.label || 'Supply Route');
    setSelectedNode(null);
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
              {selectedNode ? (
                <div className={styles.nodeDetail}>
                  <strong>{selectedNode.supplier || selectedNode.name}</strong>
                  <span className={styles.nodeDetailRow}>
                    {selectedNode.material} · {selectedNode.country}
                    {selectedNode.value != null && ` · $${selectedNode.value.toLocaleString()}`}
                  </span>
                  {worstSeverity && (
                    <span
                      className={styles.riskBadge}
                      style={{
                        background:
                          worstSeverity === 'critical' ? 'rgba(168,85,247,0.25)' :
                          worstSeverity === 'high' ? 'rgba(239,68,68,0.25)' :
                          worstSeverity === 'medium' ? 'rgba(245,158,11,0.25)' :
                          'rgba(34,197,94,0.25)',
                        color:
                          worstSeverity === 'critical' ? '#c084fc' :
                          worstSeverity === 'high' ? '#f87171' :
                          worstSeverity === 'medium' ? '#fbbf24' :
                          '#4ade80',
                      }}
                    >
                      {worstSeverity} risk
                    </span>
                  )}
                  {selectedResearch ? (
                    selectedResearch.findings === 'NO_DATA' ? (
                      <span className={styles.noData}>No public information found for this company</span>
                    ) : (
                      <>
                        <p className={styles.nodeDetailFindings}>{selectedResearch.findings}</p>
                        {selectedResearch.sub_components.length > 0 && (
                          <div className={styles.nodeDetailSubs}>
                            {selectedResearch.sub_components.slice(0, 4).map((sc, i) => (
                              <span key={i} className={styles.subChip}>
                                {sc.component}
                              </span>
                            ))}
                            {selectedResearch.sub_components.length > 4 && (
                              <span className={styles.subChip}>
                                +{selectedResearch.sub_components.length - 4}
                              </span>
                            )}
                          </div>
                        )}
                      </>
                    )
                  ) : (
                    <span className={styles.noData}>
                      {analysisPhase === 'done'
                        ? 'No public information found for this company'
                        : 'Run analysis to see company details'}
                    </span>
                  )}
                </div>
              ) : (
                <span>{selectedLabel}</span>
              )}
              <button className={styles.infoBoxClose} onClick={handleDismiss}>✕</button>
            </div>
          )}
        </>
      ) : (
        <SupplyMap2D
          arcsData={arcsData2D}
          pointsData={pointsData}
          selectedLabel={selectedLabel}
          nodeDetail={selectedNode ? {
            name: selectedNode.supplier || selectedNode.name,
            material: selectedNode.material,
            country: selectedNode.country,
            value: selectedNode.value,
          } : null}
          nodeResearch={selectedResearch}
          nodeWorstSeverity={worstSeverity}
          analysisPhase={analysisPhase}
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
          setSelectedNode(null);
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
