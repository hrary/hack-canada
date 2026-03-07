import { createContext, useContext, useState, type ReactNode } from 'react';
import type { User, SupplyPoint, AnalysisResult, SimulationResult, PanelMode, SupplierResearch, AnalysisPhase, RiskFactor, Alternative } from '../types';

interface AppContextType {
  user: User | null;
  setUser: (user: User | null) => void;
  supplyPoints: SupplyPoint[];
  setSupplyPoints: (points: SupplyPoint[]) => void;
  headquartersLocation: { lat: number; lng: number } | null;
  setHeadquartersLocation: (loc: { lat: number; lng: number } | null) => void;
  // Job tracking
  currentJobId: string | null;
  setCurrentJobId: (id: string | null) => void;
  // Panel mode
  panelMode: PanelMode;
  setPanelMode: (mode: PanelMode) => void;
  // Analysis (full result)
  analysisResult: AnalysisResult | null;
  setAnalysisResult: (r: AnalysisResult | null) => void;
  analysisLoading: boolean;
  setAnalysisLoading: (v: boolean) => void;
  // Streaming analysis phases
  analysisPhase: AnalysisPhase;
  setAnalysisPhase: (p: AnalysisPhase) => void;
  supplierResearch: SupplierResearch[];
  setSupplierResearch: (r: SupplierResearch[]) => void;
  streamedRisks: RiskFactor[];
  setStreamedRisks: (r: RiskFactor[]) => void;
  streamedAlternatives: Alternative[];
  setStreamedAlternatives: (a: Alternative[]) => void;
  // Globe focus
  focusLocation: { lat: number; lng: number } | null;
  setFocusLocation: (loc: { lat: number; lng: number } | null) => void;
  // Simulation
  simulationResults: SimulationResult[];
  setSimulationResults: (r: SimulationResult[]) => void;
  simulationLoading: boolean;
  setSimulationLoading: (v: boolean) => void;
}

const AppContext = createContext<AppContextType | undefined>(undefined);

export function AppProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [supplyPoints, setSupplyPoints] = useState<SupplyPoint[]>([]);
  const [headquartersLocation, setHeadquartersLocation] = useState<{ lat: number; lng: number } | null>(null);
  const [currentJobId, setCurrentJobId] = useState<string | null>(null);
  const [panelMode, setPanelMode] = useState<PanelMode>('upload');
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [analysisPhase, setAnalysisPhase] = useState<AnalysisPhase>('idle');
  const [supplierResearch, setSupplierResearch] = useState<SupplierResearch[]>([]);
  const [streamedRisks, setStreamedRisks] = useState<RiskFactor[]>([]);
  const [streamedAlternatives, setStreamedAlternatives] = useState<Alternative[]>([]);
  const [focusLocation, setFocusLocation] = useState<{ lat: number; lng: number } | null>(null);
  const [simulationResults, setSimulationResults] = useState<SimulationResult[]>([]);
  const [simulationLoading, setSimulationLoading] = useState(false);

  return (
    <AppContext.Provider value={{
      user, setUser,
      supplyPoints, setSupplyPoints,
      headquartersLocation, setHeadquartersLocation,
      currentJobId, setCurrentJobId,
      panelMode, setPanelMode,
      analysisResult, setAnalysisResult,
      analysisLoading, setAnalysisLoading,
      analysisPhase, setAnalysisPhase,
      supplierResearch, setSupplierResearch,
      streamedRisks, setStreamedRisks,
      streamedAlternatives, setStreamedAlternatives,
      focusLocation, setFocusLocation,
      simulationResults, setSimulationResults,
      simulationLoading, setSimulationLoading,
    }}>
      {children}
    </AppContext.Provider>
  );
}

export function useAppContext() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useAppContext must be used within AppProvider');
  return ctx;
}
