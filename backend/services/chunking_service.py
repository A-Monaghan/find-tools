"""
Advanced chunking strategies for research documents.
Provides multiple chunking approaches for optimal retrieval,
including semantic chunking based on embedding similarity.
"""

import re
from typing import List, Tuple, Optional
import numpy as np
import tiktoken

# Abbreviations that should not trigger a sentence break
_ABBREVIATIONS = (
    r"Mr|Mrs|Ms|Dr|Prof|Sr|Jr|Gen|Gov|Sgt|Cpl|Pvt|Capt|Lt|Col|Maj"
    r"|Inc|Ltd|Corp|Co|Est|Dept|Div|Assoc|Univ"
    r"|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
    r"|U\.S|U\.K|E\.U|U\.N|D\.C"
    r"|St|Ave|Blvd|Rd|Mt"
    r"|etc|vs|approx|i\.e|e\.g|cf|al"
    r"|No|Vol|Fig|Eq|Ref|Sec|Ch|App"
)

_ABBREVIATION_TAIL_RE = re.compile(rf"(?:{_ABBREVIATIONS})\.$", re.IGNORECASE)


class HybridChunker:
    """Multiple chunking strategies for research documents."""
    
    def __init__(self, chunk_size: int = 512, overlap: int = 50):
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.tokenizer = tiktoken.get_encoding("cl100k_base")
    
    # ------------------------------------------------------------------
    # Sentence splitting
    # ------------------------------------------------------------------

    def _split_sentences(self, text: str) -> List[str]:
        """Split text into sentences, preserving common abbreviation boundaries."""
        parts = re.split(r'(?<=[.!?])\s+(?=[A-Z\"\'\(\[0-9])', text)
        parts = [s.strip() for s in parts if s and s.strip()]
        if len(parts) <= 1:
            return parts

        merged: List[str] = [parts[0]]
        for part in parts[1:]:
            prev = merged[-1]
            prev_tail = prev.split()[-1] if prev.split() else ""
            is_abbrev = bool(_ABBREVIATION_TAIL_RE.search(prev_tail))
            is_single_initial = bool(re.search(r"^[A-Z]\.$", prev_tail))
            if is_abbrev or is_single_initial:
                merged[-1] = f"{prev} {part}"
            else:
                merged.append(part)
        return merged
    
    # ------------------------------------------------------------------
    # Paragraph chunking
    # ------------------------------------------------------------------

    def chunk_by_paragraphs(
        self,
        text: str,
        min_chunk_size: int = 100,
        max_chunk_size: Optional[int] = None
    ) -> List[str]:
        """Chunk by paragraphs, merging small ones.

        Overlap is the last complete sentence of the previous chunk
        rather than raw token slicing, preventing mid-word breaks.
        """
        # Respect runtime chunk size configuration unless caller overrides.
        max_chunk_size = max_chunk_size or self.chunk_size
        paragraphs = re.split(r'\n\s*\n|\r\n\s*\r\n', text)
        
        chunks: List[str] = []
        current_chunk: List[str] = []
        current_tokens = 0
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            
            para_tokens = len(self.tokenizer.encode(para))
            
            if para_tokens > max_chunk_size:
                if current_chunk:
                    chunks.append("\n\n".join(current_chunk))
                    current_chunk = []
                    current_tokens = 0
                sub_chunks = self._chunk_by_sentences(para, max_chunk_size)
                chunks.extend(sub_chunks)
                continue
            
            if current_tokens + para_tokens > max_chunk_size and current_tokens >= min_chunk_size:
                chunk_text = "\n\n".join(current_chunk)
                chunks.append(chunk_text)
                
                if self.overlap > 0:
                    overlap_text = self._last_sentence_overlap(chunk_text)
                    current_chunk = [overlap_text] if overlap_text else []
                    current_tokens = len(self.tokenizer.encode(overlap_text)) if overlap_text else 0
                else:
                    current_chunk = []
                    current_tokens = 0
            
            current_chunk.append(para)
            current_tokens += para_tokens
        
        if current_chunk:
            chunks.append("\n\n".join(current_chunk))
        
        return [c for c in chunks if len(c) >= min_chunk_size]
    
    def _last_sentence_overlap(self, text: str) -> str:
        """Return the last complete sentence as overlap context."""
        sentences = self._split_sentences(text)
        if not sentences:
            return ""
        last = sentences[-1].strip()
        tokens = len(self.tokenizer.encode(last))
        if tokens > self.overlap * 2:
            return ""
        return last
    
    def _chunk_by_sentences(self, text: str, max_tokens: int) -> List[str]:
        """Split text by sentences, respecting max token limit."""
        sentences = self._split_sentences(text)
        
        chunks: List[str] = []
        current: List[str] = []
        current_tokens = 0
        
        for sent in sentences:
            sent_tokens = len(self.tokenizer.encode(sent))
            
            if current_tokens + sent_tokens > max_tokens and current:
                chunks.append(" ".join(current))
                current = [sent]
                current_tokens = sent_tokens
            else:
                current.append(sent)
                current_tokens += sent_tokens
        
        if current:
            chunks.append(" ".join(current))
        
        return chunks
    
    # ------------------------------------------------------------------
    # Section chunking (preserves headers)
    # ------------------------------------------------------------------

    _HEADER_PATTERNS = [
        r'^#+\s+.+$',
        r'^(?:\d+\.)+\s+\w+',
        r'^(?:Chapter|Section|Part)\s+\d+',
        r'^(?:Abstract|Introduction|Methods|Results|Discussion|Conclusion|References)',
    ]
    # Use re.MULTILINE so ^/$ match per line; inline (?m) in alternation is invalid in Python re
    _HEADER_RE = re.compile(
        '|'.join(f'({p})' for p in _HEADER_PATTERNS),
        re.MULTILINE,
    )

    def chunk_by_sections(
        self,
        text: str,
        min_chunk_size: int = 100
    ) -> List[str]:
        """Chunk by section headers, prepending the header to every sub-chunk."""
        splits = re.split(
            '|'.join(f'^({p})' for p in self._HEADER_PATTERNS),
            text,
            flags=re.MULTILINE,
        )
        
        sections: List[Tuple[Optional[str], str]] = []
        current_header: Optional[str] = None
        
        for part in splits:
            if part is None:
                continue
            stripped = part.strip()
            if not stripped:
                continue
            
            if self._is_header(stripped):
                current_header = stripped
            else:
                sections.append((current_header, stripped))
        
        chunks: List[str] = []
        
        for header, body in sections:
            tokens = len(self.tokenizer.encode(body))
            prefix = f"{header}\n\n" if header else ""
            
            if tokens > self.chunk_size:
                sub_chunks = self.chunk_by_paragraphs(
                    body,
                    min_chunk_size=min_chunk_size,
                    max_chunk_size=self.chunk_size,
                )
                for sc in sub_chunks:
                    chunks.append(f"{prefix}{sc}" if prefix else sc)
            elif tokens > 0:
                chunks.append(f"{prefix}{body}" if prefix else body)
        
        return [c for c in chunks if len(self.tokenizer.encode(c)) >= min_chunk_size]
    
    def _is_header(self, text: str) -> bool:
        """Check whether text looks like a section header."""
        if len(text) > 120:
            return False
        return bool(self._HEADER_RE.match(text))
    
    # ------------------------------------------------------------------
    # Sliding window (fallback)
    # ------------------------------------------------------------------

    def chunk_sliding_window(
        self,
        text: str,
        chunk_size: Optional[int] = None,
        overlap: Optional[int] = None
    ) -> List[str]:
        """Standard sliding window chunking with token overlap."""
        chunk_size = max(1, chunk_size or self.chunk_size)
        overlap = self.overlap if overlap is None else max(0, overlap)
        overlap = min(overlap, chunk_size - 1)
        step = max(1, chunk_size - overlap)
        
        tokens = self.tokenizer.encode(text)
        
        if len(tokens) <= chunk_size:
            return [text]
        
        chunks: List[str] = []
        
        for i in range(0, len(tokens), step):
            chunk_tokens = tokens[i:i + chunk_size]
            chunk_text = self.tokenizer.decode(chunk_tokens)
            
            if chunk_text.strip():
                chunks.append(chunk_text.strip())
        
        return chunks
    
    # ------------------------------------------------------------------
    # Semantic chunking — splits on embedding-similarity breakpoints
    # ------------------------------------------------------------------

    def chunk_semantic(
        self,
        text: str,
        similarity_threshold: float = 0.5,
        min_chunk_sentences: int = 2,
    ) -> List[str]:
        """Split text at semantic boundaries detected via embedding cosine similarity.

        How it works:
        1. Split text into sentences.
        2. Embed each sentence with a lightweight model.
        3. Compute cosine similarity between consecutive sentence embeddings.
        4. Where similarity drops below the threshold, insert a chunk break.
        5. Merge very short chunks with neighbours.

        This avoids cutting mid-topic the way fixed-size chunking does.
        Falls back to paragraph chunking if embeddings are unavailable.
        """
        sentences = self._split_sentences(text)
        if len(sentences) <= min_chunk_sentences:
            return [text]

        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer("all-MiniLM-L6-v2")
            embeddings = model.encode(sentences, show_progress_bar=False, convert_to_numpy=True)
        except Exception:
            return self.chunk_by_paragraphs(text)

        # Cosine similarity between consecutive sentence embeddings
        similarities = []
        for i in range(len(embeddings) - 1):
            a, b = embeddings[i], embeddings[i + 1]
            cos_sim = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-10))
            similarities.append(cos_sim)

        # Find breakpoints where similarity drops below threshold
        breakpoints = [
            i + 1 for i, sim in enumerate(similarities)
            if sim < similarity_threshold
        ]

        # Build chunks from breakpoint indices
        chunks: List[str] = []
        prev = 0
        for bp in breakpoints:
            chunk_sents = sentences[prev:bp]
            if len(chunk_sents) >= min_chunk_sentences:
                chunks.append(" ".join(chunk_sents))
                prev = bp
        # Remaining sentences
        if prev < len(sentences):
            remaining = " ".join(sentences[prev:])
            if chunks and len(sentences[prev:]) < min_chunk_sentences:
                chunks[-1] += " " + remaining
            else:
                chunks.append(remaining)

        # Enforce max token limit per chunk
        final: List[str] = []
        for chunk in chunks:
            tokens = len(self.tokenizer.encode(chunk))
            if tokens > self.chunk_size * 2:
                final.extend(self._chunk_by_sentences(chunk, self.chunk_size))
            else:
                final.append(chunk)

        return [c for c in final if c.strip()]

    # ------------------------------------------------------------------
    # Smart chunking (auto-detect + return strategy name)
    # ------------------------------------------------------------------

    def smart_chunk(
        self,
        text: str,
        strategy: str = "auto"
    ) -> Tuple[List[str], str]:
        """Auto-detect document structure and chunk accordingly.

        Returns (chunks, strategy_name) so callers can record which
        method was used.
        """
        if strategy == "auto":
            has_headers = bool(re.search(r'^#+\s+|^\d+\.\s+\w+', text, re.M))
            has_paragraphs = '\n\n' in text
            
            if has_headers:
                strategy = "sections"
            elif has_paragraphs:
                strategy = "paragraphs"
            else:
                strategy = "sliding"
        
        if strategy == "semantic":
            return self.chunk_semantic(text), "semantic"
        elif strategy == "sections":
            return self.chunk_by_sections(text), "sections"
        elif strategy == "paragraphs":
            return self.chunk_by_paragraphs(text), "paragraphs"
        else:
            return self.chunk_sliding_window(text), "sliding"
    
    # ------------------------------------------------------------------
    # Metadata helpers
    # ------------------------------------------------------------------

    @staticmethod
    def extract_section_title(chunk_text: str) -> Optional[str]:
        """Extract the section title from a chunk if it starts with one."""
        first_line = chunk_text.split('\n', 1)[0].strip()
        if re.match(r'^#+\s+', first_line):
            return re.sub(r'^#+\s+', '', first_line)
        if re.match(r'^(?:\d+\.)+\s+\w+', first_line) and len(first_line) < 120:
            return first_line
        if re.match(
            r'^(?:Abstract|Introduction|Methods|Results|Discussion|Conclusion|References)',
            first_line,
        ):
            return first_line
        return None
