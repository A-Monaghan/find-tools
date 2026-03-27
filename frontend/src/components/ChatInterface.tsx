/**
 * Chat Interface Component
 *
 * Inspired by Quivr's chat design.
 * Displays messages with markdown support and citation highlights.
 */

import React, { useState, useRef, useEffect, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import { Send, Loader2, Quote, Sparkles } from 'lucide-react';
import { DocumentSummary, Message, QueryRequest, Citation, RetrievedChunk, RetrievalTrace } from '../types';
import { queryDocuments } from '../services/api';
import { clearDraftValue, loadDraftValue, saveDraftValue } from '../utils/draftState';
import { PRODUCT_TITLE, PRODUCT_TAGLINE } from '../branding';

const REQUEST_TIMEOUT_MS = 300_000;
const CHAT_DRAFT_KEY = 'rag_v2_draft_chat_input';

interface ChatInterfaceProps {
  selectedDocument: DocumentSummary | null;
  conversationId: string | null;
  loadedMessages?: Message[] | null;
  onConversationCreated: (id: string) => void;
  onShowCitations: (
    citations: Citation[],
    chunks: RetrievedChunk[],
    retrievalTrace?: RetrievalTrace | null
  ) => void;
  selectedModel: string;
  /** Role / standards — prepended to the RAG template */
  researcherProfile: string;
  customPrompt: string;
}

export const ChatInterface: React.FC<ChatInterfaceProps> = ({
  selectedDocument,
  conversationId,
  loadedMessages,
  onConversationCreated,
  onShowCitations,
  selectedModel,
  researcherProfile,
  customPrompt,
}) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState(() => loadDraftValue(CHAT_DRAFT_KEY));
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const appliedLoadedRef = useRef<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Reset messages when document changes
  useEffect(() => {
    setMessages([]);
    appliedLoadedRef.current = null;
  }, [selectedDocument?.id]);

  // Apply loaded conversation from Memory (once per conversationId)
  useEffect(() => {
    if (
      loadedMessages?.length &&
      conversationId &&
      appliedLoadedRef.current !== conversationId
    ) {
      setMessages(loadedMessages);
      appliedLoadedRef.current = conversationId;
    }
    if (!conversationId) appliedLoadedRef.current = null;
  }, [conversationId, loadedMessages]);

  // Cancel in-flight request on unmount
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  // Persist unsent query text so refresh does not lose draft work.
  useEffect(() => {
    saveDraftValue(CHAT_DRAFT_KEY, input);
  }, [input]);

  const handleSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    // Cancel any previous in-flight request
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    // Timeout guard
    const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input.trim(),
      timestamp: new Date().toISOString(),
    };

    setMessages(prev => [...prev, userMessage]);
    setInput('');
    clearDraftValue(CHAT_DRAFT_KEY);
    setIsLoading(true);

    try {
      // Prepend researcher profile so the backend receives one combined system prompt
      const combinedPrompt = [researcherProfile.trim(), customPrompt.trim()].filter(Boolean).join('\n\n');

      const request: QueryRequest = {
        query: userMessage.content,
        document_id: selectedDocument?.id || null,
        conversation_id: conversationId,
        model: selectedModel || null,
        system_prompt: combinedPrompt || undefined,
      };

      const response = await queryDocuments(request, controller.signal);

      if (!conversationId && response.conversation_id) {
        onConversationCreated(response.conversation_id);
      }

      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: response.answer,
        timestamp: new Date().toISOString(),
        citations: response.citations,
        retrieved_chunks: response.retrieved_chunks,
        retrieval_trace: response.retrieval_trace ?? null,
      };

      setMessages(prev => [...prev, assistantMessage]);

    } catch (error) {
      if ((error as Error).name === 'AbortError') {
        const timeoutMessage: Message = {
          id: (Date.now() + 1).toString(),
          role: 'assistant',
          content: 'Request timed out. Please try a shorter question or try again in a moment.',
          timestamp: new Date().toISOString(),
        };
        setMessages(prev => [...prev, timeoutMessage]);
        return;
      }

      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: 'Sorry, I encountered an error processing your request. Please try again.',
        timestamp: new Date().toISOString(),
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      clearTimeout(timeoutId);
      setIsLoading(false);
    }
  }, [input, isLoading, selectedDocument, conversationId, selectedModel, researcherProfile, customPrompt, onConversationCreated]);

  const handleShowCitations = (message: Message) => {
    if (message.citations) {
      onShowCitations(
        message.citations,
        message.retrieved_chunks ?? [],
        message.retrieval_trace ?? null
      );
    }
  };

  const getPlaceholderText = () => {
    if (selectedDocument) {
      return `Ask about "${selectedDocument.original_name}"...`;
    }
    return 'Ask a question about your documents...';
  };

  return (
    <div className="flex flex-col h-full bg-surface">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 sm:p-8 space-y-8 custom-scrollbar">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center max-w-2xl mx-auto px-4">
            <div className="w-24 h-24 bg-accent-light rounded-3xl flex items-center justify-center mb-8 border border-accent/20">
              <Sparkles className="w-10 h-10 text-accent" />
            </div>
            <h2 className="text-3xl font-black mb-4 tracking-tight text-ink">{PRODUCT_TITLE}</h2>
            <p className="text-ink-muted text-sm mb-6">{PRODUCT_TAGLINE}</p>
            {!selectedDocument && (
              <p className="text-ink-subtle text-xs mb-6">Select a document from the sidebar to get started</p>
            )}
            {selectedDocument && (
              <div className="flex flex-wrap gap-2 justify-center">
                {[
                  'Summarise the key points',
                  'What entities are mentioned?',
                  'What are the main conclusions?',
                ].map((suggestion) => (
                  <button
                    key={suggestion}
                    type="button"
                    onClick={() => setInput(suggestion)}
                    className="px-4 py-2 rounded-xl text-sm bg-surface-card border border-slate-200 hover:border-accent/50 hover:bg-accent-light/30 text-ink transition-colors"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            )}
          </div>
        ) : (
          <div className="max-w-4xl mx-auto w-full space-y-8">
            {messages.map((message) => (
              <div
                key={message.id}
                className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div className={`max-w-[85%] rounded-3xl ${
                  message.role === 'user'
                    ? 'bg-accent text-white'
                    : 'bg-surface-card border border-slate-200 shadow-sm'
                }`}>
                  <div className="px-6 py-5 prose prose-sm max-w-none prose-p:my-1 prose-ul:my-1 prose-ol:my-1 prose-headings:text-ink prose-p:text-ink prose-li:text-ink">
                    {message.role === 'assistant' ? (
                      <>
                        <ReactMarkdown>{message.content}</ReactMarkdown>
                        {message.citations && message.citations.length > 0 && (
                          <button
                            onClick={() => handleShowCitations(message)}
                            className="mt-2 flex items-center gap-1.5 text-xs text-accent hover:text-accent-hover"
                          >
                            <Quote className="w-3.5 h-3.5" />
                            {message.citations.length} source{message.citations.length > 1 ? 's' : ''}
                          </button>
                        )}
                      </>
                    ) : (
                      <p className="text-sm leading-relaxed">{message.content}</p>
                    )}
                  </div>
                </div>
              </div>
            ))}
            {isLoading && (
              <div className="flex justify-start">
                <div className="bg-surface-card border border-slate-200 rounded-3xl px-6 py-5 shadow-sm">
                  <Loader2 className="w-6 h-6 text-accent animate-spin" />
                </div>
              </div>
            )}
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-4 sm:p-8 pt-0">
        <form onSubmit={handleSubmit} className="max-w-4xl mx-auto flex gap-3 p-2 bg-surface-card border border-slate-200 rounded-3xl shadow-sm">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                const form = e.currentTarget.form;
                if (form && form.requestSubmit) {
                  form.requestSubmit();
                }
              }
            }}
            placeholder={getPlaceholderText()}
            disabled={isLoading}
            className="flex-1 bg-transparent px-5 py-3.5 outline-none text-sm text-ink placeholder-ink-subtle"
          />
          <button
            type="submit"
            disabled={!input.trim() || isLoading}
            className="bg-accent hover:bg-accent-hover p-4 rounded-2xl transition-all shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Send className="w-5 h-5 text-white" />
          </button>
        </form>
      </div>
    </div>
  );
};

export default ChatInterface;
