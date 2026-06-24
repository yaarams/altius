import type { ChatResponse } from '../../api/types';

export interface CannedAnswer {
  queryPattern: string; // substring match (lowercase)
  response: ChatResponse;
}

export const CHAT_CANNED_ANSWERS: CannedAnswer[] = [
  {
    queryPattern: 'total value',
    response: {
      answer:
        'As of Q3 2024, your aggregate portfolio value across all Altius funds is approximately $598.65M USD equivalent. The largest position is Altius Real Assets Fund I at $214M, followed by Altius Venture Fund III at $142.5M.',
      citations: [
        {
          file_id: 'cas-001',
          file_name: 'AVF3_Q3_2024_Capital_Account_Statement.pdf',
          period: 'Q3 2024',
        },
        {
          file_id: 'cas-005',
          file_name: 'ARAF1_Q3_2024_Capital_Account_Statement.pdf',
          period: 'Q3 2024',
        },
        {
          file_id: 'cas-003',
          file_name: 'AGE2_Q3_2024_Capital_Account_Statement.pdf',
          period: 'Q3 2024',
        },
      ],
      out_of_context: false,
    },
  },
  {
    queryPattern: 'performance',
    response: {
      answer:
        'Based on the annual reports available, Altius Venture Fund III has delivered a gross IRR of 22.4% since inception through FY 2023. Altius Real Assets Fund I has generated a 14.1% net return. Detailed vintage-year performance data is available in the respective annual reports.',
      citations: [
        {
          file_id: 'rpt-004',
          file_name: 'AVF3_Annual_2023_Report.pdf',
          period: 'FY 2023',
        },
        {
          file_id: 'rpt-014',
          file_name: 'ARAF1_Annual_2023_Report.pdf',
          period: 'FY 2023',
        },
      ],
      out_of_context: false,
    },
  },
  {
    queryPattern: 'dividend',
    response: {
      answer:
        "I don't have information about dividend distributions in the documents that have been indexed. Private equity funds typically distribute capital rather than dividends. If you are looking for distribution history, that information may be in documents not yet uploaded to the platform.",
      citations: [],
      out_of_context: true,
    },
  },
  {
    queryPattern: 'esg',
    response: {
      answer:
        'ESG reports for Altius Venture Fund III, Altius Growth Equity II, and Altius Real Assets Fund I are available for FY 2023. Key highlights include: 68% of portfolio companies have formal carbon reduction targets, and the funds achieved a weighted average UNPRI score of B+.',
      citations: [
        {
          file_id: 'rpt-021',
          file_name: 'AVF3_ESG_Report_2023.pdf',
          period: 'FY 2023',
        },
        {
          file_id: 'rpt-022',
          file_name: 'AGE2_ESG_Report_2023.pdf',
          period: 'FY 2023',
        },
        {
          file_id: 'rpt-023',
          file_name: 'ARAF1_ESG_Report_2023.pdf',
          period: 'FY 2023',
        },
      ],
      out_of_context: false,
    },
  },
];

export const CHAT_DEFAULT_RESPONSE: ChatResponse = {
  answer:
    'Based on the documents indexed, I found relevant information in your fund reports and capital account statements. Please refine your question for more specific details.',
  citations: [
    {
      file_id: 'rpt-001',
      file_name: 'AVF3_Q3_2024_Quarterly_Report.pdf',
      period: 'Q3 2024',
    },
  ],
  out_of_context: false,
};
