// src/components/layout/SearchBar.tsx
import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import RobotIcon from './RobotIcon';

import { FASTAPI_BASE_URL as API_BASE } from '../../config/api';

export type SearchResultItem = {
  id: string;
  title: string;
  category?: string;
  collection?: string;
  file_type: string;
  tags?: string;
  description?: string;
  similarity: number;
  ocr_excerpt?: string;
  icr_excerpt?: string;
  ocr_status?: string;
  icr_status?: string;
  view_url: string;
  download_url?: string;
};

function HighlightedText({ text, query }: { text?: string | null; query: string }) {
  if (!text) return null;
  if (!query.trim()) return <>{text}</>;

  const keywords = query
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .map((k) => k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));

  if (keywords.length === 0) return <>{text}</>;

  const regex = new RegExp(`(${keywords.join('|')})`, 'gi');
  const parts = text.split(regex);

  return (
    <>
      {parts.map((part, i) => {
        const isMatch = keywords.some(
          (k) => part.toLowerCase() === k.toLowerCase()
        );
        return isMatch ? (
          <mark
            key={i}
            className="bg-[#C88B47]/60 text-[#FFE5B4] px-0.5 rounded font-semibold no-underline"
          >
            {part}
          </mark>
        ) : (
          <span key={i}>{part}</span>
        );
      })}
    </>
  );
}

const SAMPLE_SUGGESTIONS = ['1962 War', 'Gallantry Awards', 'Battalion History', 'Raising Day', 'WWII'];

export default function SearchBar() {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResultItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedDoc, setSelectedDoc] = useState<SearchResultItem | null>(null);

  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Close chat window on click outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Auto focus input when chat window opens
  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 150);
    }
  }, [isOpen]);

  // Debounced search fetch
  useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      return;
    }

    const timer = setTimeout(async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(`${API_BASE}/search?q=${encodeURIComponent(query.trim())}`);
        if (!res.ok) throw new Error(`Search failed (${res.status})`);
        const data = await res.json();
        setResults(data.results || []);
      } catch (err: any) {
        setError(err.message || 'Search error');
      } finally {
        setLoading(false);
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [query]);

  const getBaseApiUrl = () => {
    if (typeof window !== 'undefined' && API_BASE.includes('127.0.0.1') && window.location.hostname === 'localhost') {
      return API_BASE.replace('127.0.0.1', 'localhost');
    }
    return API_BASE;
  };

  const getViewUrl = (item: SearchResultItem) => {
    const url = item.view_url || `/search/documents/${item.id}/view`;
    const base = getBaseApiUrl();
    return url.startsWith('http') ? url : `${base}${url}`;
  };

  const getDownloadUrl = (item: SearchResultItem) => {
    const url = item.download_url || `/search/documents/${item.id}/download`;
    const base = getBaseApiUrl();
    return url.startsWith('http') ? url : `${base}${url}`;
  };

  const isImage = (fileType: string) => {
    const clean = (fileType || '').toLowerCase().replace(/^\./, '');
    return ['png', 'jpg', 'jpeg', 'webp', 'gif', 'tiff', 'tif'].includes(clean);
  };

  const isPdf = (fileType: string) => {
    const clean = (fileType || '').toLowerCase().replace(/^\./, '');
    return clean === 'pdf';
  };

  const isVideo = (fileType: string) => {
    const clean = (fileType || '').toLowerCase().replace(/^\./, '');
    return ['mp4', 'webm', 'mov', 'avi', 'mkv', 'ogv'].includes(clean);
  };

  return (
    <>
      <div ref={containerRef} className="relative">
        {/* Floating Toggle Button (Bottom-Right Viewport Corner) */}
        <motion.button
          type="button"
          onClick={() => setIsOpen(!isOpen)}
          whileHover={{ scale: 1.08 }}
          whileTap={{ scale: 0.94 }}
          className="fixed bottom-6 right-6 z-50 flex items-center justify-center rounded-full cursor-pointer shadow-2xl transition-colors outline-none focus:outline-none"
          style={{
            width: '64px',
            height: '64px',
            background: 'radial-gradient(circle at 35% 35%, #18251e, #050806)',
            border: '1.5px solid #85683c',
            boxShadow: '0 8px 32px rgba(0, 0, 0, 0.85), inset 0 0 12px rgba(133, 104, 60, 0.4), 0 0 20px rgba(225, 188, 120, 0.3)',
          }}
          aria-label={isOpen ? 'Close Search Assistant' : 'Open Search Assistant'}
        >
          {isOpen ? (
            <svg className="w-7 h-7 text-[#E1BC78]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          ) : (
            <div className="relative flex items-center justify-center">
              {/* Robot Mascot Icon */}
              <RobotIcon size={44} />
              <span className="absolute -top-1 -right-1 w-3 h-3 bg-[#C88B47] rounded-full animate-ping opacity-75" />
              <span className="absolute -top-1 -right-1 w-3 h-3 bg-[#E1BC78] rounded-full border border-black" />
            </div>
          )}
        </motion.button>

        {/* Floating Chat Panel (Bottom-Right Viewport Corner) */}
        <AnimatePresence>
          {isOpen && (
            <motion.div
              initial={{ opacity: 0, scale: 0.88, y: 24, transformOrigin: 'bottom right' }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.88, y: 24 }}
              transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
              className="fixed bottom-24 right-4 sm:right-6 z-50 w-[92vw] sm:w-[410px] h-[540px] max-h-[80vh] flex flex-col rounded-2xl overflow-hidden shadow-2xl"
              style={{
                background: '#0a0f0c',
                border: '1.5px solid #85683c',
                boxShadow: '0 20px 60px rgba(0, 0, 0, 0.95), 0 0 24px rgba(133, 104, 60, 0.2)',
              }}
            >
              {/* Chat Header */}
              <div
                className="flex items-center justify-between px-4 py-3 bg-[#050806] border-b border-[#85683c]/40 flex-shrink-0"
                style={{ boxShadow: 'inset 0 -10px 20px rgba(0,0,0,0.4)' }}
              >
                <div className="flex items-center gap-3">
                  <div
                    className="w-8 h-8 rounded-full flex items-center justify-center border border-[#85683c]"
                    style={{ background: 'radial-gradient(circle, #18221b, #050806)' }}
                  >
                    <RobotIcon size={18} />
                  </div>
                  <div>
                    <h3 className="font-cinzel text-xs font-bold text-[#E1BC78] tracking-wider leading-none">
                      SEARCH ARCHIVE
                    </h3>
                    <p className="text-[10px] text-[#85683c] font-cinzel mt-1 flex items-center gap-1.5 leading-none">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                      Assam Regiment Digital Assistant
                    </p>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => setIsOpen(false)}
                  className="text-gray-400 hover:text-[#E1BC78] transition-colors p-1 rounded focus:outline-none cursor-pointer"
                  aria-label="Minimize Chat"
                >
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                  </svg>
                </button>
              </div>

              {/* Chat Scrollable Message / Results Area */}
              <div
                ref={scrollRef}
                className="flex-1 overflow-y-auto p-4 space-y-4 text-xs"
                style={{
                  scrollbarWidth: 'thin',
                  scrollbarColor: '#85683c #050806',
                }}
              >
                {/* Intro welcome message bubble */}
                <div className="flex gap-2.5 items-start">
                  <div className="w-6 h-6 rounded-full bg-[#85683c]/30 border border-[#85683c] flex items-center justify-center text-[10px] text-[#E1BC78] flex-shrink-0 mt-0.5">
                    🪖
                  </div>
                  <div className="bg-[#050806] border border-[#85683c]/40 text-gray-200 rounded-2xl rounded-tl-xs p-3 max-w-[88%] shadow-md">
                    <p className="leading-relaxed font-sans">
                      Greetings! Ask me or type a query below to search through historical documents, War Diaries, and military records.
                    </p>

                    {/* Quick suggestion chips */}
                    {!query.trim() && (
                      <div className="mt-3 pt-2 border-t border-[#85683c]/20">
                        <span className="text-[10px] text-[#85683c] font-cinzel block mb-1.5 font-semibold">
                          Quick Suggestions:
                        </span>
                        <div className="flex flex-wrap gap-1.5">
                          {SAMPLE_SUGGESTIONS.map((tag) => (
                            <button
                              key={tag}
                              type="button"
                              onClick={() => setQuery(tag)}
                              className="text-[10px] bg-[#85683c]/20 hover:bg-[#85683c]/40 text-[#E1BC78] border border-[#85683c]/40 px-2 py-0.5 rounded-full transition-colors font-cinzel cursor-pointer"
                            >
                              {tag}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                {/* User Prompt Message Bubble (if query typed) */}
                {query.trim().length > 0 && (
                  <div className="flex justify-end">
                    <div className="bg-[#85683c]/30 border border-[#85683c] text-[#F4E8D3] rounded-2xl rounded-tr-xs px-3.5 py-2 max-w-[85%] font-cinzel text-xs shadow-md">
                      <span className="text-[9px] text-[#85683c] block font-sans uppercase tracking-wider mb-0.5">
                        Searching:
                      </span>
                      "{query}"
                    </div>
                  </div>
                )}

                {/* Loading State */}
                {loading && (
                  <div className="flex gap-2.5 items-start">
                    <div className="w-6 h-6 rounded-full bg-[#85683c]/30 border border-[#85683c] flex items-center justify-center text-[10px] text-[#E1BC78] flex-shrink-0">
                      ⚡
                    </div>
                    <div className="bg-[#050806] border border-[#85683c]/40 text-[#E1BC78] rounded-2xl rounded-tl-xs px-4 py-3 font-cinzel text-xs flex items-center gap-2">
                      <span className="inline-block w-2 h-2 rounded-full bg-[#E1BC78] animate-ping" />
                      Searching archive records...
                    </div>
                  </div>
                )}

                {/* Error State */}
                {error && (
                  <div className="flex gap-2.5 items-start">
                    <div className="w-6 h-6 rounded-full bg-red-950 border border-red-700 flex items-center justify-center text-[10px] text-red-400 flex-shrink-0">
                      ⚠️
                    </div>
                    <div className="bg-red-950/40 border border-red-800/60 text-red-300 rounded-2xl rounded-tl-xs p-3">
                      {error}
                    </div>
                  </div>
                )}

                {/* Empty State */}
                {!loading && !error && query.trim().length > 0 && results.length === 0 && (
                  <div className="flex gap-2.5 items-start">
                    <div className="w-6 h-6 rounded-full bg-[#85683c]/30 border border-[#85683c] flex items-center justify-center text-[10px] text-[#E1BC78] flex-shrink-0">
                      🔍
                    </div>
                    <div className="bg-[#050806] border border-[#85683c]/40 text-[#85683c] font-cinzel rounded-2xl rounded-tl-xs p-3">
                      No matching archive items found for "{query}". Try checking spelling or using alternate terms.
                    </div>
                  </div>
                )}

                {/* Results List as Chat Card Bubbles */}
                {!loading && results.length > 0 && (
                  <div className="space-y-3">
                    <div className="text-[10px] text-[#85683c] font-cinzel tracking-wider uppercase text-center py-1 border-b border-[#85683c]/20">
                      Found {results.length} matching document{results.length > 1 ? 's' : ''}
                    </div>

                    {results.map((item) => {
                      const isOcrPending = item.ocr_status === 'pending';
                      const excerptText = item.ocr_excerpt || item.icr_excerpt;
                      const excerptType = item.ocr_excerpt ? 'OCR' : item.icr_excerpt ? 'ICR (Handwritten)' : null;

                      return (
                        <div key={item.id} className="flex gap-2 items-start">
                          <div
                            className="bg-[#050806] hover:bg-[#070c09] border border-[#85683c]/40 hover:border-[#E1BC78] text-left rounded-xl p-3 w-full transition-all duration-200 shadow-md group cursor-pointer"
                            onClick={() => setSelectedDoc(item)}
                          >
                            {/* Card Top Header */}
                            <div className="flex items-start justify-between gap-2 mb-1">
                              <div className="flex items-center gap-1.5 flex-wrap">
                                <span className="font-cinzel text-xs font-bold text-[#E1BC78] group-hover:text-[#F4E8D3] transition-colors leading-tight">
                                  <HighlightedText text={item.title} query={query} />
                                </span>
                                {isVideo(item.file_type) && (
                                  <span className="text-[9px] text-[#E1BC78] px-1.5 py-0.5 rounded bg-[#85683c]/30 border border-[#85683c]/60 font-semibold font-cinzel tracking-wider flex-shrink-0">
                                    🎬 VIDEO
                                  </span>
                                )}
                                {isPdf(item.file_type) && (
                                  <span className="text-[9px] text-gray-400 px-1.5 py-0.5 rounded bg-black/50 border border-gray-700 font-mono flex-shrink-0">
                                    PDF
                                  </span>
                                )}
                              </div>
                              <span className="text-[10px] text-[#C88B47] px-1.5 py-0.5 rounded bg-black/60 border border-[#85683c]/40 font-mono whitespace-nowrap flex-shrink-0">
                                {(item.similarity * 100).toFixed(1)}% match
                              </span>
                            </div>

                            {/* OCR Pending Notice Flag */}
                            {isOcrPending && (
                              <div className="my-1.5 flex items-center gap-1.5 text-[9.5px] text-amber-300 bg-amber-950/60 border border-amber-600/50 px-2 py-0.5 rounded">
                                <span className="flex-shrink-0">⚠️</span>
                                <span>OCR Pending — Match derived from ICR text</span>
                              </div>
                            )}

                            {/* Tags */}
                            {item.tags && (
                              <div className="text-[10px] text-[#85683c] mt-1 truncate">
                                🏷️ <HighlightedText text={item.tags} query={query} />
                              </div>
                            )}

                            {/* Description */}
                            {item.description && (
                              <div className="text-[10px] text-gray-300 mt-1 line-clamp-2 italic bg-black/30 p-1.5 rounded border border-[#85683c]/20">
                                "<HighlightedText text={item.description} query={query} />"
                              </div>
                            )}

                            {/* Excerpt */}
                            {excerptText && (
                              <div className="text-[10px] text-gray-300 mt-1.5 line-clamp-2 bg-black/40 p-1.5 rounded border border-[#85683c]/20">
                                📄 <span className="text-[#E1BC78]/80 font-mono text-[9px] font-semibold">[{excerptType}]: </span>
                                <HighlightedText text={excerptText} query={query} />
                              </div>
                            )}

                            {/* Action footer link */}
                            <div className="mt-2 pt-1 border-t border-[#85683c]/20 flex items-center justify-end text-[10px] text-[#E1BC78] group-hover:text-[#F4E8D3] font-cinzel font-semibold">
                              <span>Inspect Document ↗</span>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* Chat Input Box */}
              <div className="p-3 bg-[#050806] border-t border-[#85683c]/40 flex items-center gap-2 flex-shrink-0">
                <div className="relative flex-1 flex items-center">
                  <input
                    ref={inputRef}
                    type="text"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Type query to search archive..."
                    className="w-full bg-[#0a0f0c] text-[#F4E8D3] border border-[#85683c]/60 focus:border-[#E1BC78] rounded-xl px-3 py-2 text-xs font-cinzel placeholder-[#85683c] outline-none shadow-inner transition-colors pr-7"
                  />
                  {query && (
                    <button
                      type="button"
                      onClick={() => setQuery('')}
                      className="absolute right-2 text-[#85683c] hover:text-[#E1BC78] text-xs focus:outline-none cursor-pointer"
                      aria-label="Clear query"
                    >
                      ✕
                    </button>
                  )}
                </div>

                <div className="w-8 h-8 rounded-xl bg-[#85683c]/20 border border-[#85683c]/50 flex items-center justify-center text-[#E1BC78] flex-shrink-0">
                  <svg className="w-4 h-4 fill-current" viewBox="0 0 24 24">
                    <path d="M15.5 14h-.79l-.28-.27C15.41 12.59 16 11.11 16 9.5 16 5.91 13.09 3 9.5 3S3 5.91 3 9.5 5.91 16 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z" />
                  </svg>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Document Viewer Modal (Unchanged functionality) */}
      <AnimatePresence>
        {selectedDoc && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm"
            onClick={() => setSelectedDoc(null)}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              onClick={(e) => e.stopPropagation()}
              className="relative w-full max-w-4xl max-h-[90vh] overflow-y-auto rounded-xl p-6 shadow-2xl"
              style={{
                background: '#0a0f0c',
                border: '1.5px solid #85683c',
                boxShadow: '0 20px 50px rgba(0,0,0,0.9)',
              }}
            >
              {/* Close button */}
              <button
                onClick={() => setSelectedDoc(null)}
                className="absolute top-4 right-4 text-gray-400 hover:text-[#E1BC78] text-xl font-bold p-1 cursor-pointer"
                aria-label="Close modal"
              >
                ✕
              </button>

              {/* Title & Metadata */}
              <div className="pr-8 mb-4">
                <div className="flex items-center gap-2 flex-wrap mb-1">
                  <h2 className="font-cinzel text-lg font-bold text-[#E1BC78]">
                    <HighlightedText text={selectedDoc.title} query={query} />
                  </h2>
                  <span className="text-xs text-[#C88B47] px-2 py-0.5 rounded bg-black/60 border border-[#85683c]">
                    {(selectedDoc.similarity * 100).toFixed(1)}% Match
                  </span>
                  {isVideo(selectedDoc.file_type) ? (
                    <span className="text-xs text-[#E1BC78] px-2 py-0.5 rounded bg-[#85683c]/30 border border-[#85683c]/60 font-semibold font-cinzel tracking-wider uppercase">
                      🎬 VIDEO ({selectedDoc.file_type})
                    </span>
                  ) : (
                    <span className="text-xs text-gray-400 px-2 py-0.5 rounded bg-black/40 border border-gray-700 uppercase">
                      {selectedDoc.file_type}
                    </span>
                  )}
                </div>

                {(selectedDoc.category || selectedDoc.collection) && (
                  <p className="text-xs text-[#85683c] font-cinzel">
                    {selectedDoc.category && `Category: ${selectedDoc.category}`}
                    {selectedDoc.category && selectedDoc.collection && ' | '}
                    {selectedDoc.collection && `Collection: ${selectedDoc.collection}`}
                  </p>
                )}
              </div>

              {/* OCR Pending Notice Flag */}
              {selectedDoc.ocr_status === 'pending' && (
                <div className="mb-4 p-3 rounded-lg bg-amber-950/60 border border-amber-600/50 text-amber-300 text-xs">
                  <div className="font-semibold flex items-center gap-1.5 mb-1 text-amber-400">
                    <span>⚠️</span> OCR Status: Pending
                  </div>
                  <p className="text-amber-200/90 leading-relaxed">
                    Primary OCR processing has not finished for this document. Search matches are currently based on handwritten ICR text extraction, which may produce lower confidence or garbled matches.
                  </p>
                </div>
              )}

              {/* Document Preview Viewer */}
              <div className="mb-4 bg-[#050806] rounded-lg p-2 border border-[#85683c]/30 flex flex-col items-center justify-center">
                {isImage(selectedDoc.file_type) ? (
                  <img
                    src={getViewUrl(selectedDoc)}
                    alt={selectedDoc.title}
                    className="max-h-[55vh] object-contain rounded border border-[#85683c]/40"
                    onLoad={() => console.log('[Image Viewer] Image loaded successfully:', getViewUrl(selectedDoc))}
                    onError={(e) => console.error('[Image Viewer] Failed to load image:', getViewUrl(selectedDoc), e)}
                  />
                ) : isPdf(selectedDoc.file_type) ? (
                  <object
                    data={`${getViewUrl(selectedDoc)}#toolbar=0&navpanes=0`}
                    type="application/pdf"
                    className="w-full h-[55vh] rounded border border-[#85683c]/40 bg-[#050806]"
                    onLoad={() => console.log('[PDF Viewer] Object element loaded:', getViewUrl(selectedDoc))}
                    onError={(e) => console.error('[PDF Viewer] Object element load error:', e)}
                  >
                    <embed
                      src={`${getViewUrl(selectedDoc)}#toolbar=0&navpanes=0`}
                      type="application/pdf"
                      className="w-full h-[55vh] rounded border border-[#85683c]/40"
                      onLoad={() => console.log('[PDF Viewer] Embed element loaded:', getViewUrl(selectedDoc))}
                      onError={(e) => console.error('[PDF Viewer] Embed element load error:', e)}
                    />
                    <iframe
                      src={getViewUrl(selectedDoc)}
                      title={selectedDoc.title}
                      className="w-full h-[55vh] rounded border border-[#85683c]/40 bg-white"
                      onLoad={() => console.log('[PDF Viewer] Iframe element loaded:', getViewUrl(selectedDoc))}
                      onError={(e) => console.error('[PDF Viewer] Iframe element load error:', e)}
                    />
                  </object>
                ) : isVideo(selectedDoc.file_type) ? (
                  <video
                    src={getViewUrl(selectedDoc)}
                    controls
                    className="w-full max-h-[55vh] rounded border border-[#85683c]/40 bg-black"
                    onLoadedData={() => console.log('[Video Viewer] Loaded:', getViewUrl(selectedDoc))}
                    onError={(e) => console.error('[Video Viewer] Failed to load:', getViewUrl(selectedDoc), e)}
                  />
                ) : (
                  <div className="py-12 text-center text-gray-400">
                    <p className="mb-2">Preview not directly inlineable for .{selectedDoc.file_type} files.</p>
                  </div>
                )}

                <div className="mt-3 flex items-center justify-center gap-3 flex-wrap">
                  <a
                    href={getDownloadUrl(selectedDoc)}
                    download
                    className="inline-flex items-center gap-2 px-4 py-2 rounded text-xs font-semibold font-cinzel text-[#F4E8D3] bg-[#C88B47]/30 hover:bg-[#C88B47]/60 border border-[#C88B47] transition-colors"
                  >
                    📥 Download Document
                  </a>
                  <a
                    href={getViewUrl(selectedDoc)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-2 px-4 py-2 rounded text-xs font-semibold font-cinzel text-[#F4E8D3] bg-[#85683c]/40 hover:bg-[#85683c]/70 border border-[#85683c] transition-colors"
                  >
                    Open Document File in New Tab ↗
                  </a>
                </div>
              </div>

              {/* Excerpts & Descriptions */}
              <div className="space-y-3 text-xs border-t border-[#85683c]/30 pt-3">
                {selectedDoc.ocr_excerpt && (
                  <div className="bg-[#050806] p-3 rounded border border-[#85683c]/20">
                    <span className="font-semibold text-[#E1BC78] block mb-1 font-cinzel">
                      📄 OCR Excerpt:
                    </span>
                    <p className="text-gray-300 leading-relaxed">
                      <HighlightedText text={selectedDoc.ocr_excerpt} query={query} />
                    </p>
                  </div>
                )}

                {selectedDoc.icr_excerpt && (
                  <div className="bg-[#050806] p-3 rounded border border-[#85683c]/20">
                    <span className="font-semibold text-[#E1BC78] block mb-1 font-cinzel">
                      ✍️ ICR (Handwritten Text) Excerpt:
                    </span>
                    <p className="text-gray-300 leading-relaxed">
                      <HighlightedText text={selectedDoc.icr_excerpt} query={query} />
                    </p>
                  </div>
                )}

                {selectedDoc.description && (
                  <div>
                    <span className="font-semibold text-[#85683c] block mb-0.5">Description:</span>
                    <p className="text-gray-300 italic">
                      <HighlightedText text={selectedDoc.description} query={query} />
                    </p>
                  </div>
                )}

                {selectedDoc.tags && (
                  <div>
                    <span className="font-semibold text-[#85683c] block mb-0.5">Tags:</span>
                    <p className="text-gray-400">
                      🏷️ <HighlightedText text={selectedDoc.tags} query={query} />
                    </p>
                  </div>
                )}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}

