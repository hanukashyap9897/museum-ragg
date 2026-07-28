// Centralized API configuration for FastAPI (RAG) and Node.js (Express/MongoDB) backends

export const FASTAPI_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || 'https://museum-ai-2-0-1-rag.onrender.com'
).replace(/\/$/, '');

export const NODE_API_BASE_URL = (
  import.meta.env.VITE_NODE_API_BASE_URL || 'https://museum-ai-2-0-1-node.onrender.com'
).replace(/\/$/, '');
