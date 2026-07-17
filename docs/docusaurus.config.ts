import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

const config: Config = {
  stylesheets: [
    {
      rel: 'preconnect',
      href: 'https://fonts.googleapis.com',
    },
    {
      rel: 'preconnect',
      href: 'https://fonts.gstatic.com',
      crossorigin: 'anonymous',
    },
    {
      href: 'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@600;700;800&family=JetBrains+Mono:wght@400;500&display=swap',
      rel: 'stylesheet',
    },
  ],
  title: 'aerospike-py',
  tagline: 'High-performance Aerospike Python Client built in Rust (Sync/Async)',
  favicon: 'img/favicon.ico',

  future: {
    v4: true,
  },

  markdown: {
    mermaid: true,
    hooks: {
      onBrokenMarkdownLinks: 'throw',
    },
  },
  themes: ['@docusaurus/theme-mermaid'],

  url: 'https://aerospike-ce-ecosystem.github.io',
  baseUrl: '/aerospike-py/',

  organizationName: 'aerospike-ce-ecosystem',
  projectName: 'aerospike-py',

  onBrokenLinks: 'throw',

  i18n: {
    defaultLocale: 'en',
    locales: ['en', 'ko'],
    localeConfigs: {
      en: { label: 'English' },
      ko: { label: '한국어' },
    },
  },

  presets: [
    [
      'classic',
      {
        docs: {
          sidebarPath: './sidebars.ts',
          editUrl: ({locale, docPath}) => {
            const sourcePath =
              locale === 'ko'
                ? `docs/i18n/ko/docusaurus-plugin-content-docs/current/${docPath}`
                : `docs/docs/${docPath}`;
            return `https://github.com/aerospike-ce-ecosystem/aerospike-py/edit/main/${sourcePath}`;
          },
          showLastUpdateTime: true,
        },
        blog: false,
        theme: {
          customCss: './src/css/custom.css',
        },
      } satisfies Preset.Options,
    ],
  ],

  themeConfig: {
    image: 'img/social-preview.png',
    metadata: [
      {name: 'keywords', content: 'aerospike, python, rust, pyo3, async, database, nosql, client'},
    ],
    colorMode: {
      respectPrefersColorScheme: true,
    },
    navbar: {
      title: 'aerospike-py',
      logo: {
        alt: '',
        src: 'img/icon.svg',
      },
      items: [
        {
          type: 'docSidebar',
          sidebarId: 'docsSidebar',
          position: 'left',
          label: 'Docs',
        },
        {to: '/releases', label: 'Releases', position: 'left'},
        {
          type: 'localeDropdown',
          position: 'right',
        },
        {
          href: 'https://github.com/aerospike-ce-ecosystem/aerospike-py',
          label: 'GitHub',
          position: 'right',
        },
      ],
    },
    footer: {
      style: 'dark',
      links: [
        {
          title: 'Docs',
          items: [
            {
              label: 'Getting Started',
              to: '/docs/getting-started',
            },
            {
              label: 'API Reference',
              to: '/docs/api/client',
            },
            {
              label: 'Guides',
              to: '/docs/guides/write',
            },
            {
              label: 'Performance',
              to: '/docs/performance/overview',
            },
          ],
        },
        {
          title: 'More',
          items: [
            {
              label: 'Releases',
              to: '/releases',
            },
            {
              label: 'GitHub',
              href: 'https://github.com/aerospike-ce-ecosystem/aerospike-py',
            },
          ],
        },
      ],
      copyright: `Copyright © ${new Date().getFullYear()} aerospike-py. Built with Docusaurus.`,
    },
    prism: {
      theme: prismThemes.oneDark,
      darkTheme: prismThemes.oneDark,
      additionalLanguages: ['python', 'bash', 'lua', 'toml', 'json'],
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
