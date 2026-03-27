/**
 * About — overview, API keys (single place), and architecture.
 */
import React from 'react';
import { BookOpen, Cpu, Network, GitBranch, Building2 } from 'lucide-react';
import { ApiKeysPanel } from './ApiKeysPanel';
import { PRODUCT_TITLE, PRODUCT_TAGLINE } from '../branding';

export const About: React.FC = () => {
  return (
    <div className="h-full overflow-y-auto bg-surface p-6 sm:p-10 custom-scrollbar">
      <div className="max-w-2xl mx-auto space-y-10">
        <div>
          <div className="flex items-center gap-3 mb-4">
            <div className="bg-accent p-2 rounded-xl shadow-sm">
              <BookOpen className="w-6 h-6 text-white" />
            </div>
            <h1 className="text-2xl font-bold text-ink">
              About {PRODUCT_TITLE}
            </h1>
          </div>
          <p className="text-ink-muted text-sm leading-relaxed">
            {PRODUCT_TAGLINE}. Document-grounded question-answering using Retrieval-Augmented Generation.
          </p>
        </div>

        <ApiKeysPanel />

        <div>
          <h2 className="text-lg font-semibold text-ink mb-3">Modules</h2>
          <div className="space-y-4">
            <div className="bg-surface-card border border-slate-200 rounded-xl p-4 shadow-sm">
              <h3 className="font-medium text-ink mb-1 flex items-center gap-2">
                <Cpu className="w-4 h-4 text-accent" />
                Chat
              </h3>
              <p className="text-sm text-ink-muted">
                Query documents with grounded, citation-based answers. Choose the LLM in the header; tune prompts under Chat → Settings.
              </p>
            </div>
            <div className="bg-surface-card border border-slate-200 rounded-xl p-4 shadow-sm">
              <h3 className="font-medium text-ink mb-1 flex items-center gap-2">
                <GitBranch className="w-4 h-4 text-accent" />
                Entity Extractor
              </h3>
              <p className="text-sm text-ink-muted">
                Extract entities from URLs or text; push to Neo4j or export CSV. Uses the same header model and API keys as above.
              </p>
            </div>
            <div className="bg-surface-card border border-slate-200 rounded-xl p-4 shadow-sm">
              <h3 className="font-medium text-ink mb-1 flex items-center gap-2">
                <Building2 className="w-4 h-4 text-accent" />
                Companies House
              </h3>
              <p className="text-sm text-ink-muted">
                Fetch filings, officers, and PSC data. Optional API key is set in this About page.
              </p>
            </div>
          </div>
        </div>

        <div>
          <h2 className="text-lg font-semibold text-ink mb-3">How RAG works</h2>
          <ol className="list-decimal list-inside space-y-2 text-ink-muted text-sm">
            <li>Upload PDF documents which are automatically processed and chunked.</li>
            <li>Text chunks are converted to vector embeddings for semantic search.</li>
            <li>When you ask a question, relevant chunks are retrieved using similarity search.</li>
            <li>Retrieved chunks are re-ranked to improve relevance.</li>
            <li>A language model generates answers based on the retrieved context.</li>
            <li>Answers include citations linking back to source documents and pages.</li>
          </ol>
        </div>

        <div>
          <h2 className="text-lg font-semibold text-ink mb-3 flex items-center gap-2">
            <Network className="w-5 h-5 text-accent" />
            LLM providers
          </h2>
          <div className="bg-surface-card border border-slate-200 rounded-xl p-4 space-y-3 shadow-sm">
            <div>
              <h3 className="font-medium text-ink mb-1">OpenRouter</h3>
              <p className="text-sm text-ink-muted">
                Access multiple cloud models from the header picker. Enter keys above and on the backend.
              </p>
            </div>
            <div>
              <h3 className="font-medium text-ink mb-1">OpenAI</h3>
              <p className="text-sm text-ink-muted">
                Direct OpenAI-compatible usage where supported. Same key fields as above.
              </p>
            </div>
          </div>
        </div>

        <div className="bg-accent-light border border-accent/20 rounded-xl p-4">
          <h2 className="text-lg font-semibold text-accent mb-2">Architecture</h2>
          <p className="text-sm text-ink-muted">
            Built with FastAPI backend, React frontend, PostgreSQL for metadata, and vector databases
            for semantic search. Supports hybrid operation modes for flexible deployment.
          </p>
        </div>
      </div>
    </div>
  );
};

export default About;
