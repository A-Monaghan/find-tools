import React from 'react';
import { ExternalLink } from 'lucide-react';

interface EntityExtractorAboutProps {
  systemPrompt: string;
  setSystemPrompt: (prompt: string) => void;
  userPromptTemplate: string;
  setUserPromptTemplate: (template: string) => void;
  fallbackSystemPrompt: string;
  fallbackUserTemplate: string;
}

const EntityExtractorAbout: React.FC<EntityExtractorAboutProps> = ({
  systemPrompt,
  setSystemPrompt,
  userPromptTemplate,
  setUserPromptTemplate,
  fallbackSystemPrompt,
  fallbackUserTemplate,
}) => {
  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-2xl font-bold text-slate-100 mb-2">About Entity Extractor</h2>
        <p className="text-slate-400 text-sm leading-relaxed">
          Extracts <strong className="text-slate-200">entities</strong> (people, organisations, locations, concepts)
          and <strong className="text-slate-200">relationships</strong> from text or a webpage URL. Uses the OOCP
          backend with OpenRouter; fetches page content (if URL), sends to the LLM, parses JSON, and returns
          entities/relationships. Export CSV for Neo4j knowledge graphs.
        </p>
      </div>

      <div>
        <h3 className="text-lg font-semibold text-slate-200 mb-3">How it works</h3>
        <ol className="list-decimal list-inside space-y-2 text-slate-400 text-sm">
          <li>Enter a URL or paste text into the input field.</li>
          <li>Backend fetches and extracts text from URLs (newspaper3k, trafilatura, BeautifulSoup).</li>
          <li>Extracted text is sent to the LLM with your custom prompts.</li>
          <li>LLM returns JSON with entities and relationships.</li>
          <li>Results displayed in tables; export as Neo4j-compatible CSV.</li>
        </ol>
      </div>

      <div>
        <h3 className="text-lg font-semibold text-slate-200 mb-3">OpenRouter</h3>
        <p className="text-slate-400 text-sm mb-4">
          Uses OpenRouter to access LLM providers (Anthropic, OpenAI, Meta, etc.) with a single API key.
        </p>
        <div className="flex flex-wrap gap-3">
          <a
            href="https://openrouter.ai"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 px-4 py-2.5 bg-slate-800 border border-white/10 rounded-xl text-slate-200 hover:bg-slate-700 text-sm font-medium"
          >
            OpenRouter <ExternalLink className="w-3.5 h-3.5 text-orange-400" />
          </a>
        </div>
      </div>

      <div>
        <h3 className="text-lg font-semibold text-slate-200 mb-2">System Prompt</h3>
        <p className="text-slate-500 text-xs mb-2">Sets the LLM role and behaviour for entity extraction.</p>
        <textarea
          value={systemPrompt}
          onChange={(e) => setSystemPrompt(e.target.value)}
          rows={4}
          className="w-full px-4 py-3 bg-slate-900 border border-white/10 rounded-xl text-slate-200 text-sm font-mono resize-y focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
          placeholder="System prompt..."
          spellCheck={false}
        />
        <button
          type="button"
          onClick={() => setSystemPrompt(fallbackSystemPrompt)}
          className="mt-2 text-xs font-medium text-slate-400 hover:text-indigo-400 transition-colors"
        >
          Reset to default
        </button>
      </div>

      <div>
        <h3 className="text-lg font-semibold text-slate-200 mb-2">User Prompt Template</h3>
        <p className="text-slate-500 text-xs mb-2">
          Use <code className="bg-slate-800 px-1 rounded text-indigo-300">__TEXT_TO_ANALYZE__</code> where content
          is inserted.
        </p>
        <textarea
          value={userPromptTemplate}
          onChange={(e) => setUserPromptTemplate(e.target.value)}
          rows={12}
          className="w-full px-4 py-3 bg-slate-900 border border-white/10 rounded-xl text-slate-200 text-sm font-mono resize-y focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
          placeholder="User prompt template..."
          spellCheck={false}
        />
        <button
          type="button"
          onClick={() => setUserPromptTemplate(fallbackUserTemplate)}
          className="mt-2 text-xs font-medium text-slate-400 hover:text-indigo-400 transition-colors"
        >
          Reset to default
        </button>
      </div>
    </div>
  );
};

export default EntityExtractorAbout;
