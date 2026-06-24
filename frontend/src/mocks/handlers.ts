import { http, HttpResponse, delay } from 'msw';
import { HOLDINGS_FIXTURES } from './fixtures/holdings';
import { FILES_FIXTURES } from './fixtures/files';
import { CHAT_CANNED_ANSWERS, CHAT_DEFAULT_RESPONSE } from './fixtures/chat';
import type { SyncStageEvent } from '../api/types';

// Module-level flag to simulate single-flight sync
let syncRunning = false;

// SSE stage simulation sequence
const SYNC_STAGES: SyncStageEvent[] = [
  { stage: 'discover', status: 'running', files_discovered: 0 },
  { stage: 'discover', status: 'done', files_discovered: 42 },
  { stage: 'download', status: 'running', files_discovered: 42, files_downloaded: 0 },
  { stage: 'download', status: 'done', files_discovered: 42, files_downloaded: 40 },
  { stage: 'classify', status: 'running', files_downloaded: 40, files_classified: 0 },
  { stage: 'classify', status: 'done', files_downloaded: 40, files_classified: 40 },
  { stage: 'extract', status: 'running', files_classified: 40, files_extracted: 0 },
  { stage: 'extract', status: 'done', files_classified: 40, files_extracted: 40 },
  { stage: 'index', status: 'running', files_extracted: 40, files_indexed: 0 },
  { stage: 'index', status: 'done', files_extracted: 40, files_indexed: 40 },
];

export const handlers = [
  // POST /api/sync — start sync
  http.post('/api/sync', () => {
    if (syncRunning) {
      return HttpResponse.json(
        { detail: 'A sync is already in progress.' },
        { status: 409 },
      );
    }
    syncRunning = true;
    // Auto-reset after 15s so tests can re-trigger
    setTimeout(() => { syncRunning = false; }, 15_000);
    return HttpResponse.json({ status: 'started', sync_id: 'mock-sync-001' }, { status: 202 });
  }),

  // GET /api/sync/stream — SSE progress
  http.get('/api/sync/stream', () => {
    const encoder = new TextEncoder();

    const stream = new ReadableStream({
      async start(controller) {
        const send = (eventName: string, data: unknown) => {
          const chunk = `event: ${eventName}\ndata: ${JSON.stringify(data)}\n\n`;
          controller.enqueue(encoder.encode(chunk));
        };

        for (const stageEvent of SYNC_STAGES) {
          await delay(600);
          send('stage', { type: 'stage', ...stageEvent });
        }

        await delay(400);
        send('complete', {
          type: 'complete',
          stages: SYNC_STAGES.filter((s) => s.status === 'done'),
        });
        syncRunning = false;
        controller.close();
      },
    });

    return new HttpResponse(stream, {
      status: 200,
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        Connection: 'keep-alive',
      },
    });
  }),

  // GET /api/holdings
  http.get('/api/holdings', async () => {
    await delay(300);
    return HttpResponse.json(HOLDINGS_FIXTURES);
  }),

  // POST /api/chat
  http.post('/api/chat', async ({ request }) => {
    await delay(800);
    const body = await request.json() as { query: string };
    const query = (body.query ?? '').toLowerCase();

    const match = CHAT_CANNED_ANSWERS.find((c) =>
      query.includes(c.queryPattern),
    );
    return HttpResponse.json(match ? match.response : CHAT_DEFAULT_RESPONSE);
  }),

  // GET /api/files
  http.get('/api/files', async () => {
    await delay(300);
    return HttpResponse.json(FILES_FIXTURES);
  }),

  // GET /api/files/:id/download — return a tiny PDF-like blob
  http.get('/api/files/:id/download', async ({ params }) => {
    await delay(200);
    const fileId = params['id'] as string;
    const record = FILES_FIXTURES.find((f) => f.file_id === fileId);
    const fileName = record?.file_name ?? `${fileId}.pdf`;
    const blob = new Blob([`Mock PDF content for ${fileName}`], {
      type: 'application/pdf',
    });
    const buffer = await blob.arrayBuffer();
    return new HttpResponse(buffer, {
      status: 200,
      headers: {
        'Content-Type': 'application/pdf',
        'Content-Disposition': `attachment; filename="${fileName}"`,
      },
    });
  }),
];
