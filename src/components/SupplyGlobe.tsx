import { useEffect, useRef, useCallback } from 'react';
import GlobeGL from 'react-globe.gl';
import type { SupplyPoint, SupplyArc } from '../types';
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

export default function SupplyGlobe({ supplyPoints, headquartersLocation }: Props) {
  const globeRef = useRef<any>(null);

  useEffect(() => {
    const globe = globeRef.current;
    if (!globe) return;
    // Auto rotate
    globe.controls().autoRotate = true;
    globe.controls().autoRotateSpeed = 0.5;
    globe.controls().enableZoom = true;
  }, []);

  // When HQ or points change, point to HQ
  useEffect(() => {
    if (headquartersLocation && globeRef.current) {
      globeRef.current.pointOfView(
        { lat: headquartersLocation.lat, lng: headquartersLocation.lng, altitude: 2 },
        1000
      );
    }
  }, [headquartersLocation]);

  const arcsData: SupplyArc[] = headquartersLocation
    ? supplyPoints.map((pt, i) => ({
        startLat: pt.lat,
        startLng: pt.lng,
        endLat: headquartersLocation.lat,
        endLng: headquartersLocation.lng,
        color: ARC_COLORS[i % ARC_COLORS.length],
      }))
    : [];

  const pointsData = [
    ...supplyPoints.map(pt => ({
      lat: pt.lat,
      lng: pt.lng,
      size: 0.6,
      color: '#22d3ee',
      label: `${pt.name} — ${pt.material}`,
    })),
    ...(headquartersLocation
      ? [{
          lat: headquartersLocation.lat,
          lng: headquartersLocation.lng,
          size: 1,
          color: '#f43f5e',
          label: 'Headquarters',
        }]
      : []),
  ];

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
