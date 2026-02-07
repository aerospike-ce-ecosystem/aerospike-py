import type {ReactNode} from 'react';
import clsx from 'clsx';
import Heading from '@theme/Heading';
import styles from './HomepageFeatures.module.css';

type FeatureItem = {
  title: string;
  description: ReactNode;
};

const FeatureList: FeatureItem[] = [
  {
    title: 'Sync & Async',
    description: (
      <>
        Both <code>Client</code> and <code>AsyncClient</code> are available.
        The async client uses Tokio runtime for native async I/O.
      </>
    ),
  },
  {
    title: 'Full CRUD + Batch',
    description: (
      <>
        put, get, select, exists, remove, touch, increment, append, prepend
        — plus batch operations for bulk reads and writes.
      </>
    ),
  },
  {
    title: 'Query/Scan & Expressions',
    description: (
      <>
        Secondary index queries, full namespace scans, and 104+ composable
        expression filter functions for server-side filtering.
      </>
    ),
  },
  {
    title: 'CDT Operations',
    description: (
      <>
        45+ atomic List operations and 27+ atomic Map operations
        for complex data type manipulation.
      </>
    ),
  },
  {
    title: 'Type Safety',
    description: (
      <>
        Complete <code>.pyi</code> type stubs for full IDE autocompletion
        and type checking support.
      </>
    ),
  },
  {
    title: 'Drop-in Replacement',
    description: (
      <>
        API-compatible with the official aerospike-client-python.
        Migrate by changing the import.
      </>
    ),
  },
];

function Feature({title, description}: FeatureItem) {
  return (
    <div className={clsx('col col--4')}>
      <div className={clsx('text--center padding-horiz--md padding-vert--md', styles.featureCard)}>
        <Heading as="h3">{title}</Heading>
        <p>{description}</p>
      </div>
    </div>
  );
}

export default function HomepageFeatures(): ReactNode {
  return (
    <section className={styles.features}>
      <div className="container">
        <div className="row">
          {FeatureList.map((props, idx) => (
            <Feature key={idx} {...props} />
          ))}
        </div>
      </div>
    </section>
  );
}
