"""
Retrieval-Augmented Generation (RAG) engine.
Uses SentenceTransformers for embeddings and FAISS for vector search.
"""
import threading
from typing import List

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

# ---------------------------------------------------------------------------
# Module-level singletons (CPU-pinned to avoid ZeroGPU CUDA interception)
# ---------------------------------------------------------------------------

_embedder = None
_embedding_dim = 384  # paraphrase-multilingual-MiniLM-L12-v2 / all-MiniLM-L6-v2 dimension (384)

def get_embedder():
    global _embedder
    if _embedder is None:
        try:
            # Phase 2: High-accuracy multilingual sentence transformer (50+ languages incl. Hindi, Kannada, etc.)
            print("[RAG] Loading multilingual embedding model (paraphrase-multilingual-MiniLM-L12-v2)...")
            _embedder = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2", device="cpu")
            print("[RAG] ✓ Multilingual embedder loaded successfully.")
        except Exception as _m_err:
            print(f"[RAG Note] Multilingual embedder unavailable ({_m_err}), falling back to all-MiniLM-L6-v2...")
            _embedder = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
    return _embedder

_index: faiss.IndexFlatL2 = faiss.IndexFlatL2(_embedding_dim)
_index_chunks: List[str] = []
_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    """Split *text* into overlapping chunks of roughly *chunk_size* characters."""
    chunks: List[str] = []
    start = 0
    text_len = len(text)
    while start < text_len:
        end = min(start + chunk_size, text_len)
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return chunks


def _read_file(filepath: str) -> str:
    """Read text content from a PDF, TXT, or MD file."""
    lower = filepath.lower()
    if lower.endswith(".pdf"):
        from pypdf import PdfReader  # type: ignore
        reader = PdfReader(filepath)
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages)
    else:
        # Plain text / Markdown
        with open(filepath, "r", encoding="utf-8", errors="ignore") as fh:
            return fh.read()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def add_document(filepath: str) -> None:
    """
    Ingest a document into the FAISS index.

    Supported formats: PDF, TXT, MD.

    Parameters
    ----------
    filepath : str
        Absolute or relative path to the document.
    """
    text = _read_file(filepath)
    if not text.strip():
        return

    chunks = _chunk_text(text)
    if not chunks:
        return

    embedder = get_embedder()
    embeddings = embedder.encode(chunks, convert_to_numpy=True).astype(np.float32)

    with _lock:
        _index.add(embeddings)
        _index_chunks.extend(chunks)


def prewarm_embedder() -> None:
    """
    Pre-load the sentence-transformer model in a background thread at startup.
    Call this once from the FastAPI startup event so the first live call doesn't
    block waiting for a ~470 MB model download.
    """
    import threading
    def _load():
        try:
            get_embedder()
            print("[RAG] ✓ Embedder pre-loaded at startup (live calls will not block).")
        except Exception as _e:
            print(f"[RAG] Embedder pre-load note: {_e}")
    threading.Thread(target=_load, daemon=True).start()


def search(query: str, top_k: int = 3, timeout: float = 1.5) -> str:
    """
    Search the FAISS index for chunks relevant to *query*.

    Parameters
    ----------
    query : str
        The search query string.
    top_k : int
        Number of top results to return.
    timeout : float
        Maximum seconds to wait for the embedder (default 1.5 s so live
        phone calls are never blocked by a slow/cold model load).

    Returns
    -------
    str
        Concatenated relevant text chunks, or an empty string if the index
        is empty or the embedder is not yet ready within *timeout*.
    """
    import concurrent.futures
    # Fast path: nothing indexed yet → skip entirely
    if _index.ntotal == 0:
        return ""

    def _do_search():
        with _lock:
            if _index.ntotal == 0:
                return ""
            embedder = get_embedder()
            query_embedding = embedder.encode([query], convert_to_numpy=True).astype(np.float32)
            actual_k = min(top_k, _index.ntotal)
            _, indices = _index.search(query_embedding, actual_k)
            results = []
            for idx in indices[0]:
                if 0 <= idx < len(_index_chunks):
                    results.append(_index_chunks[idx])
            return "\n\n".join(results)

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(_do_search)
            return future.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        print(f"[RAG] search() timed out after {timeout}s — skipping for this turn.")
        return ""
    except Exception as _e:
        print(f"[RAG] search() error: {_e}")
        return ""
