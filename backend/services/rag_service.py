"""
FarmAI — Local RAG Service
Lightweight keyword-scoring RAG for cotton, wheat, and mango crop knowledge.

• Loads .md / .txt / .json / .csv files from backend/cotton, backend/wheat, backend/mango
• Chunks content into ~700–1200 char pieces at startup
• Scores chunks against user query using keyword overlap
• Returns top 3–5 chunks for Gemini prompt injection

No vector DB, no Chroma/FAISS/Pinecone/LangChain.
"""

import os
import re
import json
import csv
import io
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory chunk cache  (populated once at startup)
# ---------------------------------------------------------------------------
_RAG_CACHE: dict[str, list[dict]] = {
    "cotton": [],
    "wheat": [],
    "mango": [],
}

_RAG_INITIALIZED: bool = False

# ---------------------------------------------------------------------------
# Crop aliases  (user text → canonical crop key)
# ---------------------------------------------------------------------------
_CROP_ALIASES: dict[str, str] = {
    # Cotton
    "cotton": "cotton",
    "کپاس": "cotton",
    "kapas": "cotton",
    "kapaas": "cotton",
    # Wheat
    "wheat": "wheat",
    "گندم": "wheat",
    "gandum": "wheat",
    # Mango
    "mango": "mango",
    "آم": "mango",
    "aam": "mango",
}

# ---------------------------------------------------------------------------
# Symptom keywords for scoring  (Urdu / Roman Urdu / English)
# ---------------------------------------------------------------------------
_SYMPTOM_KEYWORDS: list[str] = [
    # Urdu
    "پتے", "پیلے نشان", "کالے دھبے", "بیماری", "کیڑا", "کیڑے",
    "جڑ", "پھل", "سوکھنا", "مڑنا", "داغ", "سپرے", "کھاد", "پانی",
    # Roman Urdu
    "pattay", "patton", "peelay", "zard", "nishan",
    "kalay dhabbay", "daag", "bemari", "bimari",
    "keera", "keeray", "jar", "phal", "sookhna", "murna",
    "spray", "khaad", "pani",
    # English
    "leaves", "yellow spots", "black spots", "disease", "pest",
    "insect", "root", "fruit", "drying", "curling",
    "spray", "fertilizer", "water",
]

# Supported file extensions
_SUPPORTED_EXTENSIONS = {".txt", ".md", ".json", ".csv"}

# Chunking parameters
_MIN_CHUNK = 200
_TARGET_CHUNK = 700
_MAX_CHUNK = 1200


# ═══════════════════════════════════════════════════════════════════════════
#  FILE LOADING
# ═══════════════════════════════════════════════════════════════════════════

def _read_file_content(file_path: str) -> str:
    """Read a supported file and return its text content."""
    ext = os.path.splitext(file_path)[1].lower()

    try:
        if ext in (".txt", ".md"):
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()

        elif ext == ".json":
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Flatten JSON to readable text
            if isinstance(data, str):
                return data
            return json.dumps(data, ensure_ascii=False, indent=2)

        elif ext == ".csv":
            with open(file_path, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                rows = list(reader)
            # Convert CSV rows into readable text
            lines = []
            for row in rows:
                lines.append(" | ".join(row))
            return "\n".join(lines)

    except Exception as e:
        logger.warning("Failed to read file %s: %s", file_path, e)

    return ""


# ═══════════════════════════════════════════════════════════════════════════
#  CHUNKING
# ═══════════════════════════════════════════════════════════════════════════

def _split_into_chunks(text: str) -> list[str]:
    """
    Split text into chunks of ~700–1200 characters.
    Prefers splitting at headings (## / ###), double newlines, then single newlines.
    Never cuts mid-word.
    """
    if not text or not text.strip():
        return []

    # Step 1: Split by headings first (## or ###)
    sections = re.split(r'(?=\n#{2,3}\s)', text)

    chunks: list[str] = []

    for section in sections:
        section = section.strip()
        if not section:
            continue

        if len(section) <= _MAX_CHUNK:
            if len(section) >= _MIN_CHUNK:
                chunks.append(section)
            elif chunks:
                # Merge tiny section with previous chunk if fits
                if len(chunks[-1]) + len(section) + 1 <= _MAX_CHUNK:
                    chunks[-1] = chunks[-1] + "\n" + section
                else:
                    chunks.append(section)
            else:
                chunks.append(section)
            continue

        # Section is too large — split by paragraphs (double newlines)
        paragraphs = re.split(r'\n\s*\n', section)
        current_chunk = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if not current_chunk:
                current_chunk = para
            elif len(current_chunk) + len(para) + 2 <= _MAX_CHUNK:
                current_chunk = current_chunk + "\n\n" + para
            else:
                # Flush current_chunk
                if len(current_chunk) >= _MIN_CHUNK:
                    chunks.append(current_chunk)
                elif chunks:
                    if len(chunks[-1]) + len(current_chunk) + 1 <= _MAX_CHUNK:
                        chunks[-1] = chunks[-1] + "\n" + current_chunk
                    else:
                        chunks.append(current_chunk)
                else:
                    chunks.append(current_chunk)
                current_chunk = para

                # If the para itself is too large, split by single newlines
                if len(current_chunk) > _MAX_CHUNK:
                    lines = current_chunk.split("\n")
                    current_chunk = ""
                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue
                        if not current_chunk:
                            current_chunk = line
                        elif len(current_chunk) + len(line) + 1 <= _MAX_CHUNK:
                            current_chunk = current_chunk + "\n" + line
                        else:
                            if len(current_chunk) >= _MIN_CHUNK:
                                chunks.append(current_chunk)
                            elif chunks:
                                if len(chunks[-1]) + len(current_chunk) + 1 <= _MAX_CHUNK:
                                    chunks[-1] = chunks[-1] + "\n" + current_chunk
                                else:
                                    chunks.append(current_chunk)
                            else:
                                chunks.append(current_chunk)
                            current_chunk = line

        # Flush remaining
        if current_chunk and current_chunk.strip():
            if len(current_chunk) >= _MIN_CHUNK:
                chunks.append(current_chunk)
            elif chunks:
                if len(chunks[-1]) + len(current_chunk) + 1 <= _MAX_CHUNK:
                    chunks[-1] = chunks[-1] + "\n" + current_chunk
                else:
                    chunks.append(current_chunk)
            else:
                chunks.append(current_chunk)

    # Filter out empty/whitespace-only chunks
    return [c.strip() for c in chunks if c.strip()]


# ═══════════════════════════════════════════════════════════════════════════
#  INITIALIZATION  (called once at FastAPI startup)
# ═══════════════════════════════════════════════════════════════════════════

def initialize_rag_cache() -> None:
    """
    Load and chunk all crop knowledge files into memory.
    Safe — never crashes; logs warnings for missing/unreadable files.
    """
    global _RAG_INITIALIZED

    # Determine base directory (backend/)
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    crop_folders = {
        "cotton": os.path.join(base_dir, "cotton"),
        "wheat": os.path.join(base_dir, "wheat"),
        "mango": os.path.join(base_dir, "mango"),
    }

    total_files = 0
    total_chunks = 0

    for crop_name, folder_path in crop_folders.items():
        if not os.path.isdir(folder_path):
            logger.warning("[RAG] Folder missing, skipping: %s", folder_path)
            continue

        try:
            files = os.listdir(folder_path)
        except Exception as e:
            logger.warning("[RAG] Cannot list folder %s: %s", folder_path, e)
            continue

        crop_chunks: list[dict] = []

        for filename in sorted(files):
            ext = os.path.splitext(filename)[1].lower()
            if ext not in _SUPPORTED_EXTENSIONS:
                logger.debug("[RAG] Skipping unsupported file: %s", filename)
                continue

            file_path = os.path.join(folder_path, filename)
            content = _read_file_content(file_path)
            if not content or not content.strip():
                logger.warning("[RAG] Empty or unreadable file: %s", filename)
                continue

            total_files += 1
            chunks = _split_into_chunks(content)

            for chunk_text in chunks:
                crop_chunks.append({
                    "crop": crop_name,
                    "file_name": filename,
                    "chunk_text": chunk_text,
                })

            logger.info(
                "[RAG] Loaded %s: %d chunks from %s",
                crop_name, len(chunks), filename
            )

        _RAG_CACHE[crop_name] = crop_chunks
        total_chunks += len(crop_chunks)

    _RAG_INITIALIZED = True
    logger.info(
        "[RAG] Cache initialized: %d files, %d total chunks across %d crops",
        total_files, total_chunks, len(crop_folders)
    )


# ═══════════════════════════════════════════════════════════════════════════
#  CROP DETECTION
# ═══════════════════════════════════════════════════════════════════════════

def detect_rag_crop(text: str) -> Optional[str]:
    """
    Detect crop from user text using aliases.
    Returns 'cotton', 'wheat', 'mango', or None if not detected.
    """
    if not text:
        return None

    text_lower = text.lower()

    for alias, crop in _CROP_ALIASES.items():
        # Check in lowered text for Latin aliases
        if alias.lower() in text_lower:
            return crop
        # Check in original text for Urdu script aliases
        if alias in text:
            return crop

    return None


# ═══════════════════════════════════════════════════════════════════════════
#  CHUNK SCORING & RETRIEVAL
# ═══════════════════════════════════════════════════════════════════════════

def _score_chunk(chunk: dict, user_text: str, detected_crop: Optional[str]) -> float:
    """Score a chunk against the user query."""
    score = 0.0
    chunk_text_lower = chunk["chunk_text"].lower()
    user_text_lower = user_text.lower() if user_text else ""

    # 1. Crop alias match in chunk (+3)
    if detected_crop:
        for alias, crop in _CROP_ALIASES.items():
            if crop == detected_crop and (alias.lower() in chunk_text_lower or alias in chunk["chunk_text"]):
                score += 3.0
                break

    # 2. Symptom keyword match (+2 each)
    for keyword in _SYMPTOM_KEYWORDS:
        kw_lower = keyword.lower()
        if kw_lower in user_text_lower or keyword in user_text:
            # Check if this keyword also appears in the chunk
            if kw_lower in chunk_text_lower or keyword in chunk["chunk_text"]:
                score += 2.0

    # 3. General query word overlap (+1 each, for words ≥ 3 chars)
    user_words = set(re.findall(r'\b\w+\b', user_text_lower))
    # Also include Urdu words from original text
    urdu_words = set(re.findall(r'[\u0600-\u06FF]+', user_text or ""))
    all_user_words = user_words | urdu_words

    for word in all_user_words:
        if len(word) < 3:
            continue
        if word in chunk_text_lower or word in chunk["chunk_text"]:
            score += 1.0

    return score


def retrieve_chunks(
    user_text: str,
    detected_crop: Optional[str] = None,
    top_k: int = 5,
    min_score: float = 3.0,
) -> list[dict]:
    """
    Retrieve the top-k most relevant chunks for the user query.

    Parameters
    ----------
    user_text : str
        The farmer's query text.
    detected_crop : str | None
        Detected crop name ('cotton', 'wheat', 'mango') or None.
    top_k : int
        Max number of chunks to return (3–5).
    min_score : float
        Minimum score threshold.

    Returns
    -------
    list[dict] with keys: crop, file_name, chunk_text, score
    """
    if not _RAG_INITIALIZED or not user_text:
        return []

    # Determine which pools to search
    if detected_crop and detected_crop in _RAG_CACHE:
        search_pools = [_RAG_CACHE[detected_crop]]
    else:
        # Search across all three crops lightly
        search_pools = [_RAG_CACHE[c] for c in ("cotton", "wheat", "mango")]

    scored_chunks: list[dict] = []

    for pool in search_pools:
        for chunk in pool:
            score = _score_chunk(chunk, user_text, detected_crop)
            if score >= min_score:
                scored_chunks.append({
                    "crop": chunk["crop"],
                    "file_name": chunk["file_name"],
                    "chunk_text": chunk["chunk_text"],
                    "score": score,
                })

    # Sort by score descending, take top_k
    scored_chunks.sort(key=lambda c: c["score"], reverse=True)
    return scored_chunks[:top_k]


# ═══════════════════════════════════════════════════════════════════════════
#  FORMAT FOR GEMINI PROMPT
# ═══════════════════════════════════════════════════════════════════════════

def format_rag_context(chunks: list[dict]) -> str:
    """
    Format retrieved chunks into a text block for Gemini prompt injection.
    Does NOT expose full file paths.
    """
    if not chunks:
        return ""

    header = (
        "Use the following local FarmAI crop knowledge as trusted reference "
        "context when relevant. Do not copy it word-for-word unless needed. "
        "Use it to improve accuracy and practical advice. If the context is "
        "not relevant, ignore it.\n\n"
        "RAG_CONTEXT:\n"
    )

    entries = []
    for i, chunk in enumerate(chunks, 1):
        # Truncate chunk_text for prompt to avoid huge context
        ctx_text = chunk["chunk_text"]
        if len(ctx_text) > 1000:
            ctx_text = ctx_text[:1000] + "..."

        entries.append(
            f"{i}. Crop: {chunk['crop']} | Source: {chunk['file_name']}\n"
            f"   Context: {ctx_text}"
        )

    return header + "\n\n".join(entries)


# ═══════════════════════════════════════════════════════════════════════════
#  RAG STATUS BUILDER
# ═══════════════════════════════════════════════════════════════════════════

def build_rag_status(
    detected_crop: Optional[str],
    chunks: list[dict],
    error: Optional[str] = None,
) -> dict:
    """
    Build the rag_status metadata dict for the API response.
    Does NOT expose full paths.
    """
    if error:
        return {
            "enabled": True,
            "crop_detected": detected_crop or "unknown",
            "chunks_used": 0,
            "files_used": [],
            "confidence": "low",
            "error": error,
        }

    if not chunks:
        return {
            "enabled": True,
            "crop_detected": detected_crop or "unknown",
            "chunks_used": 0,
            "files_used": [],
            "confidence": "low",
        }

    # Determine confidence from scores
    avg_score = sum(c["score"] for c in chunks) / len(chunks)
    if avg_score >= 8.0:
        confidence = "high"
    elif avg_score >= 5.0:
        confidence = "medium"
    else:
        confidence = "low"

    # Unique file names only
    files_used = list(dict.fromkeys(c["file_name"] for c in chunks))

    return {
        "enabled": True,
        "crop_detected": detected_crop or "unknown",
        "chunks_used": len(chunks),
        "files_used": files_used,
        "confidence": confidence,
    }
