import { useState, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Upload, FileText, Type, MapPin, Package,
  CheckCircle, AlertCircle, Loader2, BarChart3, FlaskConical,
  ArrowLeft, AlertTriangle, Lightbulb, Play, Send, Search,
  ShieldAlert, TrendingUp, TrendingDown, Zap, DollarSign, Download,
  ChevronDown, ChevronUp, Percent, Newspaper,
} from 'lucide-react';
import { useAppContext } from '../context/AppContext';
import {
  uploadSupplyChainText,
  getJobChain,
  streamAnalysis,
  runSimulation,
  scanNews,
} from '../api/supplyChain';
import type { SupplyPoint, PanelMode, SimulationScenario, NewsArticle } from '../types';
import styles from './SupplyPanel.module.css';

function parseCSV(text: string): SupplyPoint[] {
  const lines = text.split('\n').filter(line => line.trim());
  if (lines.length < 2) return [];
  const headers = lines[0].split(',').map(h => h.trim().toLowerCase());
  const points: SupplyPoint[] = [];
  for (let i = 1; i < lines.length; i++) {
    const vals = lines[i].split(',').map(v => v.trim());
    const get = (key: string) => {
      const idx = headers.indexOf(key);
      return idx >= 0 ? vals[idx] : '';
    };
    const lat = parseFloat(get('lat') || get('latitude') || '0');
    const lng = parseFloat(get('lng') || get('longitude') || get('lon') || '0');
    const rawVal = get('value') || get('amount');
    const value = rawVal ? parseFloat(rawVal) : undefined;
    const name = get('name') || get('supplier') || `Point ${i}`;
    const supplier = get('supplier');
    const material = get('material');
    const country = get('country');
    // Skip completely empty rows
    if (!name && !supplier && !material) continue;
    points.push({
      id: crypto.randomUUID(),
      name,
      lat: isNaN(lat) ? 0 : lat,
      lng: isNaN(lng) ? 0 : lng,
      material: material || '',
      supplier: supplier || '',
      country: country || '',
      value: isNaN(value as number) ? undefined : value,
    });
  }
  return points;
}

type UploadTab = 'csv' | 'text';
type UploadStatus = 'idle' | 'uploading' | 'success' | 'error';

const SAMPLE_CSV = `name,lat,lng,material,supplier,country,value
Shenzhen Electronics,22.5431,114.0579,Smartphone Assemblies,Foxconn,China,85000000
Detroit Motors,42.3314,-83.0458,Electric Vehicle Drivetrains,BorgWarner,United States,120000000
Stuttgart Precision,48.7758,9.1829,Automotive Sensors & ECUs,Bosch GmbH,Germany,63000000
Seoul Displays,37.5665,126.978,OLED Display Panels,Samsung Display,South Korea,95000000
Osaka Robotics,34.6937,135.5023,Industrial Robotic Arms,Fanuc Corporation,Japan,47000000
Guadalajara Aerospace,20.6597,-103.3496,Aircraft Wiring Harnesses,Safran SA,Mexico,38000000`;

export default function SupplyPanel() {
  const {
    headquartersLocation, setHeadquartersLocation,
    supplyPoints, setSupplyPoints,
    currentJobId, setCurrentJobId,
    panelMode, setPanelMode,
    analysisResult, setAnalysisResult,
    analysisLoading, setAnalysisLoading,
    analysisPhase, setAnalysisPhase,
    supplierResearch, setSupplierResearch,
    streamedRisks, setStreamedRisks,
    streamedAlternatives, setStreamedAlternatives,
    newsArticles, setNewsArticles,
    setFocusLocation,
    simulationResults, setSimulationResults,
    simulationLoading, setSimulationLoading,
  } = useAppContext();
  const [activeTab, setActiveTab] = useState<UploadTab>('csv');
  const [hqLat, setHqLat] = useState(headquartersLocation?.lat.toString() ?? '43.65');
  const [hqLng, setHqLng] = useState(headquartersLocation?.lng.toString() ?? '-79.38');

  // Upload state
  const [uploadStatus, setUploadStatus] = useState<UploadStatus>('idle');
  const [statusMessage, setStatusMessage] = useState('');

  // CSV state
  const [csvContent, setCsvContent] = useState('');
  const [csvFileName, setCsvFileName] = useState('');
  const csvInputRef = useRef<HTMLInputElement>(null);

  // Text state
  const [textContent, setTextContent] = useState('');

  // Tariff breakdown toggle
  const [tariffOpen, setTariffOpen] = useState(false);

  // News scanning state
  const [newsLoading, setNewsLoading] = useState(false);

  const handleSetHQ = () => {
    const lat = parseFloat(hqLat);
    const lng = parseFloat(hqLng);
    if (!isNaN(lat) && !isNaN(lng)) {
      setHeadquartersLocation({ lat, lng });
    }
  };

  const handleLoadSample = () => {
    setCsvContent(SAMPLE_CSV);
    setCsvFileName('sample-data.csv');
    setActiveTab('csv');
    // Immediately show on globe
    setSupplyPoints(parseCSV(SAMPLE_CSV));
    if (!headquartersLocation) {
      setHeadquartersLocation({ lat: 43.6532, lng: -79.3832 });
      setHqLat('43.6532');
      setHqLng('-79.3832');
    }
  };

  const handleCSVFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setCsvFileName(file.name);
    const reader = new FileReader();
    reader.onload = (evt) => {
      setCsvContent(evt.target?.result as string);
    };
    reader.readAsText(file);
    e.target.value = '';
  };

  const handleSubmit = async () => {
    setUploadStatus('uploading');
    setStatusMessage('');

    // For CSV, parse and display on globe immediately (points with coords)
    if (activeTab === 'csv') {
      if (!csvContent.trim()) {
        setUploadStatus('error');
        setStatusMessage('Please provide CSV content to upload.');
        return;
      }
      const parsed = parseCSV(csvContent);
      const withCoords = parsed.filter(p => p.lat !== 0 || p.lng !== 0);
      if (withCoords.length > 0) {
        setSupplyPoints(withCoords);
      }
    }

    // Fire API and capture jobId
    try {
      const content = activeTab === 'csv' ? csvContent : textContent;
      if (!content.trim()) {
        setUploadStatus('error');
        setStatusMessage('Please provide content to upload.');
        return;
      }
      const resp = await uploadSupplyChainText({
        format: activeTab,
        content,
        fileName: activeTab === 'csv' ? csvFileName : undefined,
      });
      const jobId = resp.job_id ?? null;
      setCurrentJobId(jobId);

      // Fetch backend-parsed chain (includes LLM-geocoded coords)
      if (jobId) {
        try {
          const chain = await getJobChain(jobId);
          if (chain.nodes?.length) {
            setSupplyPoints(chain.nodes.map((n: any) => ({
              id: n.id,
              name: n.name,
              lat: n.lat,
              lng: n.lng,
              material: n.material || '',
              supplier: n.supplier || '',
              country: n.country || '',
              value: n.value || undefined,
            })));
          }
        } catch { /* fall back to local parsing */ }
      }

      setUploadStatus('success');
      setStatusMessage(
        activeTab === 'csv'
          ? `Mapped ${parseCSV(csvContent).length} suppliers on the globe.`
          : 'Text uploaded and processed.'
      );
      if (activeTab === 'csv') { setCsvContent(''); setCsvFileName(''); }
      else { setTextContent(''); }

      // Switch to analysis mode after successful upload
      setPanelMode('analysis');
    } catch (err) {
      setUploadStatus('error');
      setStatusMessage(err instanceof Error ? err.message : 'Upload failed.');
    }
  };

  const abortRef = useRef<AbortController | null>(null);

  const handleRunAnalysis = () => {
    if (!currentJobId) return;

    // Abort any in-flight stream
    abortRef.current?.abort();

    // Reset phase state
    setAnalysisLoading(true);
    setAnalysisPhase('research');
    setAnalysisResult(null);
    setSupplierResearch([]);
    setStreamedRisks([]);
    setStreamedAlternatives([]);
    setSimulationResults([]); // clear any previous simulation

    abortRef.current = streamAnalysis(currentJobId, {
      onStatus(data) {
        if (data.phase === 'research') setAnalysisPhase('research');
        else if (data.phase === 'risk') setAnalysisPhase('risk');
      },
      onResearch(data) {
        setSupplierResearch(data.supplier_research);
        setAnalysisPhase('risk');
      },
      onRisk(data) {
        setStreamedRisks(data.risks);
        setStreamedAlternatives(data.alternatives);
      },
      onDone(result) {
        setAnalysisResult(result);
        setAnalysisPhase('done');
        setAnalysisLoading(false);
      },
      onError() {
        setAnalysisPhase('done');
        setAnalysisLoading(false);
      },
    });
  };

  const handleRunSimulation = async () => {
    if (!currentJobId || !scenarioText.trim()) return;
    setSimulationLoading(true);
    try {
      const scenario: SimulationScenario = {
        description: scenarioText,
        affected_countries: [],
      };
      const results = await runSimulation(currentJobId, [scenario]);
      setSimulationResults(results);
    } catch {
      setSimulationResults([]);
    } finally {
      setSimulationLoading(false);
    }
  };

  // Simulation scenario input
  const [scenarioText, setScenarioText] = useState('');

  const handleScanNews = async () => {
    if (!currentJobId) return;
    setNewsLoading(true);
    setNewsArticles([]);
    try {
      const resp = await scanNews(currentJobId);
      setNewsArticles(resp.news_articles ?? []);
    } catch {
      setNewsArticles([]);
    } finally {
      setNewsLoading(false);
    }
  };

  const handleExportJSON = () => {
    const payload = {
      supply_chain: supplyPoints,
      analysis: analysisResult ? {
        summary: analysisResult.summary,
        risks: streamedRisks,
        alternatives: streamedAlternatives,
        supplier_research: supplierResearch,
      } : null,
      simulations: simulationResults.length > 0 ? simulationResults : null,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `provenance-report-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Pan globe to a supply node by backend ID (matched via supplier name)
  const focusNode = (nodeId: string) => {
    let pt = supplyPoints.find(p => p.id === nodeId);
    if (!pt) {
      const res = supplierResearch.find(r => r.node_id === nodeId);
      if (res) {
        pt = supplyPoints.find(p => p.supplier === res.supplier || p.name === res.supplier);
      }
    }
    if (pt) setFocusLocation({ lat: pt.lat, lng: pt.lng });
  };

  const tabs: { key: UploadTab; label: string; icon: React.ReactNode }[] = [
    { key: 'csv', label: 'CSV', icon: <FileText size={14} /> },
    { key: 'text', label: 'Text', icon: <Type size={14} /> },
  ];

  const modeTabs: { key: PanelMode; label: string; icon: React.ReactNode }[] = [
    { key: 'analysis', label: 'Analysis', icon: <BarChart3 size={14} /> },
    { key: 'simulation', label: 'Simulation', icon: <FlaskConical size={14} /> },
    { key: 'news', label: 'News', icon: <Newspaper size={14} /> },
  ];

  // ── Upload view ─────────────────────────────────────────────────────
  if (panelMode === 'upload') {
    return (
      <div className={styles.panel}>
        <div className={styles.panelHeader}>
          <h2 className={styles.panelTitle}>Supply Chain Upload</h2>
        </div>

        {/* Headquarters */}
        <div className={styles.section}>
          <div className={styles.sectionLabel}>
            <MapPin size={14} />
            Headquarters
          </div>
          <div className={styles.hqRow}>
            <input
              className={styles.smallInput}
              type="text"
              placeholder="Lat"
              value={hqLat}
              onChange={e => setHqLat(e.target.value)}
            />
            <input
              className={styles.smallInput}
              type="text"
              placeholder="Lng"
              value={hqLng}
              onChange={e => setHqLng(e.target.value)}
            />
            <button className={styles.setBtn} onClick={handleSetHQ}>Set</button>
          </div>
        </div>

        {/* Sample data */}
        <div className={styles.section}>
          <button className={styles.actionBtn} onClick={handleLoadSample}>
            <Package size={15} />
            Load Sample Data
          </button>
        </div>

        {/* Tab switcher */}
        <div className={styles.tabBar}>
          {tabs.map(tab => (
            <button
              key={tab.key}
              className={`${styles.tab} ${activeTab === tab.key ? styles.tabActive : ''}`}
              onClick={() => { setActiveTab(tab.key); setUploadStatus('idle'); setStatusMessage(''); }}
            >
              {tab.icon}
              {tab.label}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div className={styles.tabContent}>
          <AnimatePresence mode="wait">
            {activeTab === 'csv' && (
              <motion.div
                key="csv"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.2 }}
                className={styles.tabPanel}
              >
                <label
                  className={styles.dropZone}
                  onClick={() => csvInputRef.current?.click()}
                >
                  <Upload size={24} />
                  {csvFileName ? (
                    <span className={styles.dropZoneFile}>{csvFileName}</span>
                  ) : (
                    <>
                      <span>Click to upload CSV</span>
                      <span className={styles.dropZoneHint}>name, material, supplier, country (lat/lng optional)</span>
                    </>
                  )}
                  <input
                    ref={csvInputRef}
                    type="file"
                    accept=".csv"
                    onChange={handleCSVFile}
                    hidden
                  />
                </label>
                {csvContent && (
                  <textarea
                    className={styles.textArea}
                    value={csvContent}
                    onChange={e => setCsvContent(e.target.value)}
                    rows={6}
                    placeholder="CSV content will appear here..."
                  />
                )}
              </motion.div>
            )}

            {activeTab === 'text' && (
              <motion.div
                key="text"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.2 }}
                className={styles.tabPanel}
              >
                <textarea
                  className={styles.textArea}
                  value={textContent}
                  onChange={e => setTextContent(e.target.value)}
                  rows={10}
                  placeholder={"Paste your supply chain information here...\n\nExample:\nOur semiconductors are sourced from Foxconn in Shenzhen, China.\nSteel alloys come from Gerdau SA in São Paulo, Brazil.\nPrecision parts are manufactured by Bosch GmbH in Stuttgart, Germany."}
                />
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Submit */}
        <div className={styles.submitSection}>
          <button
            className={styles.submitBtn}
            onClick={handleSubmit}
            disabled={uploadStatus === 'uploading'}
          >
            {uploadStatus === 'uploading' ? (
              <><Loader2 size={16} className={styles.spinner} /> Processing...</>
            ) : (
              <><Send size={16} /> Send</>
            )}
          </button>

          {/* Status message */}
          <AnimatePresence>
            {statusMessage && (
              <motion.div
                className={`${styles.statusMsg} ${uploadStatus === 'success' ? styles.statusSuccess : styles.statusError}`}
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
              >
                {uploadStatus === 'success' ? <CheckCircle size={14} /> : <AlertCircle size={14} />}
                {statusMessage}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    );
  }

  // ── Results view (analysis / simulation toggle) ─────────────────────
  return (
    <div className={styles.panel}>
      <div className={styles.panelHeader}>
        <button className={styles.backBtn} onClick={() => setPanelMode('upload')}>
          <ArrowLeft size={16} />
        </button>
        <h2 className={styles.panelTitle}>Results</h2>
      </div>

      {/* Mode toggle */}
      <div className={styles.tabBar}>
        {modeTabs.map(mt => (
          <button
            key={mt.key}
            className={`${styles.tab} ${panelMode === mt.key ? styles.tabActive : ''}`}
            onClick={() => {
              // Clear simulation overlay when leaving simulation tab
              if (mt.key !== 'simulation') setSimulationResults([]);
              // Clear news when leaving news tab
              if (mt.key !== 'news') setNewsArticles([]);
              setPanelMode(mt.key);
            }}
          >
            {mt.icon}
            {mt.label}
          </button>
        ))}
      </div>

      <div className={styles.tabContent}>
        <AnimatePresence mode="wait">
          {/* ── Analysis tab ──────────────────────────────── */}
          {panelMode === 'analysis' && (
            <motion.div
              key="analysis"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.2 }}
              className={styles.tabPanel}
            >
              {/* Phase indicators */}
              {analysisLoading && (
                <div className={styles.loadingRow}>
                  <Loader2 size={16} className={styles.spinner} />
                  <span>
                    {analysisPhase === 'research'
                      ? 'Researching suppliers…'
                      : analysisPhase === 'risk'
                        ? 'Scoring risks & alternatives…'
                        : 'Running analysis…'}
                  </span>
                </div>
              )}

              {/* Tariff impact banner */}
              {analysisResult?.tariff_data && (
                <div className={styles.tariffBanner}>
                  <div
                    className={styles.tariffBannerHeader}
                    onClick={() => setTariffOpen(o => !o)}
                  >
                    <div className={styles.tariffBannerLeft}>
                      <Percent size={18} />
                      <span className={styles.tariffPct}>
                        {analysisResult.tariff_data.net_tariff_pct.toFixed(1)}%
                      </span>
                      <span className={styles.tariffLabel}>Est. Tariff Impact</span>
                    </div>
                    {tariffOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                  </div>

                  <AnimatePresence>
                    {tariffOpen && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.2 }}
                        className={styles.tariffBreakdown}
                      >
                        <p className={styles.tariffSummary}>{analysisResult.tariff_data.summary}</p>
                        <div className={styles.tariffList}>
                          {[...analysisResult.tariff_data.nodes]
                            .sort((a, b) => b.applied_rate - a.applied_rate)
                            .map((node, i) => (
                              <div key={i} className={styles.tariffRow}>
                                <div className={styles.tariffRowMain}>
                                  <span className={styles.tariffNodeName}>{node.name}</span>
                                  <span className={styles.tariffRate}>
                                    {(node.applied_rate * 100).toFixed(1)}%
                                  </span>
                                </div>
                                <div className={styles.tariffRowMeta}>
                                  {node.country} · {node.material || 'N/A'}
                                  {node.hs_code && <> · HS {node.hs_code}</>}
                                  {node.rate_type && <> · <em>{node.rate_type}</em></>}
                                </div>
                                {node.notes && (
                                  <div className={styles.tariffRowNotes}>{node.notes}</div>
                                )}
                              </div>
                            ))}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              )}

              {/* Research results (shown as soon as phase 1 completes) */}
              {supplierResearch.length > 0 && (
                <div className={styles.resultCard}>
                  <div className={styles.resultCardTitle}>
                    <Search size={14} /> Supplier Research ({supplierResearch.length})
                  </div>
                  {supplierResearch.map((res, i) => (
                    <div key={i} className={styles.riskItem} onClick={() => focusNode(res.node_id)} style={{ cursor: 'pointer' }}>
                      <span className={`${styles.severityBadge} ${styles.severity_low}`}>
                        {res.sub_components.length} sub
                      </span>
                      <div className={styles.riskDesc}>
                        <strong>{res.supplier}</strong>
                        {res.findings && <> — {res.findings}</>}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Risks (shown as soon as phase 2 completes) */}
              {streamedRisks.length > 0 && (
                <div className={styles.resultCard}>
                  <div className={styles.resultCardTitle}>
                    <AlertTriangle size={14} /> Risks ({streamedRisks.length})
                  </div>
                  {streamedRisks.map((risk, i) => (
                    <div key={i} className={styles.riskItem} onClick={() => focusNode(risk.node_id)} style={{ cursor: 'pointer' }}>
                      <span className={`${styles.severityBadge} ${styles[`severity_${risk.severity}`]}`}>
                        {risk.severity}
                      </span>
                      <span className={styles.riskDesc}>{risk.description}</span>
                    </div>
                  ))}
                </div>
              )}

              {/* Alternatives (shown as soon as phase 2 completes) */}
              {streamedAlternatives.length > 0 && (
                <div className={styles.resultCard}>
                  <div className={styles.resultCardTitle}>
                    <Lightbulb size={14} /> Alternatives ({streamedAlternatives.length})
                  </div>
                  {streamedAlternatives.map((alt, i) => (
                    <div key={i} className={styles.altItem} onClick={() => setFocusLocation({ lat: alt.lat, lng: alt.lng })} style={{ cursor: 'pointer' }}>
                      <strong>{alt.suggested_supplier}</strong> in {alt.suggested_country}
                      <p className={styles.altReason}>{alt.reason}</p>
                    </div>
                  ))}
                </div>
              )}

              {/* Summary (shown when done) */}
              {analysisResult && (
                <div className={styles.resultCard}>
                  <div className={styles.resultCardTitle}>Summary</div>
                  <p className={styles.resultText}>{analysisResult.summary}</p>
                </div>
              )}

              {/* Empty state */}
              {!analysisLoading && !analysisResult && supplierResearch.length === 0 && (
                <div className={styles.emptyState}>
                  <BarChart3 size={32} />
                  <p>No analysis results yet.</p>
                </div>
              )}

              <button
                className={`${styles.analysisBtn} ${(!currentJobId || analysisLoading) ? styles.analysisBtnDisabled : ''}`}
                onClick={handleRunAnalysis}
                disabled={!currentJobId || analysisLoading}
              >
                {analysisLoading ? (
                  <><Loader2 size={14} className={styles.spinner} /> Analysing…</>
                ) : (
                  <><Play size={14} /> {analysisResult ? 'Re-run Analysis' : 'Run Analysis'}</>
                )}
              </button>

              {analysisResult && (
                <button className={styles.exportBtn} onClick={handleExportJSON}>
                  <Download size={14} /> Export Report
                </button>
              )}
            </motion.div>
          )}

          {/* ── Simulation tab ────────────────────────────── */}
          {panelMode === 'simulation' && (
            <motion.div
              key="simulation"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.2 }}
              className={styles.tabPanel}
            >
              <div className={styles.sectionLabel}>
                <FlaskConical size={14} /> What-If Scenario
              </div>
              <textarea
                className={styles.textArea}
                value={scenarioText}
                onChange={e => setScenarioText(e.target.value)}
                rows={3}
                placeholder={"Describe a scenario to simulate..."}
              />

              {/* Example scenario chips */}
              <div className={styles.scenarioChips}>
                {[
                  '25% tariff on Chinese imports',
                  'EU embargo on Russian energy',
                  'Earthquake disrupts Japanese manufacturing',
                  'New US-Mexico trade agreement',
                ].map(ex => (
                  <button
                    key={ex}
                    className={styles.scenarioChip}
                    onClick={() => setScenarioText(ex)}
                  >
                    {ex}
                  </button>
                ))}
              </div>

              <button
                className={styles.submitBtn}
                onClick={handleRunSimulation}
                disabled={simulationLoading || !scenarioText.trim() || !currentJobId}
              >
                {simulationLoading ? (
                  <><Loader2 size={16} className={styles.spinner} /> Analysing scenario...</>
                ) : (
                  <><Zap size={16} /> Simulate</>
                )}
              </button>

              {!currentJobId && (
                <div className={styles.simHint}>
                  Upload and analyse your supply chain first to enable simulation.
                </div>
              )}

              {simulationResults.map((sr, i) => (
                <div key={i} className={styles.simResultBlock}>
                  {/* Total impact banner */}
                  <div className={`${styles.totalImpactBanner} ${
                    sr.total_cost_impact_pct > 0 ? styles.impactNegative : styles.impactPositive
                  }`}>
                    <div className={styles.totalImpactIcon}>
                      {sr.total_cost_impact_pct > 0
                        ? <TrendingUp size={20} />
                        : <TrendingDown size={20} />
                      }
                    </div>
                    <div className={styles.totalImpactText}>
                      <span className={styles.totalImpactNumber}>
                        {sr.total_cost_impact_pct > 0 ? '+' : ''}{sr.total_cost_impact_pct.toFixed(1)}%
                      </span>
                      <span className={styles.totalImpactLabel}>Estimated Cost Impact</span>
                    </div>
                  </div>

                  {/* Summary */}
                  <div className={styles.resultCard}>
                    <div className={styles.resultCardTitle}>
                      <DollarSign size={14} /> Summary
                    </div>
                    <p className={styles.resultText}>{sr.summary}</p>
                  </div>

                  {/* Node impacts */}
                  {sr.impacts.length > 0 && (
                    <div className={styles.resultCard}>
                      <div className={styles.resultCardTitle}>
                        <AlertTriangle size={14} /> Affected Nodes ({sr.impacts.length})
                      </div>
                      {sr.impacts.map((imp, j) => (
                        <div
                          key={j}
                          className={styles.riskItem}
                          onClick={() => focusNode(imp.node_id)}
                          style={{ cursor: 'pointer' }}
                        >
                          <span className={`${styles.severityBadge} ${
                            styles[`severity_${imp.severity}`] || styles.severity_medium
                          }`}>
                            {imp.cost_change_pct > 0 ? '+' : ''}{imp.cost_change_pct.toFixed(1)}%
                          </span>
                          <span className={styles.riskDesc}>{imp.impact_description}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Recommendations */}
                  {sr.recommendations && sr.recommendations.length > 0 && (
                    <div className={styles.resultCard}>
                      <div className={styles.resultCardTitle}>
                        <Lightbulb size={14} /> Recommendations ({sr.recommendations.length})
                      </div>
                      {sr.recommendations.map((rec, j) => (
                        <div key={j} className={styles.recItem}>
                          <div className={styles.recHeader}>
                            <span className={`${styles.recTypeBadge} ${
                              rec.type === 'opportunity' ? styles.recOpportunity : styles.recMitigate
                            }`}>
                              {rec.type === 'opportunity'
                                ? <><TrendingUp size={10} /> Opportunity</>
                                : <><ShieldAlert size={10} /> Mitigate</>
                              }
                            </span>
                            <span className={`${styles.recPriority} ${
                              styles[`priority_${rec.priority}`]
                            }`}>
                              {rec.priority}
                            </span>
                          </div>
                          <div className={styles.recTitle}>{rec.title}</div>
                          <div className={styles.recDesc}>{rec.description}</div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}

              {/* Empty state */}
              {!simulationLoading && simulationResults.length === 0 && currentJobId && (
                <div className={styles.emptyState}>
                  <FlaskConical size={32} />
                  <p>Enter a scenario above to see how it would affect your supply chain.</p>
                </div>
              )}
            </motion.div>
          )}

          {/* ── News tab ──────────────────────────────────── */}
          {panelMode === 'news' && (
            <motion.div
              key="news"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.2 }}
              className={styles.tabPanel}
            >
              <div className={styles.sectionLabel}>
                <Newspaper size={14} /> Geopolitical &amp; Tariff News
              </div>
              <p className={styles.newsHint}>
                Scan for recent news about geopolitical disturbances, tariff changes,
                and trade policy shifts affecting your supply chain locations.
              </p>

              <button
                className={`${styles.analysisBtn} ${(!currentJobId || newsLoading) ? styles.analysisBtnDisabled : ''}`}
                onClick={handleScanNews}
                disabled={!currentJobId || newsLoading}
              >
                {newsLoading ? (
                  <><Loader2 size={14} className={styles.spinner} /> Scanning for news…</>
                ) : (
                  <><Search size={14} /> {newsArticles.length > 0 ? 'Re-scan News' : 'Scan for News'}</>
                )}
              </button>

              {newsArticles.length > 0 && (
                <div className={styles.resultCard}>
                  <div className={styles.resultCardTitle}>
                    <Newspaper size={14} /> Articles Found ({newsArticles.length})
                  </div>
                  {newsArticles.map((article: NewsArticle, i: number) => (
                    <div key={i} className={styles.newsItem}>
                      <div className={styles.newsTitle}>
                        {article.url ? (
                          <a href={article.url} target="_blank" rel="noopener noreferrer">{article.title}</a>
                        ) : (
                          article.title
                        )}
                      </div>
                      <p className={styles.newsSummary}>{article.summary}</p>
                      {article.affected_locations.length > 0 && (
                        <div className={styles.newsLocations}>
                          <MapPin size={10} />
                          {article.affected_locations.join(', ')}
                        </div>
                      )}
                      {article.relevance && (
                        <p className={styles.newsRelevance}>{article.relevance}</p>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {!newsLoading && newsArticles.length === 0 && currentJobId && (
                <div className={styles.emptyState}>
                  <Newspaper size={32} />
                  <p>Press the button above to scan for news affecting your supply chain.</p>
                </div>
              )}

              {!currentJobId && (
                <div className={styles.simHint}>
                  Upload your supply chain first to enable news scanning.
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
