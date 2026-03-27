"""
Source credibility scoring for OSINT.
Evaluates source reliability based on multiple factors.
"""

import re
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum


class SourceType(Enum):
    """Types of sources with inherent credibility weights."""
    ACADEMIC_PAPER = 0.9
    GOVERNMENT_DOC = 0.85
    NEWS_OUTLET = 0.7
    BLOG = 0.5
    SOCIAL_MEDIA = 0.3
    FORUM = 0.25
    UNKNOWN = 0.5


@dataclass
class CredibilityFactors:
    """Individual factors that contribute to credibility score."""
    source_type: float = 0.5
    has_author: float = 0.0
    has_date: float = 0.0
    has_citations: float = 0.0
    entity_richness: float = 0.0
    text_quality: float = 0.0
    domain_authority: float = 0.0


class CredibilityScorer:
    """
    Calculate source credibility scores (0-1).
    
    Factors considered:
    - Source type (academic, government, news, etc.)
    - Author presence and attribution
    - Publication date
    - Citations/references
    - Named entity richness
    - Text quality indicators
    - Domain authority (for web sources)
    """
    
    # Known credible domains
    CREDIBLE_DOMAINS = {
        "edu": 0.9,
        "gov": 0.9,
        "ac.uk": 0.85,
        "nih.gov": 0.9,
        "nasa.gov": 0.9,
        "nature.com": 0.85,
        "sciencedirect.com": 0.85,
        "arxiv.org": 0.8,
        "pubmed.gov": 0.85,
    }
    
    # Known low-credibility indicators
    SUSPICIOUS_PATTERNS = [
        r"clickbait",
        r"buy now",
        r"act now",
        r"limited time",
        r"miracle",
        r"shocking",
        r"you won't believe",
        r"lose weight fast",
    ]
    
    def __init__(self):
        self.suspicious_regex = re.compile(
            '|'.join(self.SUSPICIOUS_PATTERNS),
            re.IGNORECASE
        )
    
    def calculate_credibility(
        self,
        text: str,
        source_url: Optional[str] = None,
        source_type: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> Dict:
        """
        Calculate comprehensive credibility score.
        
        Returns:
            Dict with overall score and breakdown
        """
        metadata = metadata or {}
        
        factors = CredibilityFactors()
        
        # 1. Source type
        if source_type:
            factors.source_type = self._get_source_type_score(source_type)
        
        # 2. Domain authority (for web sources)
        if source_url:
            factors.domain_authority = self._score_domain(source_url)
        
        # 3. Author presence
        factors.has_author = 0.2 if metadata.get("author") else 0.0
        
        # 4. Date presence
        factors.has_date = 0.15 if metadata.get("date") else 0.0
        
        # 5. Citations/references
        factors.has_citations = self._score_citations(text)
        
        # 6. Entity richness
        factors.entity_richness = self._score_entity_richness(text)
        
        # 7. Text quality
        factors.text_quality = self._score_text_quality(text)
        
        # Calculate weighted total
        weights = {
            "source_type": 0.2,
            "domain_authority": 0.15,
            "has_author": 0.1,
            "has_date": 0.1,
            "has_citations": 0.15,
            "entity_richness": 0.1,
            "text_quality": 0.2,
        }
        
        total = sum(
            getattr(factors, key) * weight
            for key, weight in weights.items()
        )
        
        # Penalty for suspicious patterns
        penalty = self._detect_suspicious_patterns(text)
        
        score = max(0.0, min(1.0, total - penalty))
        
        return {
            "score": round(score, 2),
            "grade": self._score_to_grade(score),
            "factors": {
                "source_type": round(factors.source_type, 2),
                "domain_authority": round(factors.domain_authority, 2),
                "has_author": round(factors.has_author, 2),
                "has_date": round(factors.has_date, 2),
                "has_citations": round(factors.has_citations, 2),
                "entity_richness": round(factors.entity_richness, 2),
                "text_quality": round(factors.text_quality, 2),
            },
            "suspicious_penalty": penalty,
            "recommendation": self._get_recommendation(score)
        }
    
    def _get_source_type_score(self, source_type: str) -> float:
        """Get base score for source type."""
        type_scores = {
            "academic": SourceType.ACADEMIC_PAPER.value,
            "government": SourceType.GOVERNMENT_DOC.value,
            "news": SourceType.NEWS_OUTLET.value,
            "blog": SourceType.BLOG.value,
            "social": SourceType.SOCIAL_MEDIA.value,
            "forum": SourceType.FORUM.value,
            "pdf": 0.7,
            "docx": 0.6,
            "html": 0.5,
            "txt": 0.4,
        }
        return type_scores.get(source_type.lower(), SourceType.UNKNOWN.value)
    
    def _score_domain(self, url: str) -> float:
        """Score domain authority."""
        url = url.lower()
        
        for domain, score in self.CREDIBLE_DOMAINS.items():
            if domain in url:
                return score
        
        # Default moderate score for unknown domains
        return 0.5
    
    def _score_citations(self, text: str) -> float:
        """Score presence of citations/references."""
        # Look for reference patterns
        citation_patterns = [
            r'\[\d+\]',           # [1], [2]
            r'\(\w+,\s*\d{4}\)', # (Smith, 2020)
            r'References',
            r'Bibliography',
            r'Works Cited',
        ]
        
        matches = sum(1 for p in citation_patterns if re.search(p, text))
        
        if matches >= 3:
            return 0.15
        elif matches >= 1:
            return 0.1
        return 0.0
    
    def _score_entity_richness(self, text: str) -> float:
        """
        Score based on named entity density.
        Higher density often indicates factual, structured content.
        """
        # Common entity patterns
        entity_indicators = [
            r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b',  # Capitalized names
            r'\b\d{4}-\d{2}-\d{2}\b',                # Dates
            r'\b[A-Z]{2,}\b',                       # Acronyms
            r'\$\d+(?:,\d{3})*(?:\.\d{2})?',       # Money
            r'\b\d+(?:\.\d+)?%\b',                  # Percentages
        ]
        
        total_matches = sum(len(re.findall(p, text)) for p in entity_indicators)
        
        # Normalize by text length (per 1000 chars)
        density = (total_matches / len(text)) * 1000
        
        if density > 5:
            return 0.1
        elif density > 2:
            return 0.07
        elif density > 0.5:
            return 0.04
        return 0.0
    
    def _score_text_quality(self, text: str) -> float:
        """Score based on text quality indicators."""
        score = 0.0
        
        # Length check (too short = suspicious)
        if len(text) < 100:
            return 0.0
        elif len(text) > 500:
            score += 0.05
        
        # Has proper sentence structure
        sentences = re.split(r'[.!?]+', text)
        avg_sentence_length = sum(len(s.split()) for s in sentences) / max(len(sentences), 1)
        
        if 10 <= avg_sentence_length <= 30:
            score += 0.1
        
        # No excessive caps
        caps_ratio = sum(1 for c in text if c.isupper()) / max(len(text), 1)
        if 0.1 < caps_ratio < 0.4:
            score += 0.05
        
        return min(score, 0.2)
    
    def _detect_suspicious_patterns(self, text: str) -> float:
        """Detect suspicious patterns and return penalty."""
        matches = self.suspicious_regex.findall(text)
        
        if len(matches) >= 3:
            return 0.3
        elif len(matches) >= 1:
            return 0.15
        return 0.0
    
    def _score_to_grade(self, score: float) -> str:
        """Convert score to letter grade."""
        if score >= 0.8:
            return "A"
        elif score >= 0.7:
            return "B"
        elif score >= 0.6:
            return "C"
        elif score >= 0.4:
            return "D"
        return "F"
    
    def _get_recommendation(self, score: float) -> str:
        """Get recommendation based on score."""
        if score >= 0.8:
            return "Highly credible - suitable for research"
        elif score >= 0.6:
            return "Moderately credible - verify with additional sources"
        elif score >= 0.4:
            return "Low credibility - use with caution"
        return "Unreliable - recommend seeking alternative sources"
