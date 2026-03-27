/**
 * Memory Panel – retains and lists previous conversations.
 * Header shows documents discussed; click loads conversation into Chat.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { Database, MessageSquare, FileText, Loader2, Trash2 } from 'lucide-react';
import { Conversation, DocumentSummary } from '../types';
import { getConversations, deleteConversation } from '../services/api';

interface MemoryPanelProps {
  documents: DocumentSummary[];
  selectedDocument: DocumentSummary | null;
  onSelectConversation: (conversationId: string, messages: import('../types').Message[]) => void;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const diff = now.getTime() - d.getTime();
  if (diff < 86400000) {
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }
  if (diff < 604800000) {
    return d.toLocaleDateString([], { weekday: 'short' });
  }
  return d.toLocaleDateString([], { month: 'short', day: 'numeric', year: d.getFullYear() !== now.getFullYear() ? 'numeric' : undefined });
}

export const MemoryPanel: React.FC<MemoryPanelProps> = ({
  documents,
  selectedDocument,
  onSelectConversation,
}) => {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const mountedRef = React.useRef(true);

  React.useEffect(() => {
    return () => { mountedRef.current = false; };
  }, []);

  const loadConversations = useCallback(async () => {
    setLoading(true);
    try {
      const list = await getConversations(selectedDocument?.id);
      if (mountedRef.current) setConversations(list);
    } catch (err) {
      console.error('Failed to load conversations:', err);
      if (mountedRef.current) setConversations([]);
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, [selectedDocument?.id]);

  useEffect(() => {
    loadConversations();
  }, [loadConversations]);

  const getDocumentName = (documentId: string | null): string => {
    if (!documentId) return 'All Documents';
    const doc = documents.find(d => d.id === documentId);
    return doc?.original_name ?? 'Unknown document';
  };

  const handleSelect = (conv: Conversation) => {
    onSelectConversation(conv.id, conv.messages);
  };

  const handleDelete = async (e: React.MouseEvent, conv: Conversation) => {
    e.stopPropagation();
    if (!confirm('Delete this conversation?')) return;
    setDeletingId(conv.id);
    try {
      await deleteConversation(conv.id);
      setConversations(prev => prev.filter(c => c.id !== conv.id));
    } catch (err) {
      console.error('Failed to delete conversation:', err);
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="h-full flex flex-col bg-surface">
      <div className="p-4 border-b border-slate-200">
        <h2 className="text-lg font-semibold text-ink flex items-center gap-2">
          <Database className="w-5 h-5 text-accent" />
          Memory
        </h2>
        <p className="text-xs text-ink-muted mt-1">
          {selectedDocument
            ? `Conversations about "${selectedDocument.original_name}"`
            : 'All conversations'}
        </p>
      </div>

      <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-8 h-8 text-accent animate-spin" />
          </div>
        ) : conversations.length === 0 ? (
          <div className="text-center py-12">
            <MessageSquare className="w-12 h-12 text-ink-subtle mx-auto mb-3" />
            <p className="text-ink-muted text-sm">No conversations yet</p>
          </div>
        ) : (
          <ul className="space-y-2">
            {conversations.map((conv) => {
              const firstUser = conv.messages.find(m => m.role === 'user');
              const preview = firstUser?.content?.slice(0, 80) ?? 'No messages';
              return (
                <li key={conv.id}>
                  <button
                    type="button"
                    onClick={() => handleSelect(conv)}
                    className="w-full text-left p-4 rounded-xl bg-surface-card border border-slate-200 hover:border-accent/30 hover:bg-slate-50 transition-all group"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        <FileText className="w-4 h-4 text-accent shrink-0" />
                        <span className="text-sm font-medium text-ink truncate">
                          {getDocumentName(conv.document_id)}
                        </span>
                      </div>
                      <button
                        type="button"
                        onClick={(e) => handleDelete(e, conv)}
                        disabled={deletingId === conv.id}
                        className="opacity-0 group-hover:opacity-100 p-1.5 text-ink-muted hover:text-red-600 rounded transition-all"
                      >
                        {deletingId === conv.id ? (
                          <Loader2 className="w-4 h-4 animate-spin" />
                        ) : (
                          <Trash2 className="w-4 h-4" />
                        )}
                      </button>
                    </div>
                    <p className="text-xs text-ink-muted mt-1 truncate">{preview}{preview.length >= 80 ? '…' : ''}</p>
                    <p className="text-xs text-ink-muted mt-0.5">{formatDate(conv.updated_at)}</p>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
};

export default MemoryPanel;
