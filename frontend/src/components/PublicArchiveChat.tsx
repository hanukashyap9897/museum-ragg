import { useState, useRef, useEffect } from "react";
import { FASTAPI_BASE_URL } from "../config/api";

interface Source {
    id: string;
    title: string;
    similarity: number;
    view_url: string;
}

interface Message {
    role: "user" | "assistant";
    content: string;
    sources?: Source[];
}

const SUGGESTIONS = [
    "Find officer posting orders",
    "Tell me about the Battle of Kohima",
    "Search training conference memos",
    "Show recent archival uploads",
];

/**
 * Full-screen takeover chat experience for the public museum site.
 * Replaces the old small dropdown "Search Archive" panel — this covers
 * the entire viewport like Copilot/ChatGPT/Claude's own chat window,
 * and holds a real conversation (via /chat/ask) instead of a raw list
 * of keyword matches.
 *
 * Usage: mount <PublicArchiveChat /> once near the root of the app
 * (e.g. in App.tsx). It renders its own floating trigger button AND
 * the full-screen overlay — nothing else needs to call it.
 */
export default function PublicArchiveChat() {
    const [open, setOpen] = useState(false);
    const [messages, setMessages] = useState<Message[]>([]);
    const [input, setInput] = useState("");
    const [loading, setLoading] = useState(false);
    const scrollRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        scrollRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages]);

    useEffect(() => {
        if (open) setTimeout(() => inputRef.current?.focus(), 100);
    }, [open]);

    async function sendMessage(text: string) {
        const question = text.trim();
        if (!question || loading) return;

        setMessages((prev) => [...prev, { role: "user", content: question }]);
        setInput("");
        setLoading(true);

        try {
            const res = await fetch(`${FASTAPI_BASE_URL}/chat/ask`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message: question, top_k: 5 }),
            });
            if (!res.ok) throw new Error(`Server returned ${res.status}`);
            const data = await res.json();
            setMessages((prev) => [
                ...prev,
                { role: "assistant", content: data.answer, sources: data.sources },
            ]);
        } catch {
            setMessages((prev) => [
                ...prev,
                {
                    role: "assistant",
                    content:
                        "I couldn't reach the archive right now. Please check your connection and try again.",
                },
            ]);
        } finally {
            setLoading(false);
        }
    }

    const hasStarted = messages.length > 0;

    return (
        <>
            {/* Floating trigger button — bottom-right corner, always visible */}
            {!open && (
                <button className="pac-trigger" onClick={() => setOpen(true)} aria-label="Open archive assistant">
                    <span className="pac-trigger-dot" />
                    <svg width="26" height="26" viewBox="0 0 24 24" fill="none">
                        <rect x="4" y="7" width="16" height="12" rx="3" stroke="#d4a94a" strokeWidth="1.6" />
                        <circle cx="9" cy="13" r="1.4" fill="#d4a94a" />
                        <circle cx="15" cy="13" r="1.4" fill="#d4a94a" />
                        <path d="M12 7V4" stroke="#d4a94a" strokeWidth="1.6" strokeLinecap="round" />
                        <circle cx="12" cy="3" r="1.2" fill="#d4a94a" />
                    </svg>
                </button>
            )}

            {open && (
                <div className="pac-overlay">
                    <style>{`
            .pac-trigger {
              position: fixed; bottom: 28px; right: 28px; z-index: 900;
              width: 56px; height: 56px; border-radius: 50%;
              background: #16160f; border: 1px solid #2a2a1e;
              display: flex; align-items: center; justify-content: center;
              cursor: pointer; box-shadow: 0 4px 20px rgba(0,0,0,0.4);
              transition: transform 0.15s ease;
            }
            .pac-trigger:hover { transform: scale(1.06); }
            .pac-trigger-dot {
              position: absolute; top: 6px; right: 6px;
              width: 9px; height: 9px; border-radius: 50%;
              background: #d4a94a;
            }
            .pac-overlay {
              position: fixed; inset: 0; z-index: 1000;
              background: #0a0a08;
              display: flex; flex-direction: column;
              font-family: 'Segoe UI', system-ui, sans-serif;
              color: #ece7d8;
            }
            .pac-header {
              display: flex; align-items: center; justify-content: space-between;
              padding: 16px 24px; border-bottom: 1px solid #2a2a1e;
              flex-shrink: 0;
            }
            .pac-header-title {
              font-family: Georgia, serif; font-size: 1.1rem; letter-spacing: 0.03em;
              display: flex; align-items: center; gap: 10px;
            }
            .pac-header-title .pac-badge {
              font-size: 0.65rem; letter-spacing: 0.08em; color: #8a8578;
              border: 1px solid #2a2a1e; border-radius: 999px; padding: 2px 8px;
            }
            .pac-close {
              background: none; border: 1px solid #2a2a1e; color: #ece7d8;
              width: 34px; height: 34px; border-radius: 8px; cursor: pointer;
              font-size: 1rem; display: flex; align-items: center; justify-content: center;
            }
            .pac-close:hover { border-color: #d4a94a; color: #d4a94a; }
            .pac-body { flex: 1; overflow-y: auto; display: flex; flex-direction: column; }
            .pac-hero {
              flex: 1; display: flex; flex-direction: column;
              align-items: center; justify-content: center; padding: 40px 24px; text-align: center;
            }
            .pac-hero h1 {
              font-family: Georgia, serif; font-weight: 600; font-size: 2.1rem;
              margin: 0 0 8px; color: #ece7d8;
            }
            .pac-hero p { color: #8a8578; font-size: 0.95rem; margin: 0 0 32px; }
            .pac-input-wrap { width: 100%; max-width: 680px; }
            .pac-input-box {
              display: flex; align-items: center; gap: 10px;
              background: #16160f; border: 1px solid #2a2a1e; border-radius: 14px;
              padding: 14px 16px; transition: border-color 0.15s ease;
            }
            .pac-input-box:focus-within { border-color: #d4a94a; }
            .pac-input-box input {
              flex: 1; background: none; border: none; outline: none;
              color: #ece7d8; font-size: 0.95rem;
            }
            .pac-input-box input::placeholder { color: #8a8578; }
            .pac-send {
              background: #d4a94a; color: #171207; border: none; border-radius: 8px;
              padding: 8px 16px; font-weight: 600; font-size: 0.85rem; cursor: pointer;
            }
            .pac-send:disabled { opacity: 0.4; cursor: not-allowed; }
            .pac-chips {
              display: flex; flex-wrap: wrap; gap: 10px; justify-content: center; margin-top: 22px;
            }
            .pac-chip {
              background: #16160f; border: 1px solid #2a2a1e; color: #ece7d8;
              border-radius: 999px; padding: 9px 16px; font-size: 0.85rem; cursor: pointer;
            }
            .pac-chip:hover { border-color: #d4a94a; color: #d4a94a; }
            .pac-messages { max-width: 760px; width: 100%; margin: 0 auto; padding: 28px 20px 8px; }
            .pac-msg { margin-bottom: 20px; display: flex; }
            .pac-msg.user { justify-content: flex-end; }
            .pac-bubble {
              max-width: 78%; padding: 12px 16px; border-radius: 12px;
              font-size: 0.94rem; line-height: 1.55; white-space: pre-wrap;
            }
            .pac-msg.user .pac-bubble { background: #d4a94a; color: #171207; border-bottom-right-radius: 4px; }
            .pac-msg.assistant .pac-bubble {
              background: #1e1e14; border: 1px solid #2a2a1e; border-bottom-left-radius: 4px;
            }
            .pac-sources { margin-top: 10px; display: flex; flex-wrap: wrap; gap: 8px; }
            .pac-source-pill {
              font-size: 0.75rem; color: #d4a94a; background: rgba(212,169,74,0.1);
              border: 1px solid rgba(212,169,74,0.3); border-radius: 999px;
              padding: 4px 10px; text-decoration: none;
            }
            .pac-source-pill:hover { background: rgba(212,169,74,0.2); }
            .pac-footer { max-width: 760px; width: 100%; margin: 0 auto; padding: 16px 20px 28px; flex-shrink: 0; }
            .pac-typing { color: #8a8578; font-size: 0.85rem; font-style: italic; padding-left: 4px; }
          `}</style>

                    <div className="pac-header">
                        <div className="pac-header-title">
                            Archive Assistant <span className="pac-badge">ASSAM REGIMENT DIGITAL MUSEUM</span>
                        </div>
                        <button className="pac-close" onClick={() => setOpen(false)} aria-label="Close">✕</button>
                    </div>

                    <div className="pac-body">
                        {!hasStarted ? (
                            <div className="pac-hero">
                                <h1>Ask the Archive</h1>
                                <p>Search across historical documents, war diaries, and military records — grounded in the museum's own archive.</p>
                                <div className="pac-input-wrap">
                                    <div className="pac-input-box">
                                        <input
                                            ref={inputRef}
                                            value={input}
                                            onChange={(e) => setInput(e.target.value)}
                                            onKeyDown={(e) => e.key === "Enter" && sendMessage(input)}
                                            placeholder="Ask anything about the archive..."
                                        />
                                        <button className="pac-send" onClick={() => sendMessage(input)} disabled={!input.trim() || loading}>
                                            Ask
                                        </button>
                                    </div>
                                    <div className="pac-chips">
                                        {SUGGESTIONS.map((s) => (
                                            <button key={s} className="pac-chip" onClick={() => sendMessage(s)}>{s}</button>
                                        ))}
                                    </div>
                                </div>
                            </div>
                        ) : (
                            <div className="pac-messages">
                                {messages.map((m, i) => (
                                    <div key={i} className={`pac-msg ${m.role}`}>
                                        <div className="pac-bubble">
                                            {m.content}
                                            {m.sources && m.sources.length > 0 && (
                                                <div className="pac-sources">
                                                    {m.sources.map((s) => (
                                                        <a key={s.id} className="pac-source-pill" href={`${FASTAPI_BASE_URL}${s.view_url}`} target="_blank" rel="noreferrer">
                                                            {s.title} · {Math.round(s.similarity * 100)}%
                                                        </a>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                ))}
                                {loading && <div className="pac-typing">Reading the archive...</div>}
                                <div ref={scrollRef} />
                            </div>
                        )}
                    </div>

                    {hasStarted && (
                        <div className="pac-footer">
                            <div className="pac-input-box">
                                <input
                                    value={input}
                                    onChange={(e) => setInput(e.target.value)}
                                    onKeyDown={(e) => e.key === "Enter" && sendMessage(input)}
                                    placeholder="Ask a follow-up..."
                                />
                                <button className="pac-send" onClick={() => sendMessage(input)} disabled={!input.trim() || loading}>
                                    Ask
                                </button>
                            </div>
                        </div>
                    )}
                </div>
            )}
        </>
    );
}