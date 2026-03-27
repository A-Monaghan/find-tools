/**
 * Tools page - overview of available tools in the system.
 */
import React from 'react';
import { MessageSquare, BookOpen, Network, Database, Wrench, ArrowRight } from 'lucide-react';

interface ToolCard {
  id: string;
  name: string;
  description: string;
  icon: React.ReactNode;
  tab?: string;
  onSelect?: () => void;
}

type TabId = 'chat' | 'memory' | 'entity-extractor' | 'about' | 'tools';

interface ToolsPageProps {
  onSelectTab?: (tab: TabId) => void;
}

export const ToolsPage: React.FC<ToolsPageProps> = ({ onSelectTab }) => {
  const tools: ToolCard[] = [
    {
      id: 'chat',
      name: 'RAG Chat',
      description:
        'Query your uploaded documents with grounded, citation-based answers. Supports fusion retrieval, HyDE, and corrective RAG.',
      icon: <MessageSquare className="w-6 h-6 text-indigo-400" />,
      tab: 'chat',
    },
    {
      id: 'documents',
      name: 'Document Library',
      description:
        'Upload PDFs, DOCX, and other formats. Documents are chunked, embedded, and indexed for semantic search.',
      icon: <BookOpen className="w-6 h-6 text-indigo-400" />,
      tab: 'chat',
    },
    {
      id: 'entity-extractor',
      name: 'Entity Extractor',
      description:
        'Extract entities and relationships from URLs or text. Push directly to Neo4j or export CSV for knowledge graphs.',
      icon: <Network className="w-6 h-6 text-orange-400" />,
      tab: 'entity-extractor',
    },
    {
      id: 'memory',
      name: 'Conversation Memory',
      description:
        'Browse and resume past conversations. View query history and audit logs.',
      icon: <Database className="w-6 h-6 text-emerald-400" />,
      tab: 'memory',
    },
  ];

  return (
    <div className="h-full overflow-y-auto p-6 sm:p-10 custom-scrollbar">
      <div className="max-w-3xl mx-auto">
        <div className="flex items-center gap-3 mb-8">
          <div className="p-3 rounded-xl bg-slate-800/50 border border-white/10">
            <Wrench className="w-8 h-8 text-slate-400" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-slate-100">Tools</h1>
            <p className="text-slate-400 text-sm">
              Available tools and capabilities in this system
            </p>
          </div>
        </div>

        <div className="grid gap-4">
          {tools.map((tool) => (
            <div
              key={tool.id}
              className="p-5 rounded-xl bg-slate-900/80 border border-white/10 hover:border-white/20 transition-colors group"
            >
              <div className="flex items-start gap-4">
                <div className="p-2.5 rounded-xl bg-slate-800/50 border border-white/5 shrink-0">
                  {tool.icon}
                </div>
                <div className="flex-1 min-w-0">
                  <h2 className="text-lg font-semibold text-slate-100 mb-1">
                    {tool.name}
                  </h2>
                  <p className="text-slate-400 text-sm leading-relaxed">
                    {tool.description}
                  </p>
                  {tool.tab && onSelectTab && (
                    <button
                      onClick={() => onSelectTab(tool.tab as TabId)}
                      className="mt-3 inline-flex items-center gap-2 text-sm font-medium text-indigo-400 hover:text-indigo-300 transition-colors"
                    >
                      Open <ArrowRight className="w-4 h-4" />
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>

        <div className="mt-10 p-4 rounded-xl bg-slate-900/50 border border-white/5">
          <h3 className="text-sm font-semibold text-slate-300 mb-2">
            Quick start
          </h3>
          <p className="text-slate-500 text-sm">
            Upload documents in the sidebar, then use Chat to query them. Use
            Entity Extractor for URL/text analysis and knowledge graph export.
            Memory stores your conversation history.
          </p>
        </div>
      </div>
    </div>
  );
};
