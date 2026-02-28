import {type ReactNode, useState, useCallback} from 'react';
import clsx from 'clsx';
import Link from '@docusaurus/Link';
import Layout from '@theme/Layout';
import HomepageFeatures from '@site/src/components/HomepageFeatures';
import styles from './index.module.css';

function CopyBlock({text, className}: {text: string; className?: string}) {
  const [copied, setCopied] = useState(false);
  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [text]);
  return (
    <div className={clsx(styles.installCommand, className)}>
      <code>{text}</code>
      <button
        className={styles.copyButton}
        onClick={handleCopy}
        aria-label="Copy to clipboard"
        title="Copy to clipboard">
        {copied ? '✓' : '⧉'}
      </button>
    </div>
  );
}

const STATS = [
  {value: '2×', label: 'Faster than Official'},
  {value: '0', label: 'Python Dependencies'},
  {value: 'Sync + Async', label: 'Both APIs'},
  {value: 'PyO3', label: 'Native Rust Binding'},
];

function HeroSection() {
  return (
    <header className={styles.heroBanner}>
      <div className={clsx('container', styles.heroContent)}>
        <div className={styles.heroBadge}>
          <span>⚡</span>
          <span>Built with Rust + PyO3</span>
        </div>
        <h1 className={styles.heroTitle}>
          The <span className={styles.heroTitleAccent}>Fastest</span>{' '}
          Aerospike Python Client
        </h1>
        <p className={styles.heroSubtitle}>
          High-performance Aerospike Python client built in Rust —
          native performance, zero extra dependencies, full Sync &amp; Async support.
        </p>
        <div className={styles.buttons}>
          <Link
            className={clsx('button button--lg', styles.ctaPrimary)}
            to="/docs/getting-started">
            Get Started →
          </Link>
          <Link
            className={clsx('button button--outline button--lg', styles.ctaSecondary)}
            to="/docs/performance/overview">
            View Benchmarks
          </Link>
        </div>
        <CopyBlock text="pip install aerospike-py" />
      </div>
    </header>
  );
}

function StatsBar() {
  return (
    <div className={styles.statsBar}>
      {STATS.map((stat) => (
        <div key={stat.label} className={styles.statItem}>
          <span className={styles.statValue}>{stat.value}</span>
          <span className={styles.statLabel}>{stat.label}</span>
        </div>
      ))}
    </div>
  );
}

export default function Home(): ReactNode {
  return (
    <Layout
      title="Home"
      description="High-performance Aerospike Python Client built with PyO3 + Rust — 2× faster, zero dependencies, Sync &amp; Async">
      <HeroSection />
      <StatsBar />
      <main>
        <HomepageFeatures />
      </main>
    </Layout>
  );
}
