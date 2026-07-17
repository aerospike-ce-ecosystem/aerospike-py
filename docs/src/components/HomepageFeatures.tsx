import type {ReactNode} from 'react';
import {translate} from '@docusaurus/Translate';
import CodeBlock from '@theme/CodeBlock';
import Heading from '@theme/Heading';
import TabItem from '@theme/TabItem';
import Tabs from '@theme/Tabs';
import styles from './HomepageFeatures.module.css';

const CODE_SYNC = `from aerospike_py import Client

with Client({"hosts": [("127.0.0.1", 3000)]}).connect() as client:
    key = ("test", "users", "ada")
    client.put(key, {"name": "Ada", "active": True})
    record = client.get(key)
    print(record.bins)`;

const CODE_ASYNC = `import asyncio
from aerospike_py import AsyncClient

async def main() -> None:
    async with AsyncClient({"hosts": [("127.0.0.1", 3000)]}) as client:
        await client.connect()
        key = ("test", "users", "ada")
        await client.put(key, {"name": "Ada", "active": True})
        record = await client.get(key)
        print(record.bins)

asyncio.run(main())`;

function FeatureCardsSection() {
  const cards = [
    {
      key: 'rust',
      title: translate({id: 'homepage.feature.rust.title', message: 'Rust Performance'}),
      description: translate({
        id: 'homepage.feature.rust.description',
        message: 'Native binary via PyO3 — zero Python overhead on the hot path.',
      }),
    },
    {
      key: 'sync-async',
      title: translate({id: 'homepage.feature.async.title', message: 'Sync & Async'}),
      description: translate({
        id: 'homepage.feature.async.description',
        message: 'Both Client and AsyncClient. Works with FastAPI, Django, Gunicorn, and more.',
      }),
    },
    {
      key: 'dependencies',
      title: translate({id: 'homepage.feature.dependencies.title', message: 'Zero Python Deps'}),
      description: translate({
        id: 'homepage.feature.dependencies.description',
        message: 'Ships as a compiled wheel. No native C extensions to install separately.',
      }),
    },
    {
      key: 'types',
      title: translate({id: 'homepage.feature.types.title', message: 'Full Type Hints'}),
      description: translate({
        id: 'homepage.feature.types.description',
        message: 'PEP 561 compliant with bundled .pyi stubs. First-class IDE auto-complete.',
      }),
    },
    {
      key: 'numpy',
      title: translate({id: 'homepage.feature.numpy.title', message: 'NumPy Support'}),
      description: translate({
        id: 'homepage.feature.numpy.description',
        message: 'Batch results directly as NumPy arrays — ideal for analytics workloads.',
      }),
    },
  ];

  return (
    <section className={styles.featureCardsSection}>
      <div className="container">
        <div className={styles.sectionHeader}>
          <Heading as="h2" className={styles.sectionTitle}>
            {translate({id: 'homepage.feature.title', message: 'Why aerospike-py?'})}
          </Heading>
          <p className={styles.sectionSubtitle}>
            {translate({
              id: 'homepage.feature.subtitle',
              message: 'Built for production workloads where every millisecond counts',
            })}
          </p>
        </div>
        <div className={styles.featureCardsGrid}>
          {cards.map((card) => (
            <article key={card.key} className={styles.featureCard}>
              <Heading as="h3" className={styles.featureCardTitle}>{card.title}</Heading>
              <p className={styles.featureCardDesc}>{card.description}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

function SyncAsyncSection() {
  return (
    <section className={styles.section}>
      <div className="container">
        <div className={styles.twoColLayout}>
          <div className={styles.twoColText}>
            <Heading as="h2">
              {translate({id: 'homepage.api.title', message: 'Sync & Async Support'})}
            </Heading>
            <p>
              {translate({
                id: 'homepage.api.description',
                message: 'Use Client for synchronous workloads or AsyncClient for async frameworks like FastAPI, Starlette, and Django Channels — same API, both fully supported.',
              })}
            </p>
          </div>
          <div className={styles.codeTabs}>
            <Tabs>
              <TabItem value="sync" label={translate({id: 'homepage.api.syncTab', message: 'Sync'})} default>
                <CodeBlock language="python">{CODE_SYNC}</CodeBlock>
              </TabItem>
              <TabItem value="async" label={translate({id: 'homepage.api.asyncTab', message: 'Async'})}>
                <CodeBlock language="python">{CODE_ASYNC}</CodeBlock>
              </TabItem>
            </Tabs>
          </div>
        </div>
      </div>
    </section>
  );
}

export default function HomepageFeatures(): ReactNode {
  return (
    <>
      <FeatureCardsSection />
      <SyncAsyncSection />
    </>
  );
}
