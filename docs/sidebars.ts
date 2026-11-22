import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  docsSidebar: [
    'getting-started',
    {
      type: 'category',
      label: 'Guides',
      collapsed: false,
      items: [
        {
          type: 'category',
          label: 'Connection',
          items: [
            'guides/config/client-config',
            'guides/config/performance-tuning',
          ],
        },
        {
          type: 'category',
          label: 'Records',
          items: [
            'guides/crud/write',
            'guides/crud/read',
            'guides/crud/operations',
          ],
        },
        {
          type: 'category',
          label: 'Query & Scan',
          items: [
            'guides/query-scan/query-scan',
            'guides/query-scan/expression-filters',
          ],
        },
        {
          type: 'category',
          label: 'Batch & NumPy',
          items: [
            'guides/crud/numpy-batch',
            'guides/crud/numpy-batch-write',
            'guides/crud/numpy-guide',
          ],
        },
        {
          type: 'category',
          label: 'Administration',
          items: [
            'guides/admin/admin',
            'guides/admin/udf',
          ],
        },
        'guides/troubleshooting',
        'guides/admin/error-handling',
        'guides/version-compatibility',
        'guides/api-comparison',
        'guides/architecture',
      ],
    },
    {
      type: 'category',
      label: 'Integrations',
      items: [
        'integrations/fastapi',
        {
          type: 'category',
          label: 'Observability',
          items: [
            'integrations/observability/logging',
            'integrations/observability/metrics',
            'integrations/observability/tracing',
            'integrations/observability/internal-stage-metrics',
          ],
        },
      ],
    },
    {
      type: 'category',
      label: 'Performance',
      items: [
        {
          type: 'category',
          label: '0.15 benchmarks',
          link: {type: 'doc', id: 'performance/overview'},
          items: [
            'performance/client-comparison',
            'performance/ncloud-equal-rate',
            'performance/async-stream-profile',
          ],
        },
        {
          type: 'category',
          label: 'Benchmarks before 0.14',
          link: {type: 'doc', id: 'performance/production-benchmark'},
          items: [
            'performance/isolated-benchmark',
            'performance/bottleneck-analysis',
          ],
        },
      ],
    },
    {
      type: 'category',
      label: 'API Reference',
      items: [
        'api/client',
        'api/types',
        'api/exceptions',
        'api/constants',
        'api/query-scan',
      ],
    },
    'contributing',
    'faq',
  ],
};

export default sidebars;
