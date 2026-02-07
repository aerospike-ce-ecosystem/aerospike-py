import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

const config: Config = {
  title: 'aerospike-py',
  tagline: 'High-performance Aerospike Python Client built in Rust (Sync/Async)',
  favicon: 'img/favicon.svg',

  future: {
    v4: true,
  },

  url: 'https://kimsoungryoul.github.io',
  baseUrl: '/aerospike-py/',

  organizationName: 'KimSoungRyoul',
  projectName: 'aerospike-py',

  onBrokenLinks: 'throw',
  onBrokenMarkdownLinks: 'warn',

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
          editUrl:
            'https://github.com/KimSoungRyoul/aerospike-py/tree/main/docs/',
          showLastUpdateTime: true,
        },
        blog: {
          showReadingTime: true,
          editUrl:
            'https://github.com/KimSoungRyoul/aerospike-py/tree/main/docs/',
        },
        theme: {
          customCss: './src/css/custom.css',
        },
      } satisfies Preset.Options,
    ],
  ],

  themeConfig: {
    metadata: [
      {name: 'keywords', content: 'aerospike, python, rust, pyo3, async, database, nosql, client'},
    ],
    colorMode: {
      respectPrefersColorScheme: true,
    },
    navbar: {
      title: 'aerospike-py',
      logo: {
        alt: 'aerospike-py Logo',
        src: 'img/logo.svg',
      },
      items: [
        {
          type: 'docSidebar',
          sidebarId: 'docsSidebar',
          position: 'left',
          label: 'Docs',
        },
        {to: '/blog', label: 'Blog', position: 'left'},
        {to: '/releases', label: 'Releases', position: 'left'},
        {
          type: 'localeDropdown',
          position: 'right',
        },
        {
          href: 'https://github.com/KimSoungRyoul/aerospike-py',
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
              to: '/docs/guides/crud',
            },
          ],
        },
        {
          title: 'More',
          items: [
            {
              label: 'Blog',
              to: '/blog',
            },
            {
              label: 'Releases',
              to: '/releases',
            },
            {
              label: 'GitHub',
              href: 'https://github.com/KimSoungRyoul/aerospike-py',
            },
          ],
        },
      ],
      copyright: `Copyright © ${new Date().getFullYear()} aerospike-py. Built with Docusaurus.`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
      additionalLanguages: ['python', 'bash', 'lua', 'toml', 'json'],
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
