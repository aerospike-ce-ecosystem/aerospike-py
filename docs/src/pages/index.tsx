import {type ReactNode, useCallback, useState} from 'react';
import clsx from 'clsx';
import Link from '@docusaurus/Link';
import Translate, {translate} from '@docusaurus/Translate';
import useBaseUrl from '@docusaurus/useBaseUrl';
import Layout from '@theme/Layout';
import HomepageFeatures from '@site/src/components/HomepageFeatures';
import styles from './index.module.css';

type CopyState = 'idle' | 'copied' | 'error';

function CopyBlock({text, className}: {text: string; className?: string}) {
  const [copyState, setCopyState] = useState<CopyState>('idle');

  const handleCopy = useCallback(async () => {
    try {
      if (!navigator.clipboard) {
        throw new Error('Clipboard API is unavailable');
      }
      await navigator.clipboard.writeText(text);
      setCopyState('copied');
    } catch {
      setCopyState('error');
    }

    window.setTimeout(() => setCopyState('idle'), 2000);
  }, [text]);

  const copyLabel =
    copyState === 'copied'
      ? translate({id: 'homepage.install.copied', message: 'Copied'})
      : copyState === 'error'
        ? translate({id: 'homepage.install.copyError', message: 'Copy failed'})
        : translate({id: 'homepage.install.copy', message: 'Copy'});

  return (
    <div className={clsx(styles.installCommand, className)}>
      <span className={styles.prompt} aria-hidden="true">$</span>
      <code>{text}</code>
      <button
        className={styles.copyButton}
        onClick={handleCopy}
        aria-label={translate({
          id: 'homepage.install.copyAriaLabel',
          message: 'Copy the install command',
        })}
        title={copyLabel}>
        <span aria-live="polite">{copyLabel}</span>
      </button>
    </div>
  );
}

function HeroSection() {
  const iconSrc = useBaseUrl('/img/icon.svg');

  return (
    <header className={styles.heroBanner}>
      <div className={clsx('container', styles.heroContent)}>
        <img className={styles.heroLogo} src={iconSrc} alt="" aria-hidden="true" />
        <div className={styles.heroBadge}>
          <Translate id="homepage.hero.badge">Built with Rust + PyO3</Translate>
        </div>
        <h1 className={styles.heroTitle}>
          <Translate
            id="homepage.hero.title"
            values={{
              fastest: (
                <span className={styles.heroTitleAccent}>
                  <Translate id="homepage.hero.fastest">Fastest</Translate>
                </span>
              ),
            }}>
            {'The {fastest} Aerospike Python Client'}
          </Translate>
        </h1>
        <p className={styles.heroSubtitle}>
          <Translate id="homepage.hero.subtitle">
            High-performance Aerospike Python client built in Rust — native performance,
            zero extra dependencies, full Sync &amp; Async support.
          </Translate>
        </p>
        <div className={styles.buttons}>
          <Link className={clsx('button button--lg', styles.ctaPrimary)} to="/docs/getting-started">
            <Translate id="homepage.hero.getStarted">Get Started</Translate>
            <span aria-hidden="true"> →</span>
          </Link>
          <Link className={clsx('button button--lg', styles.ctaSecondary)} to="/docs/performance/overview">
            <Translate id="homepage.hero.viewBenchmarks">View Benchmarks</Translate>
          </Link>
        </div>
        <CopyBlock text="pip install aerospike-py" />
      </div>
    </header>
  );
}

function StatsBar() {
  const stats = [
    {value: '2×', label: translate({id: 'homepage.stats.faster', message: 'Faster than Official'})},
    {value: '0', label: translate({id: 'homepage.stats.dependencies', message: 'Python Dependencies'})},
    {value: 'Sync + Async', label: translate({id: 'homepage.stats.apis', message: 'Both APIs'})},
    {value: 'PyO3', label: translate({id: 'homepage.stats.binding', message: 'Native Rust Binding'})},
  ];

  return (
    <div className={styles.statsBar}>
      {stats.map((stat) => (
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
      title={translate({id: 'homepage.meta.title', message: 'Aerospike Python client'})}
      description={translate({
        id: 'homepage.meta.description',
        message: 'High-performance Aerospike Python Client built with PyO3 and Rust — 2× faster, zero dependencies, Sync and Async.',
      })}>
      <HeroSection />
      <StatsBar />
      <main>
        <HomepageFeatures />
      </main>
    </Layout>
  );
}
