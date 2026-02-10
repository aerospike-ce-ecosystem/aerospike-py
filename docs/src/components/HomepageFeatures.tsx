import type {ReactNode} from 'react';
import Heading from '@theme/Heading';
import CodeBlock from '@theme/CodeBlock';
import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';
import styles from './HomepageFeatures.module.css';

const CODE_DROP_IN = `- import aerospike
+ import aerospike_py as aerospike

config = {'hosts': [('localhost', 3000)]}
client = aerospike.client(config).connect()

key = ('test', 'demo', 'key1')
client.put(key, {'name': 'Alice', 'age': 30})
_, _, bins = client.get(key)
client.close()`;

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

function DropInReplacementSection() {
  return (
    <section className={styles.section}>
      <div className="container">
        <div className={styles.sectionHeader}>
          <Heading as="h2" className={styles.sectionTitle}>
            Drop-in Replacement for Official Client
          </Heading>
          <p className={styles.sectionSubtitle}>
            Just change the import — your existing code works as-is
          </p>
        </div>
        <div className={styles.dropInBlock}>
          <CodeBlock language="diff">
            {CODE_DROP_IN}
          </CodeBlock>
        </div>
      </div>
    </section>
  );
}

function SyncAsyncSection() {
  return (
    <section className={styles.section}>
      <div className="container">
        <div className={styles.sectionHeader}>
          <Heading as="h2" className={styles.sectionTitle}>
            Sync & Async Support
          </Heading>
          <p className={styles.sectionSubtitle}>
            Both Client and AsyncClient are supported
          </p>
        </div>
        <div className={styles.tabsSection}>
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
    </section>
  );
}

export default function HomepageFeatures(): ReactNode {
  return (
    <>
      <DropInReplacementSection />
      <SyncAsyncSection />
    </>
  );
}
