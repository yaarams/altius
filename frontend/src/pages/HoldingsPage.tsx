import { useCallback, useEffect, useState } from 'react';
import { getHoldings } from '../api/client';
import type { FundSnapshot, HoldingLineItem } from '../api/types';
import { Badge } from '../components/Badge';
import { Card, CardBody, CardHeader } from '../components/Card';
import { Table, TableHead, TableBody, Th, Td } from '../components/Table';

// ── Helpers ────────────────────────────────────────────────────────────────

function formatCurrency(value: number, currency: string): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    maximumFractionDigits: 0,
  }).format(value);
}

function formatDate(iso: string): string {
  // Parse YYYY-MM-DD as a local date to avoid UTC offset shifts
  const [year, month, day] = iso.split('-').map(Number);
  return new Date(year, month - 1, day).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

// ── Sub-components ─────────────────────────────────────────────────────────

interface FundCardProps {
  fund: FundSnapshot;
}

function FundCard({ fund }: FundCardProps) {
  return (
    <Card>
      {/* Card header: fund name + meta */}
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-base font-semibold text-gray-900 leading-snug">
              {fund.fund_name}
            </h2>
            <p className="mt-0.5 text-xs text-gray-500">
              As of {formatDate(fund.as_of_date)}
            </p>
          </div>
          <div className="flex items-center gap-3 flex-shrink-0">
            <Badge variant="neutral">{fund.currency}</Badge>
            <span className="text-base font-bold text-gray-900 tabular-nums">
              {formatCurrency(fund.total_value, fund.currency)}
            </span>
          </div>
        </div>
      </CardHeader>

      {/* Holdings table — only shown when position-level line items exist */}
      {fund.holdings.length > 0 && (
        <CardBody className="p-0">
          <Table>
            <TableHead>
              <tr>
                <Th>Holding</Th>
                <Th className="text-right">Value</Th>
              </tr>
            </TableHead>
            <TableBody>
              {fund.holdings.map((item: HoldingLineItem, idx: number) => (
                <tr key={idx} className="hover:bg-gray-50 transition-colors">
                  <Td>
                    <span className="text-sm font-medium text-gray-800">{item.name}</span>
                  </Td>
                  <Td className="text-right">
                    <span className="text-sm tabular-nums text-gray-700">
                      {formatCurrency(item.value, item.currency)}
                    </span>
                  </Td>
                </tr>
              ))}
            </TableBody>
          </Table>
        </CardBody>
      )}
    </Card>
  );
}

// ── SpinnerIcon ────────────────────────────────────────────────────────────

function SpinnerIcon({ className = 'h-4 w-4' }: { className?: string }) {
  return (
    <svg
      className={`animate-spin ${className}`}
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

// ── Page header (shared across states) ────────────────────────────────────

interface PageHeaderProps {
  onRefresh: () => void;
  refreshing: boolean;
}

function PageHeader({ onRefresh, refreshing }: PageHeaderProps) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Holdings</h1>
        <p className="mt-1 text-sm text-gray-500">
          Latest fund snapshots and portfolio positions.
        </p>
      </div>

      <button
        onClick={onRefresh}
        disabled={refreshing}
        className={[
          'inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2',
          refreshing
            ? 'cursor-not-allowed bg-gray-100 text-gray-400'
            : 'bg-white text-gray-700 border border-gray-300 hover:bg-gray-50 active:bg-gray-100',
        ].join(' ')}
      >
        {refreshing ? (
          <>
            <SpinnerIcon className="h-4 w-4 text-brand-600" />
            Refreshing…
          </>
        ) : (
          <>
            <span className="text-base leading-none">↻</span>
            Refresh
          </>
        )}
      </button>
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────

export default function HoldingsPage() {
  const [funds, setFunds] = useState<FundSnapshot[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadHoldings = useCallback(async (isRefresh = false) => {
    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);

    try {
      const data = await getHoldings();
      setFunds(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load holdings.');
    } finally {
      if (isRefresh) {
        setRefreshing(false);
      } else {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    loadHoldings(false);
  }, [loadHoldings]);

  const handleRefresh = useCallback(() => {
    loadHoldings(true);
  }, [loadHoldings]);

  // ── Loading ────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="p-8 max-w-5xl">
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-gray-900">Holdings</h1>
          <p className="mt-1 text-sm text-gray-500">
            Latest fund snapshots and portfolio positions.
          </p>
        </div>
        <div className="flex items-center gap-3 text-sm text-gray-500">
          <SpinnerIcon className="h-4 w-4 text-brand-600" />
          Loading holdings…
        </div>
      </div>
    );
  }

  // ── Error ──────────────────────────────────────────────────────────────

  if (error) {
    return (
      <div className="p-8 max-w-5xl">
        <PageHeader onRefresh={handleRefresh} refreshing={refreshing} />
        <div className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 p-4">
          <span className="text-red-500 mt-0.5">✕</span>
          <div>
            <p className="text-sm font-semibold text-red-800">Failed to load holdings</p>
            <p className="text-sm text-red-700 mt-0.5">{error}</p>
          </div>
        </div>
      </div>
    );
  }

  // ── Empty state ────────────────────────────────────────────────────────

  if (funds.length === 0) {
    return (
      <div className="p-8 max-w-5xl">
        <PageHeader onRefresh={handleRefresh} refreshing={refreshing} />
        <Card>
          <CardBody>
            <div className="py-12 text-center">
              <p className="text-gray-400 text-sm">
                No holdings found. Run a sync to ingest investor documents.
              </p>
            </div>
          </CardBody>
        </Card>
      </div>
    );
  }

  // ── Fund cards ─────────────────────────────────────────────────────────

  return (
    <div className="p-8 max-w-5xl">
      <PageHeader onRefresh={handleRefresh} refreshing={refreshing} />

      {/* Summary bar */}
      <p className="mb-6 text-sm text-gray-500">
        <span className="font-medium text-gray-700">{funds.length}</span>{' '}
        fund{funds.length !== 1 ? 's' : ''}
      </p>

      <div className="flex flex-col gap-6">
        {funds.map((fund, idx) => (
          <FundCard key={`${fund.fund_name}-${idx}`} fund={fund} />
        ))}
      </div>
    </div>
  );
}
