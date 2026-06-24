import { useEffect, useRef, useState } from 'react';
import { postChat, fileDownloadUrl } from '../api/client';
import type { ChatResponse, Citation } from '../api/types';
import { Badge } from '../components/Badge';
import { Card, CardBody } from '../components/Card';

// ── Types ──────────────────────────────────────────────────────────────────

interface UserMessage {
  role: 'user';
  text: string;
}

interface AssistantMessage {
  role: 'assistant';
  response: ChatResponse;
}

type ConversationEntry = UserMessage | AssistantMessage;

// ── Example questions shown in empty state ─────────────────────────────────

const EXAMPLE_QUESTIONS = [
  'What is the total value of my portfolio?',
  'How has fund performance trended over the past year?',
  'Are there any ESG reports available?',
  'What dividend distributions have been made?',
];

// ── Subcomponents ──────────────────────────────────────────────────────────

function SpinnerIcon() {
  return (
    <svg
      className="h-4 w-4 animate-spin"
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
    >
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
      />
    </svg>
  );
}

interface CitationChipProps {
  citation: Citation;
}

function CitationChip({ citation }: CitationChipProps) {
  const label = citation.period
    ? `${citation.file_name} · ${citation.period}`
    : citation.file_name;

  return (
    <a
      href={fileDownloadUrl(citation.file_id)}
      target="_blank"
      rel="noopener noreferrer"
      title={`Open ${citation.file_name}`}
      className="inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs font-medium bg-brand-50 text-brand-700 border border-brand-200 hover:bg-brand-100 hover:border-brand-300 transition-colors whitespace-nowrap max-w-xs"
    >
      <svg
        className="h-3 w-3 flex-shrink-0"
        xmlns="http://www.w3.org/2000/svg"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth={2}
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
        />
      </svg>
      <span className="truncate">{label}</span>
      <span className="flex-shrink-0 opacity-60">↗</span>
    </a>
  );
}

interface AssistantBubbleProps {
  response: ChatResponse;
}

function AssistantBubble({ response }: AssistantBubbleProps) {
  return (
    <div className="flex gap-3 items-start">
      {/* Avatar */}
      <div className="flex-shrink-0 h-8 w-8 rounded-full bg-brand-600 flex items-center justify-center text-white text-xs font-bold select-none">
        AI
      </div>

      <div className="flex-1 min-w-0">
        {/* Out-of-context notice */}
        {response.out_of_context && (
          <div className="mb-2 flex items-center gap-2">
            <Badge variant="warning">Out of context</Badge>
            <span className="text-xs text-gray-500">
              This question falls outside the indexed documents.
            </span>
          </div>
        )}

        {/* Answer text */}
        <Card className="inline-block max-w-full">
          <CardBody>
            <p className="text-sm text-gray-800 leading-relaxed whitespace-pre-wrap">
              {response.answer}
            </p>
          </CardBody>
        </Card>

        {/* Citation chips */}
        {response.citations.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-2">
            {response.citations.map((citation) => (
              <CitationChip key={citation.file_id} citation={citation} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex gap-3 items-start">
      {/* Avatar */}
      <div className="flex-shrink-0 h-8 w-8 rounded-full bg-brand-600 flex items-center justify-center text-white text-xs font-bold select-none">
        AI
      </div>
      <Card className="inline-block">
        <CardBody>
          <div className="flex items-center gap-2 text-sm text-gray-400">
            <SpinnerIcon />
            <span>Thinking…</span>
          </div>
        </CardBody>
      </Card>
    </div>
  );
}

// ── Empty state ────────────────────────────────────────────────────────────

interface EmptyStateProps {
  onSelectExample: (q: string) => void;
}

function EmptyState({ onSelectExample }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center flex-1 py-16 px-4 text-center">
      <div className="h-14 w-14 rounded-full bg-brand-100 flex items-center justify-center mb-4">
        <svg
          className="h-7 w-7 text-brand-600"
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={1.5}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M8.625 12a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H8.25m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H12m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 01-2.555-.337A5.972 5.972 0 015.41 20.97a5.969 5.969 0 01-.474-.065 4.48 4.48 0 00.978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25z"
          />
        </svg>
      </div>
      <h2 className="text-lg font-semibold text-gray-900 mb-1">
        Ask about your portfolio
      </h2>
      <p className="text-sm text-gray-500 mb-8 max-w-sm">
        Get instant answers from your indexed investor documents — capital account statements, reports, and more.
      </p>

      <div className="grid gap-2 w-full max-w-md">
        {EXAMPLE_QUESTIONS.map((q) => (
          <button
            key={q}
            onClick={() => onSelectExample(q)}
            className="text-left rounded-lg border border-gray-200 bg-white px-4 py-3 text-sm text-gray-700 hover:border-brand-300 hover:bg-brand-50 hover:text-brand-700 transition-colors shadow-sm"
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────

export default function ChatPage() {
  const [conversation, setConversation] = useState<ConversationEntry[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isPending, setIsPending] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll to bottom whenever conversation changes or pending state changes
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [conversation, isPending]);

  async function handleSubmit(queryText: string) {
    const query = queryText.trim();
    if (!query || isPending) return;

    setInputValue('');
    setErrorMessage(null);

    // Append user message immediately
    setConversation((prev) => [...prev, { role: 'user', text: query }]);
    setIsPending(true);

    try {
      const response = await postChat({ query });
      setConversation((prev) => [...prev, { role: 'assistant', response }]);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to get a response. Please try again.');
    } finally {
      setIsPending(false);
      // Restore focus to input
      inputRef.current?.focus();
    }
  }

  function handleFormSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    void handleSubmit(inputValue);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    // Submit on Enter (without Shift)
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void handleSubmit(inputValue);
    }
  }

  function handleExampleSelect(q: string) {
    setInputValue(q);
    inputRef.current?.focus();
  }

  const hasConversation = conversation.length > 0;

  return (
    <div className="flex flex-col h-full p-8 max-w-3xl mx-auto">
      {/* Page header */}
      <div className="mb-6 flex-shrink-0">
        <h1 className="text-2xl font-bold text-gray-900">Chat</h1>
        <p className="mt-1 text-sm text-gray-500">
          Ask questions about your investor documents.
        </p>
      </div>

      {/* Conversation area */}
      <div className="flex-1 overflow-y-auto min-h-0">
        {!hasConversation ? (
          <EmptyState onSelectExample={handleExampleSelect} />
        ) : (
          <div className="space-y-6 pb-4">
            {conversation.map((entry, idx) => {
              if (entry.role === 'user') {
                return (
                  <div key={idx} className="flex justify-end">
                    <div className="max-w-md">
                      <div className="rounded-2xl bg-brand-600 px-4 py-3 text-sm text-white leading-relaxed">
                        {entry.text}
                      </div>
                    </div>
                  </div>
                );
              }

              return (
                <AssistantBubble key={idx} response={entry.response} />
              );
            })}

            {/* Typing indicator */}
            {isPending && <TypingIndicator />}

            {/* Error alert */}
            {errorMessage && !isPending && (
              <div className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 p-4">
                <span className="text-red-500 mt-0.5 flex-shrink-0">✕</span>
                <div>
                  <p className="text-sm font-semibold text-red-800">Request failed</p>
                  <p className="text-sm text-red-700 mt-0.5">{errorMessage}</p>
                </div>
              </div>
            )}

            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {/* Error alert when no conversation yet */}
      {errorMessage && !hasConversation && (
        <div className="mb-4 flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 p-4 flex-shrink-0">
          <span className="text-red-500 mt-0.5 flex-shrink-0">✕</span>
          <div>
            <p className="text-sm font-semibold text-red-800">Request failed</p>
            <p className="text-sm text-red-700 mt-0.5">{errorMessage}</p>
          </div>
        </div>
      )}

      {/* Input area */}
      <div className="mt-4 flex-shrink-0">
        <form onSubmit={handleFormSubmit}>
          <div className="flex items-end gap-3 rounded-xl border border-gray-200 bg-white shadow-sm px-4 py-3 focus-within:border-brand-400 focus-within:ring-1 focus-within:ring-brand-400 transition-colors">
            <textarea
              ref={inputRef}
              rows={1}
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask a question about your portfolio…"
              disabled={isPending}
              className="flex-1 resize-none bg-transparent text-sm text-gray-900 placeholder-gray-400 focus:outline-none disabled:opacity-50 leading-relaxed"
              style={{ minHeight: '1.5rem', maxHeight: '8rem' }}
            />
            <button
              type="submit"
              disabled={isPending || !inputValue.trim()}
              className={[
                'flex-shrink-0 inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2',
                isPending || !inputValue.trim()
                  ? 'cursor-not-allowed bg-gray-100 text-gray-400'
                  : 'bg-brand-600 text-white hover:bg-brand-700 active:bg-brand-700',
              ].join(' ')}
            >
              {isPending ? (
                <>
                  <SpinnerIcon />
                  <span>Sending</span>
                </>
              ) : (
                'Send'
              )}
            </button>
          </div>
          <p className="mt-1.5 text-xs text-gray-400 text-right">
            Press Enter to send · Shift+Enter for new line
          </p>
        </form>
      </div>
    </div>
  );
}
