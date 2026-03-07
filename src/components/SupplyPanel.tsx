import { useState, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Upload, FileText, Image, Type, MapPin, Package, CheckCircle, AlertCircle, Loader2 } from 'lucide-react';
import { useAppContext } from '../context/AppContext';
import { uploadSupplyChainText, uploadSupplyChainImage } from '../api/supplyChain';
import type { SupplyPoint } from '../types';
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
    const lat = parseFloat(get('lat') || get('latitude'));
    const lng = parseFloat(get('lng') || get('longitude') || get('lon'));
    if (isNaN(lat) || isNaN(lng)) continue;
    points.push({
      id: crypto.randomUUID(),
      name: get('name') || `Point ${i}`,
      lat, lng,
      material: get('material') || '',
      supplier: get('supplier') || '',
      country: get('country') || '',
    });
  }
  return points;
}

type UploadTab = 'csv' | 'text' | 'image';
type UploadStatus = 'idle' | 'uploading' | 'success' | 'error';

const SAMPLE_CSV = `name,lat,lng,material,supplier,country
Shenzhen Electronics,22.5431,114.0579,Semiconductors,Foxconn,China
São Paulo Steel,-23.5505,-46.6333,Steel Alloys,Gerdau SA,Brazil
Stuttgart Precision,48.7758,9.1829,Precision Parts,Bosch GmbH,Germany
Mumbai Textiles,19.076,72.8777,Raw Cotton,Reliance Textiles,India
Melbourne Mining,-37.8136,144.9631,Lithium,BHP Group,Australia`;

export default function SupplyPanel() {
  const { headquartersLocation, setHeadquartersLocation, setSupplyPoints } = useAppContext();
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

  // Image state
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState('');
  const imageInputRef = useRef<HTMLInputElement>(null);

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

  const handleImageFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImageFile(file);
    const reader = new FileReader();
    reader.onload = (evt) => {
      setImagePreview(evt.target?.result as string);
    };
    reader.readAsDataURL(file);
    e.target.value = '';
  };

  const handleSubmit = () => {
    setUploadStatus('uploading');
    setStatusMessage('');

    // For CSV, parse and display on globe immediately
    if (activeTab === 'csv') {
      if (!csvContent.trim()) {
        setUploadStatus('error');
        setStatusMessage('Please provide CSV content to upload.');
        return;
      }
      const parsed = parseCSV(csvContent);
      if (parsed.length > 0) {
        setSupplyPoints(parsed);
      }
    }

    // Fire API in background
    try {
      if (activeTab === 'image') {
        if (!imageFile) {
          setUploadStatus('error');
          setStatusMessage('Please select an image first.');
          return;
        }
        uploadSupplyChainImage(imageFile).catch(() => {});
        setUploadStatus('success');
        setStatusMessage('Image uploaded. Processing will begin shortly.');
        setImageFile(null);
        setImagePreview('');
      } else {
        const content = activeTab === 'csv' ? csvContent : textContent;
        if (!content.trim()) {
          setUploadStatus('error');
          setStatusMessage('Please provide content to upload.');
          return;
        }
        uploadSupplyChainText({
          format: activeTab,
          content,
          fileName: activeTab === 'csv' ? csvFileName : undefined,
        }).catch(() => {});
        setUploadStatus('success');
        setStatusMessage(
          activeTab === 'csv'
            ? `Mapped ${parseCSV(csvContent).length} suppliers on the globe.`
            : 'Text uploaded. Processing will begin shortly.'
        );
        if (activeTab === 'csv') { setCsvContent(''); setCsvFileName(''); }
        else { setTextContent(''); }
      }
    } catch (err) {
      setUploadStatus('error');
      setStatusMessage(err instanceof Error ? err.message : 'Upload failed.');
    }
  };

  const tabs: { key: UploadTab; label: string; icon: React.ReactNode }[] = [
    { key: 'csv', label: 'CSV', icon: <FileText size={14} /> },
    { key: 'text', label: 'Text', icon: <Type size={14} /> },
    { key: 'image', label: 'Image', icon: <Image size={14} /> },
  ];

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
                    <span className={styles.dropZoneHint}>name, lat, lng, material, supplier, country</span>
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

          {activeTab === 'image' && (
            <motion.div
              key="image"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.2 }}
              className={styles.tabPanel}
            >
              <label
                className={styles.dropZone}
                onClick={() => imageInputRef.current?.click()}
              >
                {imagePreview ? (
                  <img src={imagePreview} alt="Preview" className={styles.imagePreview} />
                ) : (
                  <>
                    <Image size={28} />
                    <span>Click to upload an image</span>
                    <span className={styles.dropZoneHint}>Invoices, documents, supply maps, etc.</span>
                  </>
                )}
                <input
                  ref={imageInputRef}
                  type="file"
                  accept="image/*"
                  onChange={handleImageFile}
                  hidden
                />
              </label>
              {imageFile && (
                <div className={styles.fileInfo}>
                  <span>{imageFile.name}</span>
                  <span className={styles.fileSize}>{(imageFile.size / 1024).toFixed(1)} KB</span>
                </div>
              )}
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
            <><Upload size={16} /> Upload & Process</>
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
