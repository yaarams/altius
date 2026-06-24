import type { FundSnapshot } from '../../api/types';

export const HOLDINGS_FIXTURES: FundSnapshot[] = [
  {
    fund_name: 'Altius Venture Fund III',
    as_of_date: '2024-09-30',
    currency: 'USD',
    total_value: 142_500_000,
    holdings: [
      { name: 'DataStream AI', value: 34_200_000, currency: 'USD' },
      { name: 'NovaMed Therapeutics', value: 28_750_000, currency: 'USD' },
      { name: 'GreenPath Energy', value: 21_300_000, currency: 'USD' },
      { name: 'FinEdge Capital', value: 18_900_000, currency: 'USD' },
      { name: 'UrbanMobility Inc.', value: 15_600_000, currency: 'USD' },
      { name: 'CloudSecure Systems', value: 11_250_000, currency: 'USD' },
      { name: 'Other holdings', value: 12_500_000, currency: 'USD' },
    ],
  },
  {
    fund_name: 'Altius Growth Equity II',
    as_of_date: '2024-09-30',
    currency: 'USD',
    total_value: 87_300_000,
    holdings: [
      { name: 'NextRetail Platform', value: 22_100_000, currency: 'USD' },
      { name: 'HealthBridge Digital', value: 19_450_000, currency: 'USD' },
      { name: 'CoreLogistics AI', value: 16_200_000, currency: 'USD' },
      { name: 'AgraTech Solutions', value: 14_300_000, currency: 'USD' },
      { name: 'PropVista Group', value: 10_250_000, currency: 'USD' },
      { name: 'Other holdings', value: 5_000_000, currency: 'USD' },
    ],
  },
  {
    fund_name: 'Altius European Opportunities',
    as_of_date: '2024-06-30',
    currency: 'EUR',
    total_value: 63_800_000,
    holdings: [
      { name: 'BioNord Pharma AB', value: 18_600_000, currency: 'EUR' },
      { name: 'Solaris GmbH', value: 14_200_000, currency: 'EUR' },
      { name: 'Meridian Fintech SE', value: 12_700_000, currency: 'EUR' },
      { name: 'Avance Logistics SAS', value: 10_100_000, currency: 'EUR' },
      { name: 'Other holdings', value: 8_200_000, currency: 'EUR' },
    ],
  },
  {
    fund_name: 'Altius Real Assets Fund I',
    as_of_date: '2024-09-30',
    currency: 'USD',
    total_value: 214_000_000,
    holdings: [
      { name: 'Pacific Gateway Logistics Park', value: 58_400_000, currency: 'USD' },
      { name: 'Sunbelt Industrial REIT', value: 47_200_000, currency: 'USD' },
      { name: 'Cascade Renewable Energy', value: 41_500_000, currency: 'USD' },
      { name: 'Metro Office Portfolio', value: 35_600_000, currency: 'USD' },
      { name: 'Other assets', value: 31_300_000, currency: 'USD' },
    ],
  },
  {
    fund_name: 'Altius Credit Opportunities',
    as_of_date: '2024-09-30',
    currency: 'USD',
    total_value: 38_950_000,
    holdings: [
      { name: 'Senior Secured Term Loans', value: 18_200_000, currency: 'USD' },
      { name: 'Mezzanine Debt Portfolio', value: 12_450_000, currency: 'USD' },
      { name: 'Structured Credit', value: 8_300_000, currency: 'USD' },
    ],
  },
  {
    fund_name: 'Altius Asia-Pacific Fund',
    as_of_date: '2024-06-30',
    currency: 'USD',
    total_value: 52_100_000,
    holdings: [
      { name: 'TechBridge Singapore', value: 16_800_000, currency: 'USD' },
      { name: 'IndusScale Ventures', value: 13_200_000, currency: 'USD' },
      { name: 'OceanRoute Logistics', value: 10_400_000, currency: 'USD' },
      { name: 'NexGen Semiconductors', value: 8_150_000, currency: 'USD' },
      { name: 'Other holdings', value: 3_550_000, currency: 'USD' },
    ],
  },
];

/** Empty variant for testing empty state UI */
export const HOLDINGS_EMPTY: FundSnapshot[] = [];
