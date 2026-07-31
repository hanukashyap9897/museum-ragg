// Centralized API configuration for FastAPI backend (serves both RAG and CMS)

export const FASTAPI_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || 'https://museum-ai-2-0-1-rag.onrender.com'
).replace(/\/$/, '');

// Alias kept for backward compatibility — Node backend was
// retired; both names now point to the same FastAPI server.
export const NODE_API_BASE_URL = FASTAPI_BASE_URL;
