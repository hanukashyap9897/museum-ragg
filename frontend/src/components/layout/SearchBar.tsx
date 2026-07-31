// src/components/layout/SearchBar.tsx
import { useState, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { motion, AnimatePresence } from 'framer-motion';
import RobotIcon from './RobotIcon';
import { FASTAPI_BASE_URL } from '../../config/api';

interface Source {
  id: string;
  title: string;
  similarity: number;
  view_url: string;
  file_type?: string; // e.g. "mp4", "mp3", "pdf", "png" …
}

interface Message {
  role: 'user' | 'assistant';
  content: string;
  sources?: Source[];
}

interface ConversationThread {
  id: string;
  title: string;
  preview: string;
  messages: Message[];
}

const SUGGESTIONS = [
  { icon: '📜', label: 'Battle of Kohima', prompt: 'Tell me about the Battle of Kohima' },
  { icon: '🏅', label: 'Gallantry Awards', prompt: 'Gallantry Awards & Ashoka Chakra' },
  { icon: '📁', label: 'Posting Orders', prompt: 'Find officer posting orders' },
  { icon: '📖', label: '1962 War History', prompt: '1962 War & Battalion History' },
];

const NAV_ITEMS = [
  {
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
        <path strokeLinecap="round" strokeLinejoin="round" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
      </svg>
    ),
    label: 'Chat',
    id: 'chat',
  },
  {
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
    label: 'History',
    id: 'history',
  },
];

export default function SearchBar() {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [activeNav, setActiveNav] = useState('chat');
  const [threads, setThreads] = useState<ConversationThread[]>([]);
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 150);
    }
  }, [isOpen]);

  // Auto-resize textarea
  useEffect(() => {
    const ta = inputRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 120) + 'px';
  }, [input]);

  async function sendMessage(text: string) {
    const question = text.trim();
    if (!question || loading) return;

    const userMsg: Message = { role: 'user', content: question };
    const newMessages = [...messages, userMsg];
    setMessages(newMessages);
    setInput('');
    setLoading(true);

    try {
      const res = await fetch(`${FASTAPI_BASE_URL}/chat/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: question, top_k: 5 }),
      });
      if (!res.ok) throw new Error(`Server returned ${res.status}`);
      const data = await res.json();
      const assistantMsg: Message = { role: 'assistant', content: data.answer, sources: data.sources };
      const finalMessages = [...newMessages, assistantMsg];
      setMessages(finalMessages);

      // Save thread
      const threadTitle = question.length > 40 ? question.slice(0, 40) + '…' : question;
      const preview = data.answer.length > 60 ? data.answer.slice(0, 60) + '…' : data.answer;
      if (activeThreadId) {
        setThreads(prev => prev.map(t => t.id === activeThreadId ? { ...t, messages: finalMessages, preview } : t));
      } else {
        const newId = Date.now().toString();
        setActiveThreadId(newId);
        setThreads(prev => [{ id: newId, title: threadTitle, preview, messages: finalMessages }, ...prev]);
      }
    } catch {
      setMessages(prev => [
        ...prev,
        {
          role: 'assistant',
          content: "I couldn't reach the archive right now. Please check your connection and try again.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function startNewChat() {
    setMessages([]);
    setInput('');
    setActiveThreadId(null);
    setActiveNav('chat');
    setTimeout(() => inputRef.current?.focus(), 150);
  }

  function loadThread(thread: ConversationThread) {
    setMessages(thread.messages);
    setActiveThreadId(thread.id);
    setActiveNav('chat');
  }

  const getFullViewUrl = (viewUrl: string) => {
    if (viewUrl.startsWith('http')) return viewUrl;
    return `${FASTAPI_BASE_URL}${viewUrl}`;
  };

  const hasStarted = messages.length > 0;
  const charCount = input.length;
  const maxChars = 3000;

  const isAudio = (fileType: string) => {
    const clean = (fileType || '').toLowerCase().replace(/^\./, '');
    return ['mp3', 'wav', 'aac', 'flac', 'ogg', 'm4a', 'wma', 'opus'].includes(clean);
  };

  return (
    <>
      {/* Floating Trigger Button */}
      <motion.button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        whileHover={{ scale: 1.08 }}
        whileTap={{ scale: 0.94 }}
        className="fixed bottom-6 right-6 z-[990] flex items-center justify-center rounded-full cursor-pointer outline-none focus:outline-none"
        style={{
          width: '64px',
          height: '64px',
          background: 'radial-gradient(circle at 35% 35%, #18251e, #050806)',
          border: '1.5px solid #85683c',
          boxShadow: '0 8px 32px rgba(0,0,0,0.85), inset 0 0 12px rgba(133,104,60,0.4), 0 0 20px rgba(225,188,120,0.3)',
        }}
        aria-label={isOpen ? 'Close Search Assistant' : 'Open Search Assistant'}
      >
        {isOpen ? (
          <svg className="w-7 h-7 text-[#E1BC78]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        ) : (
          <div className="relative flex items-center justify-center">
            <RobotIcon size={44} />
            <span className="absolute -top-1 -right-1 w-3 h-3 bg-[#C88B47] rounded-full animate-ping opacity-75" />
            <span className="absolute -top-1 -right-1 w-3 h-3 bg-[#E1BC78] rounded-full border border-black" />
          </div>
        )}
      </motion.button>

      {/* Full-Screen Chat Overlay */}
      {createPortal(
        <AnimatePresence>
          {isOpen && (
            <motion.div
              initial={{ opacity: 0, scale: 0.97 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.97 }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
              style={{
                position: 'fixed',
                inset: 0,
                zIndex: 1000,
                display: 'flex',
                fontFamily: "'Inter', 'Segoe UI', system-ui, sans-serif",
                background: '#0f0f0d',
                color: '#ece7d8',
              }}
            >
              {/* ── LEFT SIDEBAR ── */}
              <div
                style={{
                  width: '220px',
                  flexShrink: 0,
                  background: '#0d0d0a',
                  borderRight: '1px solid #1e1e14',
                  display: 'flex',
                  flexDirection: 'column',
                  padding: '20px 0',
                }}
              >
                {/* Logo */}
                <div style={{ padding: '0 20px 20px', borderBottom: '1px solid #1e1e14' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <div
                      style={{
                        width: '32px', height: '32px', borderRadius: '8px',
                        background: 'linear-gradient(135deg, #1e2a1a, #0d1a0e)',
                        border: '1px solid #85683c',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        flexShrink: 0,
                      }}
                    >
                      <RobotIcon size={18} />
                    </div>
                    <div>
                      <div style={{ fontSize: '13px', fontWeight: 700, color: '#E1BC78', letterSpacing: '0.04em', lineHeight: 1.2 }}>
                        Archive
                      </div>
                      <div style={{ fontSize: '10px', color: '#6b6452', letterSpacing: '0.06em' }}>
                        Assistant
                      </div>
                    </div>
                  </div>
                </div>

                {/* New Chat Button */}
                <div style={{ padding: '16px 12px 8px' }}>
                  <button
                    type="button"
                    onClick={startNewChat}
                    style={{
                      width: '100%', display: 'flex', alignItems: 'center', gap: '8px',
                      padding: '9px 12px', borderRadius: '8px',
                      background: '#1a1a12', border: '1px solid #2a2a1e',
                      color: '#ece7d8', fontSize: '13px', cursor: 'pointer',
                      transition: 'all 0.15s ease',
                    }}
                    onMouseEnter={e => {
                      (e.currentTarget as HTMLButtonElement).style.borderColor = '#d4a94a';
                      (e.currentTarget as HTMLButtonElement).style.color = '#d4a94a';
                    }}
                    onMouseLeave={e => {
                      (e.currentTarget as HTMLButtonElement).style.borderColor = '#2a2a1e';
                      (e.currentTarget as HTMLButtonElement).style.color = '#ece7d8';
                    }}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
                    </svg>
                    New Chat
                  </button>
                </div>

                {/* Nav Items */}
                <nav style={{ padding: '4px 12px', flex: 1 }}>
                  {NAV_ITEMS.map(item => (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => setActiveNav(item.id)}
                      style={{
                        width: '100%', display: 'flex', alignItems: 'center', gap: '10px',
                        padding: '10px 12px', borderRadius: '8px', border: 'none',
                        background: activeNav === item.id ? '#1e1e14' : 'transparent',
                        color: activeNav === item.id ? '#E1BC78' : '#6b6452',
                        fontSize: '13px', fontWeight: activeNav === item.id ? 600 : 400,
                        cursor: 'pointer', marginBottom: '2px',
                        transition: 'all 0.15s ease', textAlign: 'left',
                      }}
                    >
                      <span style={{ opacity: activeNav === item.id ? 1 : 0.7 }}>{item.icon}</span>
                      {item.label}
                    </button>
                  ))}
                </nav>

                {/* Bottom: Close */}
                <div style={{ padding: '12px 12px 0', borderTop: '1px solid #1e1e14' }}>
                  <button
                    type="button"
                    onClick={() => setIsOpen(false)}
                    style={{
                      width: '100%', display: 'flex', alignItems: 'center', gap: '10px',
                      padding: '10px 12px', borderRadius: '8px', border: 'none',
                      background: 'transparent', color: '#6b6452',
                      fontSize: '13px', cursor: 'pointer', transition: 'all 0.15s ease',
                      textAlign: 'left',
                    }}
                    onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.color = '#ece7d8'; }}
                    onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.color = '#6b6452'; }}
                  >
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                    Close
                  </button>
                </div>
              </div>

              {/* ── MAIN CHAT AREA ── */}
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>

                {/* Top Bar */}
                <div
                  style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    padding: '14px 24px', borderBottom: '1px solid #1e1e14',
                    background: '#0f0f0d', flexShrink: 0,
                  }}
                >
                  <h2
                    style={{
                      fontFamily: "'Cinzel', 'Georgia', serif",
                      fontSize: '15px', fontWeight: 700,
                      color: '#E1BC78', letterSpacing: '0.12em', margin: 0,
                    }}
                  >
                    {activeNav === 'history' ? 'CONVERSATION HISTORY' : 'ARCHIVE ASSISTANT'}
                  </h2>
                  <span
                    style={{
                      fontSize: '10px', letterSpacing: '0.1em', color: '#6b6452',
                      border: '1px solid #1e1e14', borderRadius: '999px', padding: '3px 10px',
                      fontFamily: 'monospace',
                    }}
                  >
                    ASSAM REGIMENT DIGITAL MUSEUM
                  </span>
                </div>

                {/* Body — history view or chat view */}
                {activeNav === 'history' ? (
                  <div style={{ flex: 1, overflowY: 'auto', padding: '24px' }}>
                    {threads.length === 0 ? (
                      <div style={{ textAlign: 'center', color: '#6b6452', marginTop: '60px', fontSize: '14px' }}>
                        No conversations yet. Start a new chat!
                      </div>
                    ) : (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxWidth: '680px', margin: '0 auto' }}>
                        {threads.map(thread => (
                          <button
                            key={thread.id}
                            type="button"
                            onClick={() => loadThread(thread)}
                            style={{
                              display: 'flex', flexDirection: 'column', alignItems: 'flex-start',
                              padding: '14px 18px', borderRadius: '10px',
                              background: '#16160f', border: '1px solid #2a2a1e',
                              color: '#ece7d8', cursor: 'pointer', textAlign: 'left',
                              transition: 'all 0.15s ease',
                            }}
                            onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.borderColor = '#d4a94a'; }}
                            onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.borderColor = '#2a2a1e'; }}
                          >
                            <span style={{ fontSize: '13px', fontWeight: 600, marginBottom: '4px', color: '#ece7d8' }}>
                              {thread.title}
                            </span>
                            <span style={{ fontSize: '12px', color: '#6b6452', lineHeight: 1.4 }}>
                              {thread.preview}
                            </span>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                ) : (
                  <>
                    {/* Scrollable messages or hero */}
                    <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column' }}>
                      {!hasStarted ? (
                        /* ── Welcome Hero ── */
                        <div
                          style={{
                            flex: 1, display: 'flex', flexDirection: 'column',
                            alignItems: 'center', justifyContent: 'center',
                            padding: '40px 24px', textAlign: 'center',
                          }}
                        >
                          <div
                            style={{
                              width: '64px', height: '64px', borderRadius: '50%',
                              background: 'linear-gradient(135deg, #1e2a1a, #0d1a0e)',
                              border: '2px solid #85683c',
                              display: 'flex', alignItems: 'center', justifyContent: 'center',
                              marginBottom: '20px',
                              boxShadow: '0 0 30px rgba(133,104,60,0.25)',
                            }}
                          >
                            <RobotIcon size={34} />
                          </div>

                          <h1
                            style={{
                              fontFamily: "'Cinzel', 'Georgia', serif",
                              fontSize: 'clamp(1.8rem, 3vw, 2.6rem)',
                              fontWeight: 700, color: '#ece7d8',
                              margin: '0 0 10px', letterSpacing: '0.02em',
                            }}
                          >
                            Ask the Archive
                          </h1>
                          <p style={{ color: '#6b6452', fontSize: '15px', margin: '0 0 36px', maxWidth: '500px', lineHeight: 1.6 }}>
                            Search across historical documents, war diaries, and military records — grounded in the museum's own AI archive.
                          </p>

                          {/* Suggestion Cards Grid */}
                          <div
                            style={{
                              display: 'grid',
                              gridTemplateColumns: 'repeat(2, 1fr)',
                              gap: '12px',
                              width: '100%',
                              maxWidth: '560px',
                              marginBottom: '32px',
                            }}
                          >
                            {SUGGESTIONS.map(s => (
                              <button
                                key={s.prompt}
                                type="button"
                                onClick={() => sendMessage(s.prompt)}
                                style={{
                                  display: 'flex', alignItems: 'center', gap: '12px',
                                  padding: '16px 18px', borderRadius: '12px',
                                  background: '#16160f', border: '1px solid #2a2a1e',
                                  color: '#ece7d8', fontSize: '13px', fontWeight: 500,
                                  cursor: 'pointer', textAlign: 'left',
                                  transition: 'all 0.18s ease',
                                }}
                                onMouseEnter={e => {
                                  const el = e.currentTarget as HTMLButtonElement;
                                  el.style.borderColor = '#d4a94a';
                                  el.style.background = '#1a1a0f';
                                  el.style.color = '#d4a94a';
                                }}
                                onMouseLeave={e => {
                                  const el = e.currentTarget as HTMLButtonElement;
                                  el.style.borderColor = '#2a2a1e';
                                  el.style.background = '#16160f';
                                  el.style.color = '#ece7d8';
                                }}
                              >
                                <span style={{ fontSize: '20px' }}>{s.icon}</span>
                                <span style={{ lineHeight: 1.3 }}>{s.label}</span>
                                <svg
                                  style={{ marginLeft: 'auto', flexShrink: 0, opacity: 0.4 }}
                                  width="14" height="14" viewBox="0 0 24 24"
                                  fill="none" stroke="currentColor" strokeWidth="2"
                                >
                                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
                                </svg>
                              </button>
                            ))}
                          </div>
                        </div>
                      ) : (
                        /* ── Active Conversation ── */
                        <div style={{ maxWidth: '760px', width: '100%', margin: '0 auto', padding: '28px 20px 8px' }}>
                          {messages.map((m, i) => (
                            <div
                              key={i}
                              style={{
                                display: 'flex',
                                justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start',
                                marginBottom: '18px',
                              }}
                            >
                              {m.role === 'assistant' && (
                                <div
                                  style={{
                                    width: '28px', height: '28px', borderRadius: '50%',
                                    background: '#1e2a1a', border: '1px solid #85683c',
                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                    flexShrink: 0, marginRight: '10px', marginTop: '4px',
                                  }}
                                >
                                  <RobotIcon size={14} />
                                </div>
                              )}
                              <div
                                style={{
                                  maxWidth: '78%', padding: '12px 16px', borderRadius: '14px',
                                  fontSize: '14px', lineHeight: 1.65, whiteSpace: 'pre-wrap',
                                  ...(m.role === 'user'
                                    ? {
                                      background: '#d4a94a', color: '#171207',
                                      fontWeight: 500, borderBottomRightRadius: '4px',
                                    }
                                    : {
                                      background: '#16160f', border: '1px solid #2a2a1e',
                                      color: '#ece7d8', borderBottomLeftRadius: '4px',
                                    }),
                                }}
                              >
                                {m.content}

                                {m.sources && m.sources.length > 0 && (
                                  <div style={{ marginTop: '10px', paddingTop: '10px', borderTop: '1px solid #2a2a1e' }}>
                                    <div style={{ fontSize: '10px', color: '#8a8578', fontWeight: 600, marginBottom: '8px', letterSpacing: '0.08em' }}>
                                      SOURCES &amp; DOCUMENTS
                                    </div>
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                                      {m.sources.map(s => {
                                        const ft = (s.file_type ?? '').toLowerCase();
                                        const fullUrl = getFullViewUrl(s.view_url);
                                        const isAudio = ['mp3', 'wav', 'aac', 'flac', 'ogg', 'm4a'].includes(ft);
                                        const isVideo = ['mp4', 'webm', 'mov', 'avi', 'mkv'].includes(ft);

                                        // Shared pill link (always rendered)
                                        const pillIcon = isAudio ? '🎵' : isVideo ? '🎬' : '📄';
                                        const pill = (
                                          <a
                                            href={fullUrl}
                                            target="_blank"
                                            rel="noreferrer"
                                            style={{
                                              fontSize: '11px', color: '#d4a94a',
                                              background: 'rgba(212,169,74,0.1)',
                                              border: '1px solid rgba(212,169,74,0.3)',
                                              borderRadius: '999px', padding: '3px 10px',
                                              textDecoration: 'none', display: 'inline-flex',
                                              alignItems: 'center', gap: '4px',
                                              alignSelf: 'flex-start',
                                            }}
                                          >
                                            {pillIcon} {s.title} · <span style={{ fontFamily: 'monospace' }}>{Math.round(s.similarity * 100)}%</span> ↗
                                          </a>
                                        );

                                        if (isAudio) {
                                          return (
                                            <div key={s.id} style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
                                              {pill}
                                              <audio
                                                controls
                                                src={fullUrl}
                                                style={{
                                                  width: '100%', maxWidth: '420px',
                                                  height: '36px', borderRadius: '8px',
                                                  accentColor: '#d4a94a',
                                                }}
                                              />
                                            </div>
                                          );
                                        }

                                        if (isVideo) {
                                          return (
                                            <div key={s.id} style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
                                              {pill}
                                              <video
                                                controls
                                                src={fullUrl}
                                                style={{
                                                  width: '100%', maxWidth: '440px',
                                                  borderRadius: '10px',
                                                  border: '1px solid #2a2a1e',
                                                  background: '#000',
                                                }}
                                              />
                                            </div>
                                          );
                                        }

                                        // Default: document pill only
                                        return <div key={s.id}>{pill}</div>;
                                      })}
                                    </div>
                                  </div>
                                )}
                              </div>
                            </div>
                          ))}

                          {loading && (
                            <div style={{ display: 'flex', justifyContent: 'flex-start', marginBottom: '18px' }}>
                              <div
                                style={{
                                  width: '28px', height: '28px', borderRadius: '50%',
                                  background: '#1e2a1a', border: '1px solid #85683c',
                                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                                  flexShrink: 0, marginRight: '10px',
                                }}
                              >
                                <RobotIcon size={14} />
                              </div>
                              <div
                                style={{
                                  background: '#16160f', border: '1px solid #2a2a1e',
                                  borderRadius: '14px', borderBottomLeftRadius: '4px',
                                  padding: '14px 18px', display: 'flex', alignItems: 'center', gap: '8px',
                                }}
                              >
                                {[0, 1, 2].map(i => (
                                  <span
                                    key={i}
                                    style={{
                                      display: 'inline-block', width: '6px', height: '6px',
                                      borderRadius: '50%', background: '#d4a94a',
                                      animation: `pac-bounce 1.2s ease-in-out ${i * 0.2}s infinite`,
                                    }}
                                  />
                                ))}
                              </div>
                            </div>
                          )}
                          <div ref={scrollRef} />
                        </div>
                      )}
                    </div>

                    {/* ── Input Bar (always visible at bottom) ── */}
                    <div
                      style={{
                        flexShrink: 0, padding: '16px 24px 20px',
                        borderTop: '1px solid #1e1e14', background: '#0f0f0d',
                      }}
                    >
                      <div
                        style={{
                          maxWidth: '760px', margin: '0 auto',
                          background: '#16160f', border: '1px solid #2a2a1e',
                          borderRadius: '14px', padding: '12px 16px',
                          transition: 'border-color 0.15s ease',
                          boxShadow: '0 4px 24px rgba(0,0,0,0.35)',
                        }}
                        onFocus={() => { }}
                        onBlur={() => { }}
                        ref={node => {
                          if (node) {
                            node.onfocus = () => { node.style.borderColor = '#d4a94a'; };
                            node.onblur = () => { node.style.borderColor = '#2a2a1e'; };
                          }
                        }}
                      >
                        <textarea
                          ref={inputRef}
                          value={input}
                          rows={1}
                          onChange={e => setInput(e.target.value)}
                          onKeyDown={e => {
                            if (e.key === 'Enter' && !e.shiftKey) {
                              e.preventDefault();
                              sendMessage(input);
                            }
                          }}
                          placeholder={hasStarted ? 'Ask a follow-up question...' : 'Ask anything about the archive...'}
                          style={{
                            display: 'block', width: '100%',
                            background: 'transparent', border: 'none', outline: 'none',
                            color: '#ece7d8', fontSize: '14px', lineHeight: 1.6,
                            resize: 'none', overflowY: 'hidden',
                            fontFamily: 'inherit',
                          }}
                          maxLength={maxChars}
                        />

                        {/* Toolbar row */}
                        <div
                          style={{
                            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                            marginTop: '10px', paddingTop: '10px', borderTop: '1px solid #1e1e14',
                          }}
                        >
                          <span style={{ fontSize: '11px', color: '#4a4a38', fontFamily: 'monospace' }}>
                            {charCount} / {maxChars.toLocaleString()}
                          </span>

                          <button
                            type="button"
                            onClick={() => sendMessage(input)}
                            disabled={!input.trim() || loading}
                            style={{
                              display: 'flex', alignItems: 'center', justifyContent: 'center',
                              width: '34px', height: '34px', borderRadius: '8px',
                              background: input.trim() && !loading ? '#d4a94a' : '#1e1e14',
                              border: input.trim() && !loading ? '1px solid #d4a94a' : '1px solid #2a2a1e',
                              color: input.trim() && !loading ? '#171207' : '#4a4a38',
                              cursor: input.trim() && !loading ? 'pointer' : 'not-allowed',
                              transition: 'all 0.15s ease',
                              flexShrink: 0,
                            }}
                            aria-label="Send message"
                          >
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                              <path strokeLinecap="round" strokeLinejoin="round" d="M5 12h14M13 6l6 6-6 6" />
                            </svg>
                          </button>
                        </div>
                      </div>

                      <div style={{ textAlign: 'center', marginTop: '8px', fontSize: '11px', color: '#3a3a2a' }}>
                        Archive Assistant may generate inaccurate information. Always verify against source documents.
                      </div>
                    </div>
                  </>
                )}
              </div>

              {/* ── RIGHT SIDEBAR — Recent Conversations ── */}
              <div
                style={{
                  width: '260px', flexShrink: 0,
                  background: '#0d0d0a', borderLeft: '1px solid #1e1e14',
                  display: 'flex', flexDirection: 'column',
                  padding: '20px 0',
                  overflowY: 'auto',
                }}
              >
                <div
                  style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    padding: '0 16px 14px', borderBottom: '1px solid #1e1e14',
                  }}
                >
                  <span style={{ fontSize: '12px', fontWeight: 700, color: '#6b6452', letterSpacing: '0.1em', textTransform: 'uppercase' }}>
                    Recent ({threads.length})
                  </span>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#6b6452" strokeWidth="1.8">
                    <circle cx="12" cy="12" r="10" />
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3" />
                  </svg>
                </div>

                <div style={{ flex: 1, padding: '12px 12px' }}>
                  {threads.length === 0 ? (
                    <div style={{ textAlign: 'center', color: '#3a3a2a', fontSize: '12px', marginTop: '24px', lineHeight: 1.6 }}>
                      Your conversation<br />history will appear here
                    </div>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      {threads.map(thread => (
                        <button
                          key={thread.id}
                          type="button"
                          onClick={() => loadThread(thread)}
                          style={{
                            display: 'flex', flexDirection: 'column', alignItems: 'flex-start',
                            padding: '10px 12px', borderRadius: '8px', border: 'none',
                            background: activeThreadId === thread.id ? '#1e1e14' : 'transparent',
                            cursor: 'pointer', textAlign: 'left', width: '100%',
                            transition: 'background 0.12s ease',
                          }}
                          onMouseEnter={e => {
                            if (activeThreadId !== thread.id)
                              (e.currentTarget as HTMLButtonElement).style.background = '#16160f';
                          }}
                          onMouseLeave={e => {
                            if (activeThreadId !== thread.id)
                              (e.currentTarget as HTMLButtonElement).style.background = 'transparent';
                          }}
                        >
                          <span
                            style={{
                              fontSize: '12px', fontWeight: 600,
                              color: activeThreadId === thread.id ? '#E1BC78' : '#ece7d8',
                              marginBottom: '3px', lineHeight: 1.3,
                              display: '-webkit-box', WebkitLineClamp: 1,
                              WebkitBoxOrient: 'vertical', overflow: 'hidden',
                              width: '100%',
                            }}
                          >
                            {thread.title}
                          </span>
                          <span
                            style={{
                              fontSize: '11px', color: '#4a4a38', lineHeight: 1.4,
                              display: '-webkit-box', WebkitLineClamp: 2,
                              WebkitBoxOrient: 'vertical', overflow: 'hidden',
                              width: '100%',
                            }}
                          >
                            {thread.preview}
                          </span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* Bounce animation keyframes */}
              <style>{`
                @keyframes pac-bounce {
                  0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
                  40% { transform: scale(1); opacity: 1; }
                }
                @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
              `}</style>
            </motion.div>
          )}
        </AnimatePresence>,
        document.body
      )}
    </>
  );
}
