import os
import json
import re
import requests
from typing import List, Dict, Any, Optional
from flask import Flask, request, jsonify, render_template, send_file
from flask_cors import CORS
import pandas as pd
from dotenv import load_dotenv
import openai
from bs4 import BeautifulSoup
import io

load_dotenv()

app = Flask(__name__)
CORS(app)

# Configuration
class Config:
    OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY', '')
    OPENROUTER_DEFAULT_MODEL = os.getenv('OPENROUTER_DEFAULT_MODEL', 'openai/gpt-4o-mini')

# Data models
class Entity:
    def __init__(self, id: str, name: str, label: str):
        self.id = id
        self.name = name
        self.label = label
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'label': self.label
        }

class Relationship:
    def __init__(self, id: str, source: str, target: str, type: str):
        self.id = id
        self.source = source
        self.target = target
        self.type = type
    
    def to_dict(self):
        return {
            'id': self.id,
            'source': self.source,
            'target': self.target,
            'type': self.type
        }

class RawEntity:
    def __init__(self, name: str, label: str):
        self.name = name
        self.label = label

class RawRelationship:
    def __init__(self, source: str, target: str, type: str):
        self.source = source
        self.target = target
        self.type = type

# LLM Service Classes
class LLMService:
    def __init__(self, api_key: str = None, openrouter_model: str = None):
        self.api_key = api_key or Config.OPENROUTER_API_KEY
        self.openrouter_model = openrouter_model or Config.OPENROUTER_DEFAULT_MODEL
    
    def extract_text_from_url(self, url: str) -> str:
        """Extract main text content from a URL using parallel extraction and intelligent merging"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
            
            # Prefer bypassing env proxy settings, but fall back for managed SSL/cert setups.
            try:
                with requests.Session() as session:
                    session.trust_env = False
                    response = session.get(url, headers=headers, timeout=15)
            except requests.exceptions.SSLError:
                # Last-resort fallback for environments missing local CA bundles.
                response = requests.get(url, headers=headers, timeout=15, verify=False)
            response.raise_for_status()
            
            if response.encoding == 'ISO-8859-1':
                response.encoding = response.apparent_encoding
            
            html_content = response.content
            
            # --- PARALLEL EXTRACTION ---
            extraction_results = {}
            
            # 1. Try newspaper3k
            try:
                import newspaper
                article = newspaper.Article(url)
                article.download()
                article.parse()
                if article.text and len(article.text.strip()) > 50:
                    extraction_results['newspaper3k'] = self._clean_text(article.text)
            except Exception as e:
                print(f"Newspaper3k extraction failed: {e}")
            
            # 2. Try trafilatura
            try:
                import trafilatura
                extracted = trafilatura.extract(html_content, include_comments=False, include_tables=False)
                if extracted and len(extracted.strip()) > 50:
                    extraction_results['trafilatura'] = self._clean_text(extracted)
            except Exception as e:
                print(f"Trafilatura extraction failed: {e}")
            
            # 3. Try BeautifulSoup paragraph combination
            try:
                soup = BeautifulSoup(html_content, 'html.parser')
                
                # Remove unwanted elements
                unwanted_tags = [
                    'script', 'style', 'noscript', 'iframe', 'embed', 'object', 'applet',
                    'form', 'button', 'input', 'select', 'textarea', 'meta', 'link', 'title', 'head'
                ]
                for tag in unwanted_tags:
                    for element in soup.find_all(tag):
                        element.decompose()

                # Combine all <p> tags in reading order
                paragraphs = []
                for p in soup.find_all('p'):
                    text = p.get_text(separator=' ', strip=True)
                    if len(text) > 30 and not any(
                        kw in text.lower() for kw in [
                            'cookie', 'privacy', 'terms', 'navigation', 'menu', 'subscribe', 'sign up', 'login', 
                            'advertisement', 'ad', 'footer', 'header', 'copyright', 'all rights reserved', 
                            'share', 'comment', 'related', 'recommended', 'popular', 'trending', 'newsletter', 
                            'disclaimer', 'contact', 'home', 'about']
                    ):
                        paragraphs.append(text)
                
                # Add <div> and <section> blocks with enough text
                for tag in soup.find_all(['div', 'section']):
                    text = tag.get_text(separator=' ', strip=True)
                    if len(text) > 100 and not any(
                        kw in text.lower() for kw in [
                            'cookie', 'privacy', 'terms', 'navigation', 'menu', 'subscribe', 'sign up', 'login', 
                            'advertisement', 'ad', 'footer', 'header', 'copyright', 'all rights reserved', 
                            'share', 'comment', 'related', 'recommended', 'popular', 'trending', 'newsletter', 
                            'disclaimer', 'contact', 'home', 'about']
                    ):
                        paragraphs.append(text)
                
                combined_text = '\n'.join(paragraphs)
                if len(combined_text.strip()) > 50:
                    extraction_results['beautifulsoup'] = self._clean_text(combined_text)
            except Exception as e:
                print(f"BeautifulSoup extraction failed: {e}")
            
            # --- INTELLIGENT MERGING ---
            if not extraction_results:
                raise Exception("All extraction methods failed")
            
            # If we have multiple results, merge them intelligently
            if len(extraction_results) > 1:
                return self._merge_extraction_results(extraction_results)
            else:
                # Return the single result
                return list(extraction_results.values())[0]
            
        except Exception as e:
            raise Exception(f"Failed to extract content from URL: {str(e)}")
    
    def _merge_extraction_results(self, results: dict) -> str:
        """Intelligently merge multiple extraction results"""
        # Sort by length (longer is usually better)
        sorted_results = sorted(results.items(), key=lambda x: len(x[1]), reverse=True)
        
        # Use the longest result as base
        base_text = sorted_results[0][1]
        base_method = sorted_results[0][0]
        
        print(f"Using {base_method} as base (length: {len(base_text)})")
        
        # For each other result, find differences and evaluate if they're relevant
        merged_text = base_text
        
        for method, text in sorted_results[1:]:
            print(f"Analyzing differences from {method} (length: {len(text)})")
            
            # Find text that's in the other result but not in base
            differences = self._find_text_differences(base_text, text)
            
            if differences:
                # Evaluate if differences are relevant
                relevant_differences = self._evaluate_differences(differences, base_text)
                
                if relevant_differences:
                    print(f"Adding {len(relevant_differences)} relevant text blocks from {method}")
                    # Insert relevant differences at appropriate positions
                    merged_text = self._insert_relevant_text(merged_text, relevant_differences)
                else:
                    print(f"No relevant differences found in {method}")
        
        return merged_text
    
    def _find_text_differences(self, base_text: str, other_text: str) -> list:
        """Find text blocks that are in other_text but not in base_text"""
        # Split into sentences for comparison
        import re
        
        def split_into_sentences(text):
            # Simple sentence splitting
            sentences = re.split(r'[.!?]+', text)
            return [s.strip() for s in sentences if len(s.strip()) > 20]
        
        base_sentences = set(split_into_sentences(base_text))
        other_sentences = set(split_into_sentences(other_text))
        
        # Find sentences that are only in other_text
        unique_sentences = other_sentences - base_sentences
        
        # Group consecutive sentences
        other_sentences_list = split_into_sentences(other_text)
        differences = []
        current_block = []
        
        for sentence in other_sentences_list:
            if sentence in unique_sentences:
                current_block.append(sentence)
            else:
                if current_block:
                    differences.append(' '.join(current_block))
                    current_block = []
        
        if current_block:
            differences.append(' '.join(current_block))
        
        return differences
    
    def _evaluate_differences(self, differences: list, base_text: str) -> list:
        """Evaluate if differences are relevant content"""
        relevant_differences = []
        
        # Keywords that suggest relevant content
        relevant_keywords = [
            'research', 'study', 'analysis', 'report', 'findings', 'conclusion', 'method', 'result',
            'data', 'evidence', 'example', 'case', 'scenario', 'situation', 'context', 'background',
            'history', 'development', 'process', 'procedure', 'technique', 'approach', 'strategy',
            'solution', 'recommendation', 'suggestion', 'advice', 'guidance', 'instruction', 'tutorial',
            'explanation', 'description', 'definition', 'concept', 'theory', 'principle', 'rule',
            'feature', 'function', 'capability', 'advantage', 'benefit', 'advantage', 'disadvantage',
            'limitation', 'challenge', 'problem', 'issue', 'concern', 'consideration', 'factor',
            'element', 'component', 'part', 'section', 'chapter', 'topic', 'subject', 'theme'
        ]
        
        # Keywords that suggest irrelevant content
        irrelevant_keywords = [
            'cookie', 'privacy', 'terms', 'navigation', 'menu', 'subscribe', 'sign up', 'login',
            'advertisement', 'ad', 'footer', 'header', 'copyright', 'all rights reserved',
            'share', 'comment', 'related', 'recommended', 'popular', 'trending', 'newsletter',
            'disclaimer', 'contact', 'home', 'about', 'search', 'filter', 'sort', 'browse',
            'previous', 'next', 'back', 'forward', 'close', 'open', 'download', 'upload',
            'print', 'email', 'bookmark', 'favorite', 'like', 'follow', 'subscribe'
        ]
        
        for diff in differences:
            diff_lower = diff.lower()
            
            # Check for relevant keywords
            relevant_score = sum(1 for kw in relevant_keywords if kw in diff_lower)
            
            # Check for irrelevant keywords
            irrelevant_score = sum(1 for kw in irrelevant_keywords if kw in diff_lower)
            
            # Length consideration (longer text is more likely to be relevant)
            length_score = min(len(diff) / 100, 3)  # Cap at 3 points
            
            # Calculate overall score
            score = relevant_score + length_score - irrelevant_score
            
            # Consider it relevant if score is positive and text is substantial
            if score > 0 and len(diff.strip()) > 50:
                relevant_differences.append(diff)
        
        return relevant_differences
    
    def _insert_relevant_text(self, base_text: str, relevant_differences: list) -> str:
        """Insert relevant differences into the base text at appropriate positions"""
        # For now, append the differences at the end
        # In a more sophisticated version, we could try to insert them at semantically appropriate positions
        
        if relevant_differences:
            additional_text = '\n\n'.join(relevant_differences)
            return base_text + '\n\n' + additional_text
        
        return base_text
    
    def _clean_text(self, text: str) -> str:
        """Clean and normalize extracted text"""
        if not text:
            return ""
        
        # Clean up the text
        lines = []
        for line in text.split('\n'):
            line = line.strip()
            if line and len(line) > 5:  # Less aggressive line filtering
                lines.append(line)
        
        # Join lines and clean up whitespace
        text = ' '.join(lines)
        text = re.sub(r'\s+', ' ', text)  # Replace multiple spaces with single space
        text = text.strip()
        
        # Less aggressive character cleaning - keep more punctuation and symbols
        # Only remove truly problematic characters
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)  # Remove control characters
        text = re.sub(r'\s+', ' ', text)  # Clean up whitespace again
        
        return text
    
    def extract_graph_data(self, text: str) -> Dict[str, List]:
        """Extract entities and relationships from text using OpenRouter"""
        return self._extract_with_openrouter(text)
    
    def _extract_with_openrouter(self, text: str) -> Dict[str, List]:
        """Extract using OpenRouter (OpenAI-compatible API)"""
        if not self.api_key:
            raise Exception("OpenRouter API key is required")
        prompt = f"""Analyze the following text and extract entities and their relationships.

Text to analyze:
{text[:8000]}

Return a JSON object with the following structure:
{{
    "entities": [
        {{"name": "Entity Name", "label": "Entity Type (Person, Company, Location, etc.)"}}
    ],
    "relationships": [
        {{"source": "Source Entity Name", "target": "Target Entity Name", "type": "RELATIONSHIP_TYPE"}}
    ]
}}

Rules:
- Entities should be people, organizations, locations, addresses, concepts, events or significant items
- Assign concise, descriptive labels for each entity
- Relationships should describe how two entities are connected
- Use UPPERCASE_SNAKE_CASE for relationship types
- Source and target must exactly match entity names
- Return only valid JSON, no additional text"""

        try:
            client = openai.OpenAI(
                api_key=self.api_key,
                base_url="https://openrouter.ai/api/v1",
            )
            response = client.chat.completions.create(
                model=self.openrouter_model,
                messages=[
                    {"role": "system", "content": "You are an expert data analyst and corporate intelligence specialist, specializing in knowledge graph extraction. Return only valid JSON responses."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=2000,
            )
            response_text = response.choices[0].message.content.strip()
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            json_str = json_match.group() if json_match else response_text
            json_str = self._fix_json_issues(json_str)
            data = json.loads(json_str)
            return {
                'entities': data.get('entities', []),
                'relationships': data.get('relationships', [])
            }
        except json.JSONDecodeError:
            manual_result = self._extract_manual_from_response(response_text)
            if manual_result:
                return manual_result
            raise Exception("Failed to parse OpenRouter response")
        except Exception as e:
            raise Exception(f"OpenRouter extraction failed: {str(e)}")
    
    def _fix_json_issues(self, json_str: str) -> str:
        """Fix common JSON formatting issues"""
        # Remove trailing commas in arrays and objects
        json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
        
        # Fix missing quotes around property names
        json_str = re.sub(r'(\s*)(\w+)(\s*):', r'\1"\2"\3:', json_str)
        
        # Fix single quotes to double quotes
        json_str = json_str.replace("'", '"')
        
        # Remove any control characters
        json_str = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', json_str)
        
        return json_str
    
    def _extract_manual_from_response(self, response_text: str) -> Dict[str, List]:
        """Manually extract entities and relationships from response text when JSON parsing fails"""
        entities = []
        relationships = []
        
        # Look for entity patterns
        entity_patterns = [
            r'"name":\s*"([^"]+)"[^}]*"label":\s*"([^"]+)"',
            r'name["\s]*:["\s]*([^",\n]+)["\s,]*label["\s]*:["\s]*([^",\n]+)',
            r'Entity:\s*([^,\n]+)[^,\n]*Type:\s*([^,\n]+)',
        ]
        
        for pattern in entity_patterns:
            matches = re.findall(pattern, response_text, re.IGNORECASE)
            for match in matches:
                if len(match) >= 2:
                    entities.append({
                        'name': match[0].strip(),
                        'label': match[1].strip()
                    })
        
        # Look for relationship patterns
        rel_patterns = [
            r'"source":\s*"([^"]+)"[^}]*"target":\s*"([^"]+)"[^}]*"type":\s*"([^"]+)"',
            r'source["\s]*:["\s]*([^",\n]+)["\s,]*target["\s]*:["\s]*([^",\n]+)["\s,]*type["\s]*:["\s]*([^",\n]+)',
            r'([^,\n]+)\s*->\s*([^,\n]+)\s*:\s*([^,\n]+)',
        ]
        
        for pattern in rel_patterns:
            matches = re.findall(pattern, response_text, re.IGNORECASE)
            for match in matches:
                if len(match) >= 3:
                    relationships.append({
                        'source': match[0].strip(),
                        'target': match[1].strip(),
                        'type': match[2].strip().upper().replace(' ', '_')
                    })
        
        if entities or relationships:
            print(f"Manual extraction found {len(entities)} entities and {len(relationships)} relationships")
            return {
                'entities': entities,
                'relationships': relationships
            }
        
        return None

# Utility functions
def normalize_id(name: str) -> str:
    """Normalize entity name to ID format"""
    return re.sub(r'\s+', '_', name.lower())

def process_graph_results(raw_data: Dict[str, List]) -> Dict[str, List]:
    """Process raw graph data and normalize IDs"""
    entity_map = {}
    entities = []
    relationships = []
    
    # Process entities
    for raw_entity in raw_data.get('entities', []):
        entity_id = normalize_id(raw_entity['name'])
        if entity_id not in entity_map:
            entity = Entity(entity_id, raw_entity['name'], raw_entity['label'])
            entity_map[entity_id] = entity
            entities.append(entity)
    
    # Process relationships
    relationship_map = {}
    for raw_rel in raw_data.get('relationships', []):
        source_id = normalize_id(raw_rel['source'])
        target_id = normalize_id(raw_rel['target'])
        
        if source_id in entity_map and target_id in entity_map:
            rel_id = f"{source_id}_{normalize_id(raw_rel['type'])}_{target_id}"
            if rel_id not in relationship_map:
                relationship = Relationship(
                    rel_id, source_id, target_id, 
                    raw_rel['type'].upper().replace(' ', '_')
                )
                relationship_map[rel_id] = relationship
                relationships.append(relationship)
    
    return {
        'entities': [e.to_dict() for e in entities],
        'relationships': [r.to_dict() for r in relationships]
    }

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/analyze', methods=['POST'])
def analyze():
    try:
        data = request.get_json()
        
        # Validate input
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        api_key = data.get('api_key') or Config.OPENROUTER_API_KEY
        openrouter_model = data.get('openrouter_model') or Config.OPENROUTER_DEFAULT_MODEL
        url = data.get('url', '').strip()
        text = data.get('text', '').strip()
        input_mode = data.get('input_mode', 'text')
        
        if not api_key or api_key == 'your_openrouter_api_key_here':
            return jsonify({'error': 'OpenRouter API key is required'}), 400
        
        llm_service = LLMService(api_key=api_key, openrouter_model=openrouter_model)
        
        # Get content to analyze
        if input_mode == 'url':
            if not url or not re.match(r'^https?://', url):
                return jsonify({'error': 'Please enter a valid URL'}), 400
            
            try:
                content_to_process = llm_service.extract_text_from_url(url)
            except Exception as e:
                return jsonify({'error': str(e)}), 400
        else:
            if not text.strip():
                return jsonify({'error': 'Please enter text to analyze'}), 400
            content_to_process = text
        
        # Extract graph data
        try:
            raw_graph_data = llm_service.extract_graph_data(content_to_process)
            processed_data = process_graph_results(raw_graph_data)
            
            return jsonify({
                'success': True,
                'data': processed_data,
                'extracted_text': content_to_process if input_mode == 'url' else None
            })
            
        except Exception as e:
            return jsonify({'error': str(e)}), 500
            
    except Exception as e:
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/api/download/<file_type>', methods=['POST'])
def download_csv(file_type):
    try:
        data = request.get_json()
        
        if file_type == 'entities':
            entities = data.get('entities', [])
            df = pd.DataFrame(entities)
            df = df[['id', 'name', 'label']]
            df.columns = ['entityId:ID', 'name', ':LABEL']
            
        elif file_type == 'relationships':
            relationships = data.get('relationships', [])
            df = pd.DataFrame(relationships)
            df = df[['source', 'target', 'type']]
            df.columns = [':START_ID', ':END_ID', ':TYPE']
            
        else:
            return jsonify({'error': 'Invalid file type'}), 400
        
        # Create CSV in memory
        output = io.StringIO()
        df.to_csv(output, index=False)
        output.seek(0)
        
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'{file_type}.csv'
        )
        
    except Exception as e:
        return jsonify({'error': f'Download error: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000) 