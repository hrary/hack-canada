export interface SupplyPoint {
  id: string;
  name: string;
  lat: number;
  lng: number;
  material: string;
  supplier: string;
  country: string;
  value?: number; // estimated monetary value (USD) of this supply link
}

export interface SupplyArc {
  startLat: number;
  startLng: number;
  endLat: number;
  endLng: number;
  color: [string, string];
}

export interface User {
  email: string;
  name: string;
  company: string;
}

// ── Analysis / Simulation types (mirror backend schemas) ─────────────

export type RiskSeverity = 'low' | 'medium' | 'high' | 'critical';

export interface RiskFactor {
  node_id: string;
  category: string;
  description: string;
  severity: RiskSeverity;
  estimated_cost_impact?: number | null;
}

export interface Alternative {
  original_node_id: string;
  suggested_supplier: string;
  suggested_country: string;
  lat: number;
  lng: number;
  reason: string;
  estimated_savings?: number | null;
}

export interface AnalysisResult {
  job_id: string;
  status: string;
  supply_chain: { headquarters: { lat: number; lng: number } | null; nodes: SupplyPoint[] };
  risks: RiskFactor[];
  alternatives: Alternative[];
  supplier_research: SupplierResearch[];
  summary: string;
  tariff_data?: TariffData | null;
}

// ── Tariff types ─────────────────────────────────────────────────────

export interface TariffNodeBreakdown {
  node_id: string;
  name: string;
  country: string;
  material: string;
  hs_code: string | null;
  description?: string;
  value: number;
  mfn_rate: number | null;
  applied_rate: number | null;
  tariff_cost: number;
  rate_type: string;
  notes: string;
}

export interface TariffData {
  nodes: TariffNodeBreakdown[];
  total_goods_value: number;
  total_tariff_cost: number;
  net_tariff_pct: number;
  summary: string;
}

// ── Supplier research (sub-component discovery) ──────────────────────

export interface SubComponent {
  component: string;
  source_company: string;
  source_country: string;
  lat: number;
  lng: number;
}

export interface SupplierResearch {
  node_id: string;
  supplier: string;
  findings: string;
  sub_components: SubComponent[];
}

/** Which phase the streaming analysis is in */
export type AnalysisPhase = 'idle' | 'research' | 'risk' | 'done';

export interface SimulationScenario {
  description: string;
  affected_countries: string[];
  tariff_change_pct?: number | null;
  trade_deal?: string | null;
}

export interface NodeImpact {
  node_id: string;
  impact_description: string;
  cost_change_pct: number;
  severity: string;  // low | medium | high | critical
}

export interface Recommendation {
  title: string;
  description: string;
  priority: string;  // high | medium | low
  type: string;      // mitigate | opportunity
}

export interface SimulationResult {
  job_id: string;
  scenario: SimulationScenario;
  impacts: NodeImpact[];
  recommendations: Recommendation[];
  total_cost_impact_pct: number;
  summary: string;
}

export type PanelMode = 'upload' | 'analysis' | 'simulation';
