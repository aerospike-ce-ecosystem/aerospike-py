import {type ReactNode, useState, useCallback} from 'react';
import clsx from 'clsx';
import Link from '@docusaurus/Link';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import Layout from '@theme/Layout';
import Heading from '@theme/Heading';
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

function HomepageHeader() {
  const {siteConfig} = useDocusaurusContext();
  return (
    <header className={clsx('hero hero--primary', styles.heroBanner)}>
      <div className="container">
        <Heading as="h1" className="hero__title">
          {siteConfig.title}
        </Heading>
        <p className="hero__subtitle">{siteConfig.tagline}</p>
        <div className={styles.buttons}>
          <Link
            className="button button--secondary button--lg"
            to="/docs/getting-started">
            Get Started
          </Link>
          <Link
            className="button button--secondary button--outline button--lg"
            to="/releases">
            Releases
          </Link>
        </div>
        <CopyBlock text="pip install aerospike-py" />
        <p className={styles.agentLabel}>
          For AI Agents — copy this prompt to give your agent full context:
        </p>
        <CopyBlock className={styles.agentPrompt} text="Fetch and read https://kimsoungryoul.github.io/aerospike-py/llms-full.txt to understand the aerospike-py Python client API, then write code based on that documentation." />
      </div>
    </header>
  );
}

export default function Home(): ReactNode {
  return (
    <Layout
      title="Home"
      description="Aerospike Python Client built with PyO3 + Rust">
      <HomepageHeader />
      <main>
        <HomepageFeatures />
      </main>
    </Layout>
  );
}
