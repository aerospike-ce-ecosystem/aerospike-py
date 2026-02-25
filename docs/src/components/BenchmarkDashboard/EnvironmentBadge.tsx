import React from 'react';
import chartStyles from './styles/Charts.module.css';
import type {EnvironmentConfig} from './types';

interface Props {
  env: EnvironmentConfig;
}

export default function EnvironmentBadge({env}: Props) {
  const parts = [
    env.platform,
    `Python ${env.python_version}`,
    `${env.count.toLocaleString()} ops`,
    `${env.rounds} rounds`,
  ];

  return (
    <div className={chartStyles.envBadgeWrap}>
      {parts.map((part, i) => (
        <span key={i} className={chartStyles.envBadge}>{part}</span>
      ))}
    </div>
  );
}
