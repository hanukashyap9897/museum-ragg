"""
LLM service for RAG chat — calls Groq API (llama-3.3-70b-versatile)
with retrieved document context to produce grounded answers.
"""

from groq import Groq
from app.config.settings import settings

_client = None


def _get_client() -> Groq:
    """Lazily initialize the Groq client (avoids crashing app startup if key is missing)."""
    global _client
    if _client is None:
        if not settings.GROQ_API_KEY:
            raise RuntimeError(
                "GROQ_API_KEY is not set. Add it to your .env file: GROQ_API_KEY=gsk_..."
            )
        _client = Groq(api_key=settings.GROQ_API_KEY)
    return _client


SYSTEM_PROMPT = """You are the Archive Assistant for the Assam Regiment Digital Museum — a knowledgeable, conversational guide to the museum's collection, not a search results page.

You'll be given some archive material as context, and a visitor's question. Answer the way a well-informed museum guide would speak to a visitor: naturally, directly, and confidently.

How to talk:
- Just answer the question. Don't narrate your process — never say things like "Based on the archival documents I found..." or "Document 1 and Document 2 show...". A person doesn't care how you found the answer, just what it is.
- Weave in specific details (names, dates, places, ranks) naturally into sentences, the way you'd explain something to a person standing next to you.
- If multiple documents overlap or repeat the same thing, just say it once — don't narrate that you noticed duplicates.
- It's fine to mention a document by its title in passing if it adds useful context ("a training memo from 2004 mentions..."), but don't structure your whole answer around listing documents.
- If the material only partly answers the question, answer the part you can plainly, then briefly note what's missing — don't hedge every sentence.
- If there's genuinely nothing relevant in the material, just say so plainly and briefly, like a person would ("I don't have anything on that in the archive yet") — don't apologize elaborately.
- Never invent dates, names, ranks, or facts that aren't in the material.
- Keep the tone warm and respectful of the subject matter (military history, honors, service), but write like a person talking, not a report.
"""


_AUDIO_VIDEO_TYPES = {"mp3", "wav", "aac", "flac", "ogg", "m4a", "mp4", "webm", "mov", "avi", "mkv"}


def build_context(search_results: list[dict]) -> str:
    """Formats retrieved documents into a numbered context block for the LLM prompt."""
    if not search_results:
        return "No relevant documents were found in the archive."

    blocks = []
    for i, doc in enumerate(search_results, start=1):
        file_type = (doc.get("file_type") or "").lower().lstrip(".")
        excerpt = doc.get("ocr_excerpt") or doc.get("icr_excerpt")

        if not excerpt:
            if file_type in _AUDIO_VIDEO_TYPES:
                # Tell the LLM this is a media file that exists in the archive.
                media_kind = "audio" if file_type in {"mp3", "wav", "aac", "flac", "ogg", "m4a"} else "video"
                excerpt = (
                    f"(This is a {media_kind} file available in the archive. "
                    f"The file is titled '{doc.get('title') or 'Untitled'}' and can be played directly.)"
                )
            else:
                excerpt = "(no extracted text available)"

        blocks.append(
            f"[Document {i}] Title: {doc.get('title') or 'Untitled'} "
            f"(Category: {doc.get('category') or 'N/A'}, Collection: {doc.get('collection') or 'N/A'})\n"
            f"Excerpt: {excerpt}"
        )
    return "\n\n".join(blocks)



def generate_answer(question: str, search_results: list[dict]) -> str:
    """Sends the question + retrieved context to Groq and returns the answer text."""
    client = _get_client()
    context = build_context(search_results)

    user_prompt = f"""Archive material:
{context}

Visitor's question: {question}

Answer naturally and directly, as described in your instructions."""

    response = client.chat.completions.create(
        model=settings.GROQ_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
        max_tokens=800,
    )

    return response.choices[0].message.content