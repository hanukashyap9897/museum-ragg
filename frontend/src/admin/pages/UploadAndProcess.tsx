// src/admin/pages/UploadAndProcess.tsx
import { useState, useRef, useEffect, useCallback } from 'react';

import { FASTAPI_BASE_URL as API_BASE } from '../../config/api';
const POLL_INTERVAL_MS = 2_000;
const SOFT_TIMEOUT_ATTEMPTS = 600;   // UI hint after ~20 min — user can keep waiting

type IdpBlock = {
  category: string;
  content: string | null;
  bbox?: number[];
  officer_name?: string;
};

type PageResult = {
  page?: number;
  clean_text: string;
  blocks: IdpBlock[];
  metadata?: {
    dates?: string[];
    reference_numbers?: string[];
  };
  error?: string;
};

type ProgressInfo = {
  current_page: number;
  total_pages: number;
  percent: number;
  remaining_pages: number;
};

type PollResult = {
  id?: string;
  status: 'processing' | 'completed' | 'failed';
  progress?: ProgressInfo;
  result?: { 
    pages?: PageResult[];
    clean_text?: string;
  };
  error?: string;
};

const isVideoFile = (f: File | null) => {
  if (!f) return false;
  const ext = (f.name.split('.').pop() || '').toLowerCase();
  return ['mp4', 'webm', 'mov', 'avi', 'mkv'].includes(ext) || f.type.startsWith('video/');
};

export default function UploadAndProcess() {
  /* ── state ────────────────────────────────────────── */
  const [file, setFile] = useState<File | null>(null);
  const [metaTitle, setMetaTitle] = useState('');
  const [metaTags, setMetaTags] = useState('');
  const [metaDescription, setMetaDescription] = useState('');
  const [documentId, setDocumentId] = useState<string | null>(null);

  const [processingMode, setProcessingMode] = useState<'icr' | 'combined' | 'idp'>('icr');
  const [status, setStatus] = useState<'idle' | 'uploading' | 'processing' | 'completed' | 'failed' | 'timeout'>('idle');
  const [uploadPercent, setUploadPercent] = useState<number>(0);
  const [pages, setPages] = useState<PageResult[]>([]);
  const [fullResult, setFullResult] = useState<any>(null);
  const [activeTab, setActiveTab] = useState<'pages' | 'text' | 'json'>('pages');
  const [copiedType, setCopiedType] = useState<string | null>(null);
  const [progress, setProgress] = useState<ProgressInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollAttemptsRef = useRef(0);
  const [dragActive, setDragActive] = useState(false);

  const isVideo = isVideoFile(file);

  /* ── cleanup on unmount ───────────────────────────── */
  useEffect(() => {
    return () => {
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    };
  }, []);

  /* ── polling logic ────────────────────────────────── */
  const applyPollResult = useCallback((data: PollResult) => {
    if (data.progress) {
      setProgress(data.progress);
    }
    if (data.status === 'completed') {
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
      setPages(data.result?.pages ?? []);
      setFullResult(data);
      setStatus('completed');
      return true;
    }
    if (data.status === 'failed') {
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
      setError(data.error ?? 'Processing failed on the server.');
      setStatus('failed');
      return true;
    }
    return false;
  }, []);

  const checkResultNow = useCallback(async (docId: string, mode: 'icr' | 'combined' | 'idp') => {
    const endpoint = mode === 'icr'
      ? `${API_BASE}/icr/result/${docId}`
      : mode === 'combined'
      ? `${API_BASE}/ocr/result/${docId}`
      : `${API_BASE}/idp/result/${docId}`;
    const res = await fetch(endpoint);
    if (!res.ok) throw new Error(`Server responded ${res.status}`);
    const data: PollResult = await res.json();
    return applyPollResult(data);
  }, [applyPollResult]);

  const startPolling = useCallback((docId: string, mode: 'icr' | 'combined' | 'idp') => {
    pollAttemptsRef.current = 0;

    if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    setStatus('processing');

    pollTimerRef.current = setInterval(async () => {
      pollAttemptsRef.current += 1;

      if (pollAttemptsRef.current === SOFT_TIMEOUT_ATTEMPTS) {
        setStatus('timeout');
      }

      try {
        const done = await checkResultNow(docId, mode);
        if (done && pollTimerRef.current) {
          clearInterval(pollTimerRef.current);
          pollTimerRef.current = null;
        }
      } catch (err: any) {
        if (pollTimerRef.current) clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
        setError(err.message ?? 'Polling request failed.');
        setStatus('failed');
      }
    }, POLL_INTERVAL_MS);
  }, [checkResultNow]);

  const handleKeepWaiting = () => {
    setStatus('processing');
  };

  const handleCheckNow = async () => {
    if (!documentId) return;
    try {
      await checkResultNow(documentId, processingMode);
    } catch (err: any) {
      setError(err.message ?? 'Could not reach the server.');
      setStatus('failed');
    }
  };

  /* ── upload + kick-off ────────────────────────────── */
  const handleUpload = async () => {
    if (!file) return;

    // reset
    setError(null);
    setPages([]);
    setFullResult(null);
    setProgress(null);
    setDocumentId(null);
    setUploadPercent(0);
    setStatus('uploading');

    const isVid = isVideoFile(file);

    try {
      /* 1 — upload file with real-time progress */
      const form = new FormData();
      form.append('file', file);
      if (metaTitle.trim()) form.append('title', metaTitle.trim());
      if (metaTags.trim()) form.append('tags', metaTags.trim());
      if (metaDescription.trim()) form.append('description', metaDescription.trim());

      const json = await new Promise<any>((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open('POST', `${API_BASE}/upload/document`);
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) {
            const pct = Math.round((e.loaded / e.total) * 100);
            setUploadPercent(pct);
          }
        };
        xhr.onload = () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            try {
              resolve(JSON.parse(xhr.responseText));
            } catch {
              reject(new Error('Invalid response from server'));
            }
          } else {
            try {
              const resJson = JSON.parse(xhr.responseText);
              reject(new Error(resJson.detail || `Upload failed (${xhr.status})`));
            } catch {
              reject(new Error(`Upload failed (${xhr.status})`));
            }
          }
        };
        xhr.onerror = () => reject(new Error('Network connection error during upload'));
        xhr.send(form);
      });

      const document_id = json.id;
      setDocumentId(document_id);

      if (isVid) {
        setStatus('completed');
        setFullResult({
          id: document_id,
          status: 'completed',
          result: {
            clean_text: metaDescription || `${metaTitle || file.name} (Video Content Indexed)`
          }
        });
        return;
      }

      /* 2 — start selected pipeline mode for documents */
      const startUrl = processingMode === 'icr'
        ? `${API_BASE}/icr/start/${document_id}`
        : processingMode === 'combined'
        ? `${API_BASE}/ocr/start-combined/${document_id}`
        : `${API_BASE}/idp/start/${document_id}`;

      const procRes = await fetch(startUrl, { method: 'POST' });
      if (!procRes.ok) throw new Error(`Processing start failed (${procRes.status})`);

      /* 3 — poll */
      setStatus('processing');
      startPolling(document_id, processingMode);
    } catch (err: any) {
      setError(err.message ?? 'An unexpected error occurred.');
      setStatus('failed');
    }
  };

  /* ── reset ────────────────────────────────────────── */
  const handleReset = () => {
    if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    pollTimerRef.current = null;
    pollAttemptsRef.current = 0;
    setFile(null);
    setMetaTitle('');
    setMetaTags('');
    setMetaDescription('');
    setDocumentId(null);

    setStatus('idle');
    setPages([]);
    setFullResult(null);
    setProgress(null);
    setError(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  /* ── clipboard & download ────────────────────────── */
  const getFullCleanText = () => {
    if (fullResult?.result?.clean_text) return fullResult.result.clean_text;
    return pages.map(p => p.clean_text).filter(Boolean).join('\n\n--- Page Break ---\n\n');
  };

  const handleCopyText = () => {
    const text = getFullCleanText();
    if (!text) return;
    navigator.clipboard.writeText(text);
    setCopiedType('text');
    setTimeout(() => setCopiedType(null), 2000);
  };

  const handleCopyJson = () => {
    if (!fullResult) return;
    navigator.clipboard.writeText(JSON.stringify(fullResult, null, 2));
    setCopiedType('json');
    setTimeout(() => setCopiedType(null), 2000);
  };

  const handleDownloadJson = () => {
    if (!fullResult) return;
    const blob = new Blob([JSON.stringify(fullResult, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `result_${documentId || 'output'}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  /* ── drag & drop ──────────────────────────────────── */
  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') setDragActive(true);
    else if (e.type === 'dragleave') setDragActive(false);
  };
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files?.[0]) setFile(e.dataTransfer.files[0]);
  };

  /* ── render helpers ───────────────────────────────── */
  const isWorking = status === 'uploading' || status === 'processing' || status === 'timeout';
  const fullText = getFullCleanText();

  return (
    <div>
      <div className="admin-page-title">Upload &amp; Process</div>
      <div className="admin-page-subtitle">
        Upload documents, photos, or videos for archive search indexing
      </div>

      {/* ── Upload card ────────────────────────────── */}
      <div className="admin-card" style={{ marginBottom: '1.5rem' }}>
        <div className="admin-card-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <div style={{
              width: 44, height: 44, borderRadius: 12,
              background: 'linear-gradient(135deg, #d4a017, #8c5500)',
              display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1.25rem',
            }}>{isVideo ? '🎬' : '📄'}</div>
            <div>
              <div style={{ fontWeight: 600, fontSize: '0.9rem', color: '#e4dcc8' }}>
                Document / Image / Video Upload
              </div>
              <div style={{ fontSize: '0.7rem', color: '#7a6e58' }}>
                Supported formats: PDF, PNG, JPG, JPEG, TIFF, MP4, WEBM, MOV, AVI, MKV
              </div>
            </div>
          </div>
        </div>

        <div className="admin-divider" />

        {/* Processing Mode Selection Cards vs Video Notice */}
        {isVideo ? (
          <div style={{
            padding: '0.9rem 1.1rem',
            borderRadius: 10,
            border: '1px solid rgba(212,160,23,0.35)',
            background: 'rgba(212,160,23,0.08)',
            marginBottom: '1.25rem',
            fontSize: '0.82rem',
            color: '#e4dcc8',
            display: 'flex',
            alignItems: 'center',
            gap: '0.75rem'
          }}>
            <span style={{ fontSize: '1.4rem' }}>🎬</span>
            <div>
              <div style={{ fontWeight: 600, color: '#d4a017', fontSize: '0.85rem', marginBottom: '0.15rem' }}>
                Video File Selected
              </div>
              <div style={{ fontSize: '0.75rem', color: '#c0ad90', lineHeight: 1.4 }}>
                Videos are indexed by title, tags, and description only — OCR/ICR model pipeline is skipped.
              </div>
            </div>
          </div>
        ) : (
          <div style={{ marginBottom: '1.25rem' }}>
            <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#d4a017', marginBottom: '0.5rem' }}>
              Select Processing Model Engine:
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: '0.75rem' }}>
              {/* ICR Mode */}
              <div
                onClick={() => setProcessingMode('icr')}
                style={{
                  padding: '0.85rem',
                  borderRadius: 10,
                  border: processingMode === 'icr' ? '2px solid #d4a017' : '1px solid rgba(212,160,23,0.2)',
                  background: processingMode === 'icr' ? 'rgba(212,160,23,0.12)' : 'rgba(10,12,8,0.5)',
                  cursor: 'pointer',
                  transition: 'all 0.2s ease',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 600, color: '#e4dcc8', fontSize: '0.85rem' }}>
                  <span>✍️</span> Handwritten (TrOCR)
                </div>
                <div style={{ fontSize: '0.72rem', color: '#7a6e58', marginTop: '0.25rem' }}>
                  Enabled for cursive, notes, &amp; handwritten letters (Microsoft TrOCR model)
                </div>
              </div>

              {/* Combined Mode */}
              <div
                onClick={() => setProcessingMode('combined')}
                style={{
                  padding: '0.85rem',
                  borderRadius: 10,
                  border: processingMode === 'combined' ? '2px solid #d4a017' : '1px solid rgba(212,160,23,0.2)',
                  background: processingMode === 'combined' ? 'rgba(212,160,23,0.12)' : 'rgba(10,12,8,0.5)',
                  cursor: 'pointer',
                  transition: 'all 0.2s ease',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 600, color: '#e4dcc8', fontSize: '0.85rem' }}>
                  <span>🔀</span> Combined OCR + ICR
                </div>
                <div style={{ fontSize: '0.72rem', color: '#7a6e58', marginTop: '0.25rem' }}>
                  For documents with mixed printed header/footer + handwritten letter body
                </div>
              </div>

              {/* IDP Mode */}
              <div
                onClick={() => setProcessingMode('idp')}
                style={{
                  padding: '0.85rem',
                  borderRadius: 10,
                  border: processingMode === 'idp' ? '2px solid #d4a017' : '1px solid rgba(212,160,23,0.2)',
                  background: processingMode === 'idp' ? 'rgba(212,160,23,0.12)' : 'rgba(10,12,8,0.5)',
                  cursor: 'pointer',
                  transition: 'all 0.2s ease',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 600, color: '#e4dcc8', fontSize: '0.85rem' }}>
                  <span>📊</span> IDP (PaddleOCR)
                </div>
                <div style={{ fontSize: '0.72rem', color: '#7a6e58', marginTop: '0.25rem' }}>
                  For printed documents, military diaries, and reconstructed HTML tables
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Metadata fields (Title, Tags, Description) */}
        <div style={{ marginBottom: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
          <div>
            <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, color: '#d4a017', marginBottom: '0.35rem' }}>
              Title (optional — defaults to filename)
            </label>
            <input
              type="text"
              value={metaTitle}
              onChange={(e) => setMetaTitle(e.target.value)}
              placeholder="e.g. Regimental Parade, 1965"
              style={{
                width: '100%',
                padding: '0.6rem 0.85rem',
                borderRadius: '8px',
                border: '1px solid rgba(212, 160, 23, 0.3)',
                background: 'rgba(10, 12, 8, 0.6)',
                color: '#e4dcc8',
                fontSize: '0.85rem',
                outline: 'none',
              }}
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, color: '#d4a017', marginBottom: '0.35rem' }}>
              Tags (comma-separated)
            </label>
            <input
              type="text"
              value={metaTags}
              onChange={(e) => setMetaTags(e.target.value)}
              placeholder="e.g. parade, ceremony, 1965, Nagaland"
              style={{
                width: '100%',
                padding: '0.6rem 0.85rem',
                borderRadius: '8px',
                border: '1px solid rgba(212, 160, 23, 0.3)',
                background: 'rgba(10, 12, 8, 0.6)',
                color: '#e4dcc8',
                fontSize: '0.85rem',
                outline: 'none',
              }}
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, color: '#d4a017', marginBottom: '0.35rem' }}>
              Description
            </label>
            <textarea
              rows={2}
              value={metaDescription}
              onChange={(e) => setMetaDescription(e.target.value)}
              placeholder="Describe the content — especially important for photos/videos that can't be OCR'd"
              style={{
                width: '100%',
                padding: '0.6rem 0.85rem',
                borderRadius: '8px',
                border: '1px solid rgba(212, 160, 23, 0.3)',
                background: 'rgba(10, 12, 8, 0.6)',
                color: '#e4dcc8',
                fontSize: '0.85rem',
                outline: 'none',
                resize: 'vertical',
              }}
            />
          </div>
        </div>

        {/* Drop zone */}
        <div
          className="admin-image-upload"
          style={{
            borderColor: dragActive ? 'rgba(212,160,23,0.6)' : undefined,
            background: dragActive ? 'rgba(20,26,13,0.7)' : undefined,
            marginBottom: '1rem',
          }}
          onDragEnter={handleDrag}
          onDragOver={handleDrag}
          onDragLeave={handleDrag}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.png,.jpg,.jpeg,.tiff,.tif,.mp4,.webm,.mov,.avi,.mkv"
            style={{ display: 'none' }}
            onChange={e => { if (e.target.files?.[0]) setFile(e.target.files[0]); }}
          />
          <div style={{ fontSize: '2.25rem', marginBottom: '0.5rem' }}>
            {file ? (isVideo ? '🎬' : '📎') : '📤'}
          </div>
          <div style={{ color: '#c0ad90', fontSize: '0.85rem', fontWeight: 500 }}>
            {file ? file.name : 'Click or drag a PDF, Image, or Video file (PNG, JPG, MP4, MOV, etc.) here'}
          </div>
          {file && (
            <div style={{ fontSize: '0.7rem', color: '#7a6e58', marginTop: '0.25rem' }}>
              {(file.size / (1024 * 1024)).toFixed(2)} MB
            </div>
          )}
        </div>

        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button
            className="admin-btn admin-btn-primary"
            disabled={!file || isWorking}
            onClick={handleUpload}
            style={{ opacity: (!file || isWorking) ? 0.5 : 1, cursor: (!file || isWorking) ? 'not-allowed' : 'pointer' }}
          >
            {isWorking
              ? (status === 'uploading' ? `⏳ Uploading... (${uploadPercent}%)` : '⏳ Processing…')
              : (isVideo ? '🚀 Upload Video' : `🚀 Process with ${processingMode === 'icr' ? 'Handwritten ICR' : processingMode === 'combined' ? 'Combined Engine' : 'IDP Pipeline'}`)}
          </button>
          {(file || status !== 'idle') && (
            <button className="admin-btn admin-btn-ghost" onClick={handleReset}>
              ↩ Reset
            </button>
          )}
        </div>
      </div>

      {/* ── Status feedback ────────────────────────── */}
      {status === 'uploading' && (
        <div className="admin-card" style={{ marginBottom: '1.5rem', borderColor: 'rgba(212,160,23,0.35)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <div className="idp-spinner" />
            <div style={{ flex: 1 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.4rem' }}>
                <div style={{ color: '#d4a017', fontWeight: 600, fontSize: '0.88rem' }}>
                  Transmitting file over network... ({uploadPercent}%)
                </div>
                <div style={{ color: '#c0ad90', fontSize: '0.8rem', fontWeight: 600 }}>
                  {uploadPercent}%
                </div>
              </div>
              <div style={{ width: '100%', height: 6, background: 'rgba(212,160,23,0.15)', borderRadius: 3, overflow: 'hidden' }}>
                <div style={{ width: `${uploadPercent}%`, height: '100%', background: '#d4a017', transition: 'width 0.2s ease' }} />
              </div>
            </div>
          </div>
        </div>
      )}
      {(status === 'processing' || status === 'timeout') && (
        <div className="admin-card" style={{ marginBottom: '1.5rem', borderColor: status === 'timeout' ? 'rgba(212,160,23,0.35)' : undefined }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <div className="idp-spinner" />
            <div style={{ flex: 1 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ color: '#d4a017', fontWeight: 600, fontSize: '0.88rem' }}>
                  {progress
                    ? `Processing Page ${progress.current_page} of ${progress.total_pages}`
                    : (status === 'timeout' ? 'Still processing on the server…' : 'Analyzing document structure…')}
                </div>
                {progress && (
                  <div style={{ color: '#d4a017', fontWeight: 700, fontSize: '0.88rem' }}>
                    {progress.percent}%
                  </div>
                )}
              </div>

              {/* Progress Bar */}
              {progress ? (
                <div style={{ marginTop: '0.5rem' }}>
                  <div style={{
                    height: 8,
                    width: '100%',
                    background: 'rgba(10,12,8,0.8)',
                    borderRadius: 4,
                    overflow: 'hidden',
                    border: '1px solid rgba(212,160,23,0.2)',
                  }}>
                    <div style={{
                      height: '100%',
                      width: `${progress.percent}%`,
                      background: 'linear-gradient(90deg, #c8820a, #d4a017, #f0ca50)',
                      borderRadius: 4,
                      transition: 'width 0.4s ease',
                    }} />
                  </div>
                  <div style={{ color: '#7a6e58', fontSize: '0.75rem', marginTop: '0.35rem', display: 'flex', justifyContent: 'space-between' }}>
                    <span>{progress.remaining_pages} page{progress.remaining_pages !== 1 ? 's' : ''} remaining</span>
                    <span>Document ID: <code style={{ color: '#c0ad90' }}>{documentId}</code></span>
                  </div>
                </div>
              ) : (
                <div style={{ color: '#7a6e58', fontSize: '0.75rem', marginTop: '0.2rem' }}>
                  Preparing document… Document ID: <code style={{ color: '#c0ad90' }}>{documentId}</code>
                </div>
              )}

              {status === 'timeout' && (
                <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.75rem' }}>
                  <button className="admin-btn admin-btn-primary admin-btn-sm" onClick={handleKeepWaiting}>
                    Keep waiting
                  </button>
                  <button className="admin-btn admin-btn-ghost admin-btn-sm" onClick={handleCheckNow}>
                    Check result now
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {status === 'failed' && (
        <div className="admin-card" style={{ marginBottom: '1.5rem', borderColor: 'rgba(180,40,40,0.35)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', color: '#e85555' }}>
            <span style={{ fontSize: '1.5rem' }}>❌</span>
            <div>
              <div style={{ fontWeight: 600, fontSize: '0.88rem' }}>Processing Failed</div>
              <div style={{ color: '#7a6e58', fontSize: '0.75rem', marginTop: '0.15rem' }}>{error}</div>
            </div>
          </div>
        </div>
      )}

      {/* ── Extracted Results Output Section ────────── */}
      {status === 'completed' && (
        <div>
          {/* Output Header Bar */}
          <div className="admin-card" style={{ marginBottom: '1rem', padding: '1rem 1.25rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.75rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <span className="admin-badge admin-badge-green">✓ Processing Completed</span>
                <span style={{ fontSize: '0.78rem', color: '#7a6e58' }}>
                  {pages.length} page{pages.length !== 1 ? 's' : ''} · {fullText.length} characters extracted
                </span>
              </div>

              {/* View Switcher Tabs */}
              <div style={{ display: 'flex', gap: '0.35rem', background: 'rgba(10,12,8,0.6)', padding: '0.25rem', borderRadius: 8, border: '1px solid rgba(212,160,23,0.15)' }}>
                <button
                  onClick={() => setActiveTab('pages')}
                  style={{
                    padding: '0.35rem 0.75rem',
                    borderRadius: 6,
                    fontSize: '0.78rem',
                    fontWeight: 600,
                    border: 'none',
                    cursor: 'pointer',
                    background: activeTab === 'pages' ? '#d4a017' : 'transparent',
                    color: activeTab === 'pages' ? '#0a0c08' : '#c0ad90',
                    transition: 'all 0.2s ease',
                  }}
                >
                  📄 Pages &amp; Blocks ({pages.length})
                </button>
                <button
                  onClick={() => setActiveTab('text')}
                  style={{
                    padding: '0.35rem 0.75rem',
                    borderRadius: 6,
                    fontSize: '0.78rem',
                    fontWeight: 600,
                    border: 'none',
                    cursor: 'pointer',
                    background: activeTab === 'text' ? '#d4a017' : 'transparent',
                    color: activeTab === 'text' ? '#0a0c08' : '#c0ad90',
                    transition: 'all 0.2s ease',
                  }}
                >
                  📝 Clean Text
                </button>
                <button
                  onClick={() => setActiveTab('json')}
                  style={{
                    padding: '0.35rem 0.75rem',
                    borderRadius: 6,
                    fontSize: '0.78rem',
                    fontWeight: 600,
                    border: 'none',
                    cursor: 'pointer',
                    background: activeTab === 'json' ? '#d4a017' : 'transparent',
                    color: activeTab === 'json' ? '#0a0c08' : '#c0ad90',
                    transition: 'all 0.2s ease',
                  }}
                >
                  💻 Raw JSON
                </button>
              </div>
            </div>
          </div>

          {/* TAB 1: Pages & Blocks View */}
          {activeTab === 'pages' && (
            <div>
              {pages.length === 0 ? (
                <div className="admin-card" style={{ marginBottom: '1.5rem' }}>
                  <div style={{ color: '#7a6e58', fontSize: '0.82rem' }}>
                    Processing completed but no page layout blocks were extracted. Switch to the <strong>Clean Text</strong> or <strong>Raw JSON</strong> tab to view extracted contents.
                  </div>
                </div>
              ) : (
                pages.map((page, i) => (
                  <div key={i} className="admin-card" style={{ marginBottom: '1rem' }}>
                    <div className="admin-card-header">
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                        <span style={{
                          width: 32, height: 32, borderRadius: 8,
                          background: 'rgba(212,160,23,0.12)',
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          fontFamily: "'Cinzel', serif", fontWeight: 700, fontSize: '0.85rem',
                          color: '#d4a017',
                        }}>{i + 1}</span>
                        <span style={{ fontFamily: "'Cinzel', serif", fontWeight: 600, fontSize: '0.9rem', color: '#e4dcc8' }}>
                          Page {i + 1}
                        </span>
                      </div>
                    </div>

                    <div className="admin-divider" />

                    {/* Clean text */}
                    <div className="admin-form-group">
                      <label className="admin-label">Clean Text</label>
                      <div style={{
                        background: 'rgba(20,26,13,0.8)',
                        border: '1px solid rgba(212,160,23,0.12)',
                        borderRadius: 8,
                        padding: '0.85rem',
                        fontSize: '0.82rem',
                        lineHeight: 1.7,
                        color: '#e4dcc8',
                        whiteSpace: 'pre-wrap',
                        maxHeight: 280,
                        overflowY: 'auto',
                      }}>
                        {page.clean_text || '—'}
                      </div>
                    </div>

                    {page.error && (
                      <div className="admin-form-group">
                        <label className="admin-label">Page Error</label>
                        <div style={{ color: '#e85555', fontSize: '0.78rem' }}>{page.error}</div>
                      </div>
                    )}

                    {/* Blocks */}
                    {page.blocks && page.blocks.length > 0 && (
                      <div className="admin-form-group">
                        <label className="admin-label">Extracted Blocks ({page.blocks.length})</label>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                          {page.blocks.map((block, bi) => (
                            <div key={bi} style={{
                              background: 'rgba(20,26,13,0.5)',
                              border: '1px solid rgba(212,160,23,0.08)',
                              borderRadius: 6,
                              padding: '0.6rem 0.85rem',
                              fontSize: '0.78rem',
                              color: '#c0ad90',
                            }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.35rem' }}>
                                <span className="admin-badge admin-badge-gold">{block.category}</span>
                                {block.officer_name && (
                                  <span style={{ color: '#7a6e58', fontSize: '0.72rem' }}>{block.officer_name}</span>
                                )}
                              </div>
                              {block.category === 'table' && block.content ? (
                                <div
                                  className="idp-table-wrapper"
                                  style={{ overflowX: 'auto', lineHeight: 1.5 }}
                                  dangerouslySetInnerHTML={{ __html: block.content }}
                                />
                              ) : (
                                <div style={{ whiteSpace: 'pre-wrap' }}>{block.content ?? '—'}</div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Metadata */}
                    {page.metadata && (
                      <div style={{ display: 'flex', gap: '1.5rem', flexWrap: 'wrap' }}>
                        {page.metadata.dates && page.metadata.dates.length > 0 && (
                          <div className="admin-form-group" style={{ flex: 1, minWidth: 200 }}>
                            <label className="admin-label">📅 Dates</label>
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem' }}>
                              {page.metadata.dates.map((d, di) => (
                                <span key={di} className="admin-badge admin-badge-gold">{d}</span>
                              ))}
                            </div>
                          </div>
                        )}
                        {page.metadata.reference_numbers && page.metadata.reference_numbers.length > 0 && (
                          <div className="admin-form-group" style={{ flex: 1, minWidth: 200 }}>
                            <label className="admin-label">🔢 Reference Numbers</label>
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem' }}>
                              {page.metadata.reference_numbers.map((r, ri) => (
                                <span key={ri} className="admin-badge admin-badge-gold">{r}</span>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
          )}

          {/* TAB 2: Clean Text View */}
          {activeTab === 'text' && (
            <div className="admin-card">
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
                <label className="admin-label" style={{ margin: 0 }}>Complete Document Text</label>
                <button
                  className="admin-btn admin-btn-ghost admin-btn-sm"
                  onClick={handleCopyText}
                >
                  {copiedType === 'text' ? '✓ Copied!' : '📋 Copy All Text'}
                </button>
              </div>
              <div style={{
                background: 'rgba(10,12,8,0.85)',
                border: '1px solid rgba(212,160,23,0.15)',
                borderRadius: 8,
                padding: '1rem',
                fontSize: '0.85rem',
                lineHeight: 1.7,
                color: '#e4dcc8',
                whiteSpace: 'pre-wrap',
                maxHeight: 500,
                overflowY: 'auto',
                fontFamily: 'monospace',
              }}>
                {fullText || 'No text extracted.'}
              </div>
            </div>
          )}

          {/* TAB 3: Raw JSON Output View */}
          {activeTab === 'json' && (
            <div className="admin-card">
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
                <div>
                  <label className="admin-label" style={{ margin: 0 }}>Raw JSON API Output</label>
                  <div style={{ fontSize: '0.7rem', color: '#7a6e58' }}>Full output returned from /idp/result/{documentId}</div>
                </div>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <button
                    className="admin-btn admin-btn-ghost admin-btn-sm"
                    onClick={handleCopyJson}
                  >
                    {copiedType === 'json' ? '✓ Copied JSON!' : '📋 Copy JSON'}
                  </button>
                  <button
                    className="admin-btn admin-btn-primary admin-btn-sm"
                    onClick={handleDownloadJson}
                  >
                    ⬇️ Download JSON
                  </button>
                </div>
              </div>

              <pre style={{
                background: '#070905',
                border: '1px solid rgba(212,160,23,0.2)',
                borderRadius: 8,
                padding: '1.25rem',
                fontSize: '0.8rem',
                lineHeight: 1.5,
                color: '#84ad54',
                maxHeight: 550,
                overflow: 'auto',
                fontFamily: "'Fira Code', 'Courier New', Courier, monospace",
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
              }}>
                {fullResult ? JSON.stringify(fullResult, null, 2) : 'No JSON data available.'}
              </pre>
            </div>
          )}
        </div>
      )}

      {/* ── Spinner keyframes (scoped) ─────────────── */}
      <style>{`
        .idp-spinner {
          width: 32px; height: 32px;
          border: 3px solid rgba(212,160,23,0.15);
          border-top-color: #d4a017;
          border-radius: 50%;
          animation: idpSpin 0.8s linear infinite;
          flex-shrink: 0;
        }
        @keyframes idpSpin {
          to { transform: rotate(360deg); }
        }
        .idp-table-wrapper table {
          width: 100%;
          border-collapse: collapse;
          margin-top: 0.5rem;
          background: rgba(10,12,8,0.7);
          border: 1px solid rgba(212,160,23,0.25);
        }
        .idp-table-wrapper th, .idp-table-wrapper td {
          border: 1px solid rgba(212,160,23,0.2);
          padding: 0.4rem 0.6rem;
          text-align: left;
          font-size: 0.78rem;
          color: #e4dcc8;
        }
        .idp-table-wrapper th {
          background: rgba(212,160,23,0.12);
          color: #d4a017;
          font-weight: 600;
        }
      `}</style>
    </div>
  );
}
