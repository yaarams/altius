import { useCallback, useEffect, useRef, useState } from 'react';
import { startSync, subscribeSync } from '../api/client';
import { SyncInProgressError } from '../api/types';
import type { SyncStage, SyncStageStatus, SyncStreamEvent } from '../api/types';
import { Badge } from '../components/Badge';
import type { BadgeVariant } from '../components/Badge';
import { Card, CardBody, CardHeader } from '../components/Card';

// ── Types ──────────────────────────────────────────────────────────────────

interface StageState {
  stage: SyncStage;
  status: SyncStageStatus;
  counts: Record<string, number>;
}

type SyncStatus = 'idle' | 'running' | 'complete' | 'error';

const STAGE_ORDER: SyncStage[] = [
  'discover',
  'download',
  'classify',
  'extract',
  'index',
];

const STAGE_LABELS: Record<SyncStage, string> = {
  discover: 'Discover files',
  download: 'Download documents',
  classify: 'Classify documents',
  extract: 'Extract content',
  index: 'Build index',
};

const COUNT_LABELS: Record<string, string> = {
  files_discovered: 'discovered',
  files_downloaded: 'downloaded',
  files_classified: 'classified',
  files_extracted: 'extracted',
  files_indexed: 'indexed',
};

// ── Helpers ────────────────────────────────────────────────────────────────

function initialStages(): StageState[] {
  return STAGE_ORDER.map((stage) => ({
    stage,
    status: 'pending' as SyncStageStatus,
    counts: {},
  }));
}

function statusToBadge(status: SyncStageStatus): BadgeVariant {
  switch (status) {
    case 'done': return 'success';
    case 'running': return 'info';
    case 'error': return 'error';
    default: return 'neutral';
  }
}

function statusLabel(status: SyncStageStatus): string {
  switch (status) {
    case 'done': return 'Done';
    case 'running': return 'Running…';
    case 'error': return 'Error';
    default: return 'Pending';
  }
}

// ── Component ──────────────────────────────────────────────────────────────

export default function SyncPage() {
  const [syncStatus, setSyncStatus] = useState<SyncStatus>('idle');
  const [stages, setStages] = useState<StageState[]>(initialStages());
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [alreadyRunning, setAlreadyRunning] = useState(false);
  const cleanupRef = useRef<(() => void) | null>(null);

  // Cleanup SSE on unmount
  useEffect(() => {
    return () => {
      cleanupRef.current?.();
    };
  }, []);

  const applyStreamEvent = useCallback((event: SyncStreamEvent) => {
    if (event.type === 'complete') {
      setSyncStatus('complete');
      return;
    }
    if (event.type === 'error') {
      setSyncStatus('error');
      setErrorMessage(event.message);
      return;
    }
    // type === 'stage'
    if (event.type === 'stage') {
      const { stage, status, ...rest } = event;
      const counts: Record<string, number> = {};
      for (const [k, v] of Object.entries(rest)) {
        if (k !== 'stage' && k !== 'status' && typeof v === 'number') {
          counts[k] = v;
        }
      }
      setStages((prev) =>
        prev.map((s) =>
          s.stage === stage ? { ...s, status, counts } : s,
        ),
      );
    }
  }, []);

  const handleRunSync = useCallback(async () => {
    setAlreadyRunning(false);
    setErrorMessage(null);
    setStages(initialStages());

    try {
      await startSync();
    } catch (err) {
      if (err instanceof SyncInProgressError) {
        setAlreadyRunning(true);
        return;
      }
      setErrorMessage(err instanceof Error ? err.message : 'Unknown error starting sync.');
      setSyncStatus('error');
      return;
    }

    setSyncStatus('running');

    const cleanup = subscribeSync(
      (event) => applyStreamEvent(event),
      () => {
        setSyncStatus('error');
        setErrorMessage('Lost connection to sync stream.');
      },
    );
    cleanupRef.current = cleanup;
  }, [applyStreamEvent]);

  const handleReset = () => {
    cleanupRef.current?.();
    cleanupRef.current = null;
    setSyncStatus('idle');
    setStages(initialStages());
    setErrorMessage(null);
    setAlreadyRunning(false);
  };

  const isRunning = syncStatus === 'running';

  return (
    <div className="p-8 max-w-2xl">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">Sync Documents</h1>
        <p className="mt-1 text-sm text-gray-500">
          Pull the latest investor documents from storage and index them for chat.
        </p>
      </div>

      {/* Action row */}
      <div className="flex items-center gap-4 mb-6">
        <button
          onClick={handleRunSync}
          disabled={isRunning}
          className={[
            'inline-flex items-center gap-2 rounded-lg px-5 py-2.5 text-sm font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2',
            isRunning
              ? 'cursor-not-allowed bg-gray-200 text-gray-400'
              : 'bg-brand-600 text-white hover:bg-brand-700 active:bg-brand-700',
          ].join(' ')}
        >
          {isRunning ? (
            <>
              <SpinnerIcon />
              Syncing…
            </>
          ) : (
            <>
              <span className="text-base leading-none">↻</span>
              Run sync
            </>
          )}
        </button>

        {(syncStatus === 'complete' || syncStatus === 'error') && (
          <button
            onClick={handleReset}
            className="text-sm text-gray-500 underline hover:text-gray-700"
          >
            Reset
          </button>
        )}
      </div>

      {/* Already running alert */}
      {alreadyRunning && (
        <div className="mb-5 flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 p-4">
          <span className="text-amber-500 mt-0.5">⚠</span>
          <div>
            <p className="text-sm font-semibold text-amber-800">Sync already in progress</p>
            <p className="text-sm text-amber-700 mt-0.5">
              Another sync run is currently active. Please wait for it to complete before starting a new one.
            </p>
          </div>
        </div>
      )}

      {/* Error alert */}
      {errorMessage && !alreadyRunning && (
        <div className="mb-5 flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 p-4">
          <span className="text-red-500 mt-0.5">✕</span>
          <div>
            <p className="text-sm font-semibold text-red-800">Sync failed</p>
            <p className="text-sm text-red-700 mt-0.5">{errorMessage}</p>
          </div>
        </div>
      )}

      {/* Complete banner */}
      {syncStatus === 'complete' && (
        <div className="mb-5 flex items-start gap-3 rounded-lg border border-green-200 bg-green-50 p-4">
          <span className="text-green-500 mt-0.5">✓</span>
          <p className="text-sm font-semibold text-green-800">Sync completed successfully.</p>
        </div>
      )}

      {/* Stage progress */}
      {(isRunning || syncStatus === 'complete' || syncStatus === 'error') && (
        <Card>
          <CardHeader>
            <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">
              Progress
            </h2>
          </CardHeader>
          <CardBody className="p-0">
            <ul className="divide-y divide-gray-100">
              {stages.map((s, idx) => (
                <li key={s.stage} className="flex items-center gap-4 px-6 py-4">
                  {/* Step number */}
                  <div
                    className={[
                      'flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full text-xs font-bold',
                      s.status === 'done'
                        ? 'bg-green-100 text-green-700'
                        : s.status === 'running'
                        ? 'bg-blue-100 text-blue-700'
                        : s.status === 'error'
                        ? 'bg-red-100 text-red-700'
                        : 'bg-gray-100 text-gray-400',
                    ].join(' ')}
                  >
                    {s.status === 'done' ? '✓' : idx + 1}
                  </div>

                  {/* Label */}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-800">
                      {STAGE_LABELS[s.stage]}
                    </p>
                    {Object.entries(s.counts).length > 0 && (
                      <p className="text-xs text-gray-400 mt-0.5">
                        {Object.entries(s.counts)
                          .map(
                            ([k, v]) =>
                              `${v.toLocaleString()} ${COUNT_LABELS[k] ?? k}`,
                          )
                          .join(' · ')}
                      </p>
                    )}
                  </div>

                  {/* Status badge */}
                  <Badge variant={statusToBadge(s.status)}>
                    {statusLabel(s.status)}
                  </Badge>
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>
      )}
    </div>
  );
}

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
