import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  docsSidebar: [
    'getting-started',
    {
      type: 'category',
      label: 'Guides',
      collapsed: false,
      items: [
        'guides/crud/crud',
        'guides/crud/cdt-list',
        'guides/crud/cdt-map',
        'guides/crud/numpy-batch',
        'guides/query-scan/query-scan',
        'guides/query-scan/expression-filters',
        'guides/config/client-config',
        'guides/config/performance-tuning',
        'guides/config/migration',
        'guides/admin/admin',
        'guides/admin/udf',
        'guides/admin/error-handling',
      ],
    },
    {
      type: 'category',
      label: 'API Reference',
      collapsed: false,
      items: [
        'api/client',
        'api/types',
        'api/exceptions',
        'api/constants',
        'api/query-scan',
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
          ],
        },
      ],
    },
    {
      type: 'category',
      label: 'Performance',
      items: [
        'performance/overview',
        'performance/benchmark-results',
        'performance/numpy-benchmark-results',
      ],
    },
    'contributing',
  ],
};

export default sidebars;
