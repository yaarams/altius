import { useEffect, useState } from 'react';
import { getFiles, fileDownloadUrl } from '../api/client';
import type { FileRecord, DocType } from '../api/types';
import { Badge } from '../components/Badge';
import { Card, CardHeader, CardBody } from '../components/Card';
import { Table, TableHead, TableBody, Th, Td } from '../components/Table';

// ── Helpers ────────────────────────────────────────────────────────────────

const DOC_TYPE_LABELS: Record<DocType, string> = {
  capital_account_statement: 'Capital Account Statement',
  report: 'Report',
  other: 'Other',
};

function formatDocType(docType: DocType): string {
  return DOC_TYPE_LABELS[docType] ?? docType;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

function formatConfidence(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function isLowConfidence(file: FileRecord): boolean {
  return file.low_confidence || file.classification_confidence < 0.75;
}

// ── Sort ───────────────────────────────────────────────────────────────────

type SortKey = 'file_name' | 'doc_type' | 'fund_name' | 'classification_confidence' | 'uploaded_at';
type SortDir = 'asc' | 'desc';

function compareFiles(a: FileRecord, b: FileRecord, key: SortKey, dir: SortDir): number {
  let result = 0;

  switch (key) {
    case 'file_name':
      result = a.file_name.localeCompare(b.file_name);
      break;
    case 'doc_type':
      result = formatDocType(a.doc_type).localeCompare(formatDocType(b.doc_type));
      break;
    case 'fund_name': {
      const fa = a.fund_name ?? '';
      const fb = b.fund_name ?? '';
      result = fa.localeCompare(fb);
      break;
    }
    case 'classification_confidence':
      result = a.classification_confidence - b.classification_confidence;
      break;
    case 'uploaded_at':
      result = new Date(a.uploaded_at).getTime() - new Date(b.uploaded_at).getTime();
      break;
  }

  return dir === 'asc' ? result : -result;
}

function sortFiles(files: FileRecord[], key: SortKey, dir: SortDir): FileRecord[] {
  // Stable sort: preserve original index as tiebreaker
  return files
    .map((f, i) => ({ f, i }))
    .sort((a, b) => {
      const primary = compareFiles(a.f, b.f, key, dir);
      return primary !== 0 ? primary : a.i - b.i;
    })
    .map(({ f }) => f);
}

// ── Sortable column header ─────────────────────────────────────────────────

interface SortableThProps {
  label: string;
  sortKey: SortKey;
  currentKey: SortKey;
  currentDir: SortDir;
  onSort: (key: SortKey) => void;
  className?: string;
}

function SortableTh({ label, sortKey, currentKey, currentDir, onSort, className = '' }: SortableThProps) {
  const isActive = currentKey === sortKey;
  const indicator = isActive ? (currentDir === 'asc' ? ' ▲' : ' ▼') : '';

  return (
    <th
      scope="col"
      onClick={() => onSort(sortKey)}
      className={[
        'px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide cursor-pointer select-none whitespace-nowrap',
        isActive ? 'text-brand-700' : 'text-gray-500 hover:text-gray-700',
        className,
      ].join(' ')}
    >
      {label}{indicator}
    </th>
  );
}

// ── Component ──────────────────────────────────────────────────────────────

export default function FilesPage() {
  const [files, setFiles] = useState<FileRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>('uploaded_at');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    getFiles()
      .then((data) => {
        if (!cancelled) {
          setFiles(data);
          setLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load files.');
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  function handleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('asc');
    }
  }

  const sortedFiles = sortFiles(files, sortKey, sortDir);

  // ── Loading ──────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="p-8 max-w-6xl">
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-gray-900">Files</h1>
          <p className="mt-1 text-sm text-gray-500">Investor documents ingested into the platform.</p>
        </div>
        <div className="flex items-center gap-3 text-sm text-gray-500">
          <svg className="h-4 w-4 animate-spin text-brand-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
          </svg>
          Loading files…
        </div>
      </div>
    );
  }

  // ── Error ────────────────────────────────────────────────────────────────

  if (error) {
    return (
      <div className="p-8 max-w-6xl">
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-gray-900">Files</h1>
          <p className="mt-1 text-sm text-gray-500">Investor documents ingested into the platform.</p>
        </div>
        <div className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 p-4">
          <span className="text-red-500 mt-0.5">✕</span>
          <div>
            <p className="text-sm font-semibold text-red-800">Failed to load files</p>
            <p className="text-sm text-red-700 mt-0.5">{error}</p>
          </div>
        </div>
      </div>
    );
  }

  // ── Empty state ──────────────────────────────────────────────────────────

  if (sortedFiles.length === 0) {
    return (
      <div className="p-8 max-w-6xl">
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-gray-900">Files</h1>
          <p className="mt-1 text-sm text-gray-500">Investor documents ingested into the platform.</p>
        </div>
        <Card>
          <CardBody>
            <div className="py-12 text-center">
              <p className="text-gray-400 text-sm">No files found. Run a sync to ingest investor documents.</p>
            </div>
          </CardBody>
        </Card>
      </div>
    );
  }

  // ── Table ────────────────────────────────────────────────────────────────

  const lowConfidenceCount = sortedFiles.filter(isLowConfidence).length;

  return (
    <div className="p-8 max-w-6xl">
      {/* Page header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Files</h1>
        <p className="mt-1 text-sm text-gray-500">
          Investor documents ingested into the platform.{' '}
          <span className="text-gray-700 font-medium">{sortedFiles.length}</span> file{sortedFiles.length !== 1 ? 's' : ''} total.
          {lowConfidenceCount > 0 && (
            <span className="ml-2 text-amber-700">
              {lowConfidenceCount} with low classification confidence.
            </span>
          )}
        </p>
      </div>

      <Card>
        <CardHeader>
          <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">
            All Files
          </h2>
        </CardHeader>
        <CardBody className="p-0">
          <Table>
            <TableHead>
              <tr>
                <SortableTh
                  label="File Name"
                  sortKey="file_name"
                  currentKey={sortKey}
                  currentDir={sortDir}
                  onSort={handleSort}
                />
                <SortableTh
                  label="Doc Type"
                  sortKey="doc_type"
                  currentKey={sortKey}
                  currentDir={sortDir}
                  onSort={handleSort}
                />
                <SortableTh
                  label="Fund"
                  sortKey="fund_name"
                  currentKey={sortKey}
                  currentDir={sortDir}
                  onSort={handleSort}
                />
                <Th>Period</Th>
                <SortableTh
                  label="Confidence"
                  sortKey="classification_confidence"
                  currentKey={sortKey}
                  currentDir={sortDir}
                  onSort={handleSort}
                />
                <SortableTh
                  label="Uploaded"
                  sortKey="uploaded_at"
                  currentKey={sortKey}
                  currentDir={sortDir}
                  onSort={handleSort}
                />
                <Th className="text-right">Action</Th>
              </tr>
            </TableHead>
            <TableBody>
              {sortedFiles.map((file) => {
                const lowConf = isLowConfidence(file);
                return (
                  <tr key={file.file_id} className="hover:bg-gray-50 transition-colors">
                    {/* File name */}
                    <Td className="max-w-xs">
                      <div className="flex items-start gap-2">
                        <span className="truncate text-sm font-medium text-gray-900" title={file.file_name}>
                          {file.file_name}
                        </span>
                      </div>
                    </Td>

                    {/* Doc type */}
                    <Td>
                      <span className="whitespace-nowrap text-sm text-gray-700">
                        {formatDocType(file.doc_type)}
                      </span>
                    </Td>

                    {/* Fund */}
                    <Td>
                      <span className="text-sm text-gray-700">
                        {file.fund_name ?? <span className="text-gray-400 italic">—</span>}
                      </span>
                    </Td>

                    {/* Period */}
                    <Td>
                      <span className="text-sm text-gray-700 whitespace-nowrap">
                        {file.period ?? <span className="text-gray-400 italic">—</span>}
                      </span>
                    </Td>

                    {/* Confidence */}
                    <Td>
                      <div className="flex items-center gap-2">
                        <span className={['text-sm tabular-nums', lowConf ? 'text-amber-700 font-medium' : 'text-gray-700'].join(' ')}>
                          {formatConfidence(file.classification_confidence)}
                        </span>
                        {lowConf && (
                          <Badge variant="warning">Low confidence</Badge>
                        )}
                      </div>
                    </Td>

                    {/* Uploaded date */}
                    <Td>
                      <span className="text-sm text-gray-700 whitespace-nowrap">
                        {formatDate(file.uploaded_at)}
                      </span>
                    </Td>

                    {/* Open action */}
                    <Td className="text-right">
                      <a
                        href={fileDownloadUrl(file.file_id)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 rounded-md px-3 py-1.5 text-xs font-semibold text-brand-700 border border-brand-200 bg-brand-50 hover:bg-brand-100 hover:border-brand-300 transition-colors whitespace-nowrap"
                      >
                        Open ↗
                      </a>
                    </Td>
                  </tr>
                );
              })}
            </TableBody>
          </Table>
        </CardBody>
      </Card>
    </div>
  );
}
