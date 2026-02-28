import type {ReactNode} from 'react';
import Heading from '@theme/Heading';
import CodeBlock from '@theme/CodeBlock';
import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';
import styles from './HomepageFeatures.module.css';

/* ── Feature Card Data ───────────────────────────────────── */
const FEATURE_CARDS = [
  {
    icon: '🦀',
    title: 'Rust Performance',
    desc: 'Native binary via PyO3 — zero Python overhead on the hot path.',
  },
  {
    icon: '⚡',
    title: 'Sync & Async',
    desc: 'Both Client and AsyncClient. Works with FastAPI, Django, Gunicorn, and more.',
  },
  {
    icon: '📦',
    title: 'Zero Python Deps',
    desc: 'Ships as a compiled wheel. No native C extensions to install separately.',
  },
  {
    icon: '🔍',
    title: 'Full Type Hints',
    desc: 'PEP 561 compliant with bundled .pyi stubs. First-class IDE auto-complete.',
  },
  {
    icon: '🔢',
    title: 'NumPy Support',
    desc: 'Batch results directly as NumPy arrays — ideal for analytics workloads.',
  },
];

/* ── Code Snippets ───────────────────────────────────────── */
const CODE_SYNC = `from aerospike_py import Client

client = Client({'hosts': [('localhost', 3000)]})
client.connect()

client.put(('test','demo','key1'), {'name': 'Alice', 'age': 30})
_, _, bins = client.get(('test','demo','key1'))
print(bins)  # {'name': 'Alice', 'age': 30}

client.close()`;

const CODE_ASYNC = `import asyncio
from aerospike_py import AsyncClient

async def main():
    client = AsyncClient({'hosts': [('localhost', 3000)]})
    await client.connect()

    await client.put(('test','demo','key1'), {'name': 'Alice', 'age': 30})
    _, _, bins = await client.get(('test','demo','key1'))
    print(bins)  # {'name': 'Alice', 'age': 30}

    await client.close()

asyncio.run(main())`;

/* ── Feature Cards Section ───────────────────────────────── */
function FeatureCardsSection() {
  return (
    <section className={styles.featureCardsSection}>
      <div className="container">
        <div className={styles.sectionHeader}>
          <Heading as="h2" className={styles.sectionTitle}>
            Why aerospike-py?
          </Heading>
          <p className={styles.sectionSubtitle}>
            Built for production workloads where every millisecond counts
          </p>
        </div>
        <div className={styles.featureCardsGrid}>
          {FEATURE_CARDS.map((card) => (
            <div key={card.title} className={styles.featureCard}>
              <span className={styles.featureCardIcon}>{card.icon}</span>
              <div className={styles.featureCardTitle}>{card.title}</div>
              <p className={styles.featureCardDesc}>{card.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ── Sync & Async Section ────────────────────────────────── */
function SyncAsyncSection() {
  return (
    <section className={styles.section}>
      <div className="container">
        <div className={styles.twoColLayout}>
          <div className={styles.twoColText}>
            <Heading as="h2">
              Sync &amp; Async Support
            </Heading>
            <p>
              Use <code>Client</code> for synchronous workloads or{' '}
              <code>AsyncClient</code> for async frameworks like FastAPI,
              Starlette, and Django Channels — same API, both fully supported.
            </p>
          </div>
          <div>
            <Tabs>
              <TabItem value="sync" label="SyncClient" default>
                <CodeBlock language="python">
                  {CODE_SYNC}
                </CodeBlock>
              </TabItem>
              <TabItem value="async" label="AsyncClient">
                <CodeBlock language="python">
                  {CODE_ASYNC}
                </CodeBlock>
              </TabItem>
            </Tabs>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ── Main Export ─────────────────────────────────────────── */
export default function HomepageFeatures(): ReactNode {
  return (
    <>
      <FeatureCardsSection />
      <SyncAsyncSection />
    </>
  );
}
