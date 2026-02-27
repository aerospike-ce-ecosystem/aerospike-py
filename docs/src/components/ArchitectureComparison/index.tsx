import React, { useState, useCallback } from 'react';
import styles from './styles.module.css';

/* ── Slider data ─────────────────────────────────── */
const CONC_DATA = [
  {
    conc: '1',
    sTP: 6500, aTP: 6500, rTP: 12500,
    sTH: 1, aTH: 1, rTH: 4,
    sMem: 0.1, aMem: 8, rMem: 2,
    insight:
      '<b>Sync \u2248 Async</b> \u2014 동시 요청 1개에서는 executor 오버헤드 때문에 Sync가 오히려 비슷. aerospike-py만 1.9\u00d7 빠름.',
  },
  {
    conc: '10',
    sTP: 6500, aTP: 45000, rTP: 100000,
    sTH: 1, aTH: 10, rTH: 4,
    sMem: 0.1, aMem: 80, rMem: 3,
    insight:
      '<b>Sync 정체 시작.</b> 순차 처리라 throughput 변화 없음. Async는 10 thread로 확장, aerospike-py는 2.2\u00d7 앞섬.',
  },
  {
    conc: '100',
    sTP: 6500, aTP: 120000, rTP: 350000,
    sTH: 1, aTH: 36, rTH: 4,
    sMem: 0.1, aMem: 288, rMem: 5,
    insight:
      '<b>Sync 완전 뒤처짐.</b> Async 스레드풀 거의 포화. GIL 경합 선형 증가. aerospike-py 2.9\u00d7 리드.',
  },
  {
    conc: '1,000',
    sTP: 6500, aTP: 150000, rTP: 500000,
    sTH: 1, aTH: 36, rTH: 4,
    sMem: 0.1, aMem: 288, rMem: 15,
    insight:
      '<b>Async 스레드풀 포화</b> \u2014 964개 큐 대기. Sync는 999개 대기. aerospike-py만 전부 동시 처리.',
  },
  {
    conc: '10,000',
    sTP: 6500, aTP: 150000, rTP: 550000,
    sTH: 1, aTH: 36, rTH: 4,
    sMem: 0.1, aMem: 288, rMem: 50,
    insight:
      '<b>aerospike-py 독주.</b> Sync 6.5K vs Async 150K vs aerospike-py 550K. 격차 최대.',
  },
];
const MAX_TP = 550000;
const MAX_TH = 100;
const MAX_MEM = 500;

function fmtOps(n: number) {
  return n >= 1e6
    ? `${(n / 1e6).toFixed(1)}M`
    : n >= 1e3
      ? `${(n / 1e3).toFixed(0)}K`
      : String(n);
}
function fmtMem(m: number) {
  return m >= 1e3
    ? `${(m / 1e3).toFixed(1)}GB`
    : m < 1
      ? '~0MB'
      : `${m}MB`;
}

/* ── Sub-components ──────────────────────────────── */

function FlowStep({
  num,
  label,
  variant,
}: {
  num: number;
  label: React.ReactNode;
  variant: 'bad' | 'good' | 'neutral';
}) {
  const cls =
    variant === 'bad'
      ? styles.stepBad
      : variant === 'good'
        ? styles.stepGood
        : styles.stepNeutral;
  return (
    <div className={`${styles.flowStep} ${cls}`}>
      <span className={styles.flowStepNum}>{num}</span>
      <span className={styles.flowStepLabel}>{label}</span>
    </div>
  );
}

function GilBlock({
  type,
  width,
  children,
}: {
  type: 'held' | 'free' | 'io' | 'empty' | 'tokio';
  width: string;
  children?: React.ReactNode;
}) {
  const cls = {
    held: styles.gilHeld,
    free: styles.gilFree,
    io: styles.gilIo,
    empty: styles.gilEmpty,
    tokio: styles.gilTokio,
  }[type];
  return (
    <div className={`${styles.gilBlock} ${cls}`} style={{ width }}>
      {children}
    </div>
  );
}

function MetricBar({
  label,
  pct,
  value,
}: {
  label: string;
  pct: number;
  value: string;
}) {
  return (
    <div className={styles.metricBarRow}>
      <span className={styles.metricBarLabel}>{label}</span>
      <div className={styles.metricBarTrack}>
        <div className={styles.metricBarFill} style={{ width: `${pct}%` }} />
      </div>
      <span className={styles.metricBarValue}>{value}</span>
    </div>
  );
}

/* ── Exported section components ─────────────────── */

export function RequestFlow(): React.ReactElement {
  return (
    <div className={styles.wrapper}>
      <div className={styles.triGrid}>
        {/* Sync */}
        <div className={`${styles.panel} ${styles.panelSync}`}>
          <div className={styles.panelTitle}>
            OFFICIAL SYNC{' '}
            <span className={`${styles.tag} ${styles.tagSlow}`}>동기 블로킹</span>
          </div>
          <div className={styles.flow}>
            <FlowStep num={1} variant="neutral" label={<>Python &rarr; <b>C 확장 호출</b></>} />
            <div className={styles.flowArrow}>&darr;</div>
            <FlowStep num={2} variant="bad" label={<><b>GIL 해제</b> &rarr; 동기 블로킹 I/O</>} />
            <div className={styles.flowArrow}>&darr;</div>
            <FlowStep num={3} variant="bad" label={<><b>스레드 완전 정지</b> (응답 대기)</>} />
            <div className={styles.flowArrow}>&darr;</div>
            <FlowStep num={4} variant="neutral" label={<><b>GIL 획득</b> &rarr; 결과 변환 &rarr; 리턴</>} />
          </div>
          <div className={styles.flowFooter} style={{ color: 'var(--arch-red)' }}>
            호출 스레드 완전 차단 &middot; 동시 처리 불가
          </div>
        </div>

        {/* Async executor */}
        <div className={`${styles.panel} ${styles.panelAsync}`}>
          <div className={styles.panelTitle}>
            OFFICIAL ASYNC{' '}
            <span className={`${styles.tag} ${styles.tagMid}`}>스레드 위임</span>
          </div>
          <div className={styles.flow}>
            <FlowStep num={1} variant="neutral" label={<>asyncio &rarr; <b>executor.submit()</b></>} />
            <div className={styles.flowArrow}>&darr;</div>
            <FlowStep num={2} variant="bad" label={<><b>OS Thread 할당</b> (스레드풀)</>} />
            <div className={styles.flowArrow}>&darr;</div>
            <FlowStep num={3} variant="bad" label={<><b>GIL 획득</b> &rarr; C 진입 &rarr; GIL 해제</>} />
            <div className={styles.flowArrow}>&darr;</div>
            <FlowStep num={4} variant="neutral" label={<>동기 블로킹 I/O (Thread 점유)</>} />
            <div className={styles.flowArrow}>&darr;</div>
            <FlowStep num={5} variant="bad" label={<><b>GIL 재획득</b> &rarr; 변환 &rarr; Future 완료</>} />
          </div>
          <div className={styles.flowFooter} style={{ color: 'var(--arch-yellow)' }}>
            GIL 3~4회 &middot; 경계 4회 &middot; Thread 점유
          </div>
        </div>

        {/* aerospike-py */}
        <div className={`${styles.panel} ${styles.panelRust}`}>
          <div className={styles.panelTitle}>
            AEROSPIKE-PY{' '}
            <span className={`${styles.tag} ${styles.tagFast}`}>네이티브 async</span>
          </div>
          <div className={styles.flow}>
            <FlowStep num={1} variant="neutral" label={<>asyncio &rarr; <b>future_into_py()</b></>} />
            <div className={styles.flowArrow}>&darr;</div>
            <FlowStep num={2} variant="good" label={<>인자 파싱 + key 사전 변환 + <b>GIL 해제</b></>} />
            <div className={styles.flowArrow}>&darr;</div>
            <FlowStep num={3} variant="good" label={<><b>Tokio</b> epoll/kqueue 논블로킹 I/O</>} />
            <div className={styles.flowArrow}>&darr;</div>
            <FlowStep num={4} variant="good" label={<>Pending 반환 &rarr; <b>pyo3 자동 변환</b></>} />
          </div>
          <div className={styles.flowFooter} style={{ color: 'var(--arch-green)' }}>
            GIL 1회 &middot; 경계 1회 &middot; Thread 생성 없음
          </div>
        </div>
      </div>
    </div>
  );
}

export function GilTimeline(): React.ReactElement {
  return (
    <div className={styles.wrapper}>
      <div className={styles.triGrid}>
        <div className={`${styles.panel} ${styles.panelSync}`}>
          <div className={styles.panelTitle}>SYNC — GIL 타임라인</div>
          <div className={styles.gilTimeline}>
            <div className={styles.gilRow}>
              <span className={styles.gilLabel}>Main</span>
              <div className={styles.gilBlocks}>
                <GilBlock type="held" width="12%">GIL</GilBlock>
                <GilBlock type="io" width="65%">I/O 블로킹 (GIL 해제됨)</GilBlock>
                <GilBlock type="held" width="12%">GIL</GilBlock>
                <GilBlock type="empty" width="11%" />
              </div>
            </div>
          </div>
          <div className={styles.gilFooter}>
            GIL <span style={{ color: 'var(--arch-c-sync)' }}>2회</span> &middot; 하지만{' '}
            <span style={{ color: 'var(--arch-red)' }}>스레드가 블로킹</span>
          </div>
        </div>

        <div className={`${styles.panel} ${styles.panelAsync}`}>
          <div className={styles.panelTitle}>ASYNC — GIL 타임라인</div>
          <div className={styles.gilTimeline}>
            <div className={styles.gilRow}>
              <span className={styles.gilLabel}>asyncio</span>
              <div className={styles.gilBlocks}>
                <GilBlock type="held" width="12%">GIL</GilBlock>
                <GilBlock type="empty" width="60%" />
                <GilBlock type="held" width="12%">GIL</GilBlock>
                <GilBlock type="empty" width="16%" />
              </div>
            </div>
            <div className={styles.gilRow}>
              <span className={styles.gilLabel}>Thread-N</span>
              <div className={styles.gilBlocks}>
                <GilBlock type="empty" width="8%" />
                <GilBlock type="held" width="8%">GIL</GilBlock>
                <GilBlock type="io" width="48%">블로킹 I/O</GilBlock>
                <GilBlock type="held" width="10%">GIL</GilBlock>
                <GilBlock type="free" width="6%">해제</GilBlock>
                <GilBlock type="empty" width="20%" />
              </div>
            </div>
          </div>
          <div className={styles.gilFooter}>
            GIL <span style={{ color: 'var(--arch-red)' }}>3~4회</span> &middot; 스레드 간 핸드오프
          </div>
        </div>

        <div className={`${styles.panel} ${styles.panelRust}`}>
          <div className={styles.panelTitle}>AEROSPIKE-PY — GIL 타임라인</div>
          <div className={styles.gilTimeline}>
            <div className={styles.gilRow}>
              <span className={styles.gilLabel}>asyncio</span>
              <div className={styles.gilBlocks}>
                <GilBlock type="held" width="10%">GIL</GilBlock>
                <GilBlock type="free" width="80%">GIL 해제 — Pending 반환 → pyo3 자동 변환</GilBlock>
                <GilBlock type="empty" width="10%" />
              </div>
            </div>
            <div className={styles.gilRow}>
              <span className={styles.gilLabel}>Tokio</span>
              <div className={styles.gilBlocks}>
                <GilBlock type="empty" width="10%" />
                <GilBlock type="tokio" width="70%">비동기 I/O (GIL 없음)</GilBlock>
                <GilBlock type="empty" width="20%" />
              </div>
            </div>
          </div>
          <div className={styles.gilFooter}>
            GIL <span style={{ color: 'var(--arch-green)' }}>1회</span> &middot; 핸드오프 없음
          </div>
        </div>
      </div>
    </div>
  );
}

export function ConcurrencyViz(): React.ReactElement {
  return (
    <div className={styles.wrapper}>
      <div className={styles.triGrid}>
        <div className={`${styles.panel} ${styles.panelSync}`}>
          <div className={styles.panelTitle}>SYNC — 순차 처리</div>
          <div className={styles.threadViz}>
            <div className={styles.threadRow}>
              <span className={styles.threadLabel}>Main</span>
              <div className={styles.threadBarCt}>
                <div className={`${styles.threadBar} ${styles.barSync}`} style={{ left: 0, width: '5%' }}>1</div>
                <div className={`${styles.threadBar} ${styles.barSyncIo}`} style={{ left: '5%', width: '12%' }} />
                <div className={`${styles.threadBar} ${styles.barSync}`} style={{ left: '17%', width: '5%' }}>2</div>
                <div className={`${styles.threadBar} ${styles.barSyncIo}`} style={{ left: '22%', width: '12%' }} />
                <div className={`${styles.threadBar} ${styles.barSync}`} style={{ left: '34%', width: '5%' }}>3</div>
                <div className={`${styles.threadBar} ${styles.barSyncIo}`} style={{ left: '39%', width: '12%' }} />
                <div className={`${styles.threadBar} ${styles.barIdle}`} style={{ left: '51%', width: '49%' }}>&rarr; 997개 남음...</div>
              </div>
            </div>
            <div className={styles.threadRow}>
              <span className={styles.threadLabel} style={{ color: 'var(--arch-red)' }}>처리량</span>
              <div className={styles.threadBarCt}>
                <div className={`${styles.threadBar} ${styles.barBlocked}`} style={{ left: 0, width: '100%' }}>한 번에 1개씩 순차 처리 — 동시성 없음</div>
              </div>
            </div>
          </div>
          <div className={styles.panelFooter} style={{ color: 'var(--arch-red)' }}>
            1개씩 순차 처리 &middot; 1,000번째 요청은 ~150초 후 완료
          </div>
        </div>

        <div className={`${styles.panel} ${styles.panelAsync}`}>
          <div className={styles.panelTitle}>ASYNC — 16 Thread Pool</div>
          <div className={styles.threadViz}>
            <div className={styles.threadRow}>
              <span className={styles.threadLabel}>Thread-1</span>
              <div className={styles.threadBarCt}>
                <div className={`${styles.threadBar} ${styles.barCpu}`} style={{ left: 0, width: '6%' }} />
                <div className={`${styles.threadBar} ${styles.barIo}`} style={{ left: '6%', width: '68%' }}>I/O 대기</div>
                <div className={`${styles.threadBar} ${styles.barCpu}`} style={{ left: '74%', width: '6%' }} />
              </div>
            </div>
            <div className={styles.threadRow}>
              <span className={styles.threadLabel}>Thread-2</span>
              <div className={styles.threadBarCt}>
                <div className={`${styles.threadBar} ${styles.barCpu}`} style={{ left: '3%', width: '6%' }} />
                <div className={`${styles.threadBar} ${styles.barIo}`} style={{ left: '9%', width: '68%' }}>I/O 대기</div>
              </div>
            </div>
            <div className={styles.threadRow}>
              <span className={styles.threadLabel}>...</span>
              <div className={styles.threadBarCt}>
                <div className={`${styles.threadBar} ${styles.barIdle}`} style={{ left: 0, width: '100%' }}>&times; 16 threads</div>
              </div>
            </div>
            <div className={styles.threadRow}>
              <span className={styles.threadLabel} style={{ color: 'var(--arch-red)' }}>Queue</span>
              <div className={styles.threadBarCt}>
                <div className={`${styles.threadBar} ${styles.barWait}`} style={{ left: 0, width: '100%' }}>&#x23F3; 984개 대기 중...</div>
              </div>
            </div>
          </div>
          <div className={styles.panelFooter} style={{ color: 'var(--arch-yellow)' }}>
            16개 동시 처리 &middot; 984개 큐 대기
          </div>
        </div>

        <div className={`${styles.panel} ${styles.panelRust}`}>
          <div className={styles.panelTitle}>AEROSPIKE-PY — 4 Tokio Workers</div>
          <div className={styles.threadViz}>
            {['Worker-1', 'Worker-2'].map((label, i) => (
              <div className={styles.threadRow} key={label}>
                <span className={styles.threadLabel}>{label}</span>
                <div className={styles.threadBarCt}>
                  {[0, 1, 2, 3, 4, 5, 6].map((j) => (
                    <div key={j} className={`${styles.threadBar} ${styles.barTask}`} style={{ left: `${j * 12}%`, width: '11%' }}>
                      {j === 6 ? '...' : `T${j * 4 + i + 1}`}
                    </div>
                  ))}
                </div>
              </div>
            ))}
            <div className={styles.threadRow}>
              <span className={styles.threadLabel}>Worker-3~4</span>
              <div className={styles.threadBarCt}>
                <div className={`${styles.threadBar} ${styles.barTask}`} style={{ left: 0, width: '84%' }}>T3,T4,T7,T8,T11,T12,T15,T16,T19,T20...</div>
              </div>
            </div>
            <div className={styles.threadRow}>
              <span className={styles.threadLabel} style={{ color: 'var(--arch-green)' }}>Status</span>
              <div className={styles.threadBarCt}>
                <div className={`${styles.threadBar} ${styles.barStatusGood}`} style={{ left: 0, width: '100%' }}>&#x2713; 1,000개 모두 동시 처리</div>
              </div>
            </div>
          </div>
          <div className={styles.panelFooter} style={{ color: 'var(--arch-green)' }}>
            4개 워커로 전부 동시 처리 &middot; 대기열 없음
          </div>
        </div>
      </div>
    </div>
  );
}

export function ThroughputSlider(): React.ReactElement {
  const [sliderIdx, setSliderIdx] = useState(0);
  const d = CONC_DATA[sliderIdx];

  const onSlide = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) =>
      setSliderIdx(Number(e.target.value)),
    [],
  );

  return (
    <div className={styles.wrapper}>
      <div className={styles.concurrencyViz}>
        <div className={styles.concurrencyHeader}>
          <h3>동시 요청 수에 따른 Throughput</h3>
          <div className={styles.sliderGroup}>
            <span>동시 요청:</span>
            <input
              type="range"
              min={0}
              max={CONC_DATA.length - 1}
              step={1}
              value={sliderIdx}
              onChange={onSlide}
            />
            <span className={styles.sliderValue}>{d.conc}</span>
          </div>
        </div>

        <div className={styles.triBars}>
          <div className={`${styles.barGroup} ${styles.syncGroup}`}>
            <h4>OFFICIAL SYNC</h4>
            <MetricBar label="Throughput" pct={(d.sTP / MAX_TP) * 100} value={`${fmtOps(d.sTP)} ops/s`} />
            <MetricBar label="Threads" pct={(d.sTH / MAX_TH) * 100} value={`${d.sTH} thread`} />
            <MetricBar label="Memory" pct={(d.sMem / MAX_MEM) * 100} value={fmtMem(d.sMem)} />
          </div>

          <div className={`${styles.barGroup} ${styles.asyncGroup}`}>
            <h4>OFFICIAL ASYNC (executor)</h4>
            <MetricBar label="Throughput" pct={(d.aTP / MAX_TP) * 100} value={`${fmtOps(d.aTP)} ops/s`} />
            <MetricBar label="Threads" pct={(d.aTH / MAX_TH) * 100} value={`${d.aTH} threads`} />
            <MetricBar label="Memory" pct={(d.aMem / MAX_MEM) * 100} value={fmtMem(d.aMem)} />
          </div>

          <div className={`${styles.barGroup} ${styles.rustGroup}`}>
            <h4>AEROSPIKE-PY (Tokio)</h4>
            <MetricBar label="Throughput" pct={(d.rTP / MAX_TP) * 100} value={`${fmtOps(d.rTP)} ops/s`} />
            <MetricBar label="Workers" pct={(d.rTH / MAX_TH) * 100} value={`${d.rTH} workers`} />
            <MetricBar label="Memory" pct={(d.rMem / MAX_MEM) * 100} value={fmtMem(d.rMem)} />
          </div>
        </div>

        <div className={styles.sliderInsight}>
          <div dangerouslySetInnerHTML={{ __html: d.insight }} />
        </div>
      </div>
    </div>
  );
}

/* ── Beyond Benchmark: Condition Grid ────────────── */

export function ConditionGrid(): React.ReactElement {
  const rows = [
    ['네트워크', 'localhost (~0.01ms)', '네트워크 홉 (0.5~2ms)'],
    ['동시 요청', '50개', '수백~수천'],
    ['서비스 수명', '수 초', '수 시간~수 일'],
    ['다른 async 작업', '없음', 'HTTP, DB 쿼리 등 혼재'],
    ['GIL 경쟁자', 'Aerospike만', '웹 프레임워크 + ORM + ...'],
  ];
  return (
    <div className={styles.wrapper}>
      <div className={styles.condGrid}>
        <div className={styles.condHead}>조건</div>
        <div className={`${styles.condHead} ${styles.condHeadBench}`}>벤치마크</div>
        <div className={`${styles.condHead} ${styles.condHeadProd}`}>실 운영</div>
        {rows.map(([label, bench, prod]) => (
          <React.Fragment key={label}>
            <div className={styles.condCell}>{label}</div>
            <div className={styles.condCell}>{bench}</div>
            <div className={`${styles.condCell} ${styles.condCellHl}`}>{prod}</div>
          </React.Fragment>
        ))}
      </div>
    </div>
  );
}

/* ── Beyond Benchmark: Throughput Simulation ─────── */

const RT_STEPS = [0.01, 0.1, 0.5, 1, 2, 5];
const CO_STEPS = [10, 50, 100, 500, 1000, 5000];
const POOL_SIZE = 16;

function simOfficial(rtt: number, conc: number) {
  const cpu = 0.013;
  const active = Math.min(conc, POOL_SIZE);
  const raw = (active / (cpu + rtt)) * 1000;
  const gilPenalty = 1 + Math.max(0, active - 1) * 0.025;
  return { throughput: Math.floor(raw / gilPenalty), threads: active, queue: Math.max(0, conc - POOL_SIZE) };
}

function simRust(rtt: number, conc: number) {
  const cpu = 0.019;
  const workers = 4;
  const cap = (workers / cpu) * 1000;
  const ioBound = (conc / (rtt || 0.01)) * 1000;
  return { throughput: Math.floor(Math.min(cap, ioBound) * 0.92), workers, queue: 0 };
}

function fmtNum(n: number) {
  return n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? n.toLocaleString() : String(n);
}

export function ThroughputSim(): React.ReactElement {
  const [rttIdx, setRttIdx] = useState(0);
  const [concIdx, setConcIdx] = useState(1);

  const rtt = RT_STEPS[rttIdx];
  const conc = CO_STEPS[concIdx];
  const off = simOfficial(rtt, conc);
  const rus = simRust(rtt, conc);
  const oT = Math.max(50, off.throughput);
  const rT = Math.max(50, rus.throughput);
  const mx = Math.max(oT, rT);
  const ratio = rT >= oT ? (rT / oT).toFixed(1) : (oT / rT).toFixed(1);

  return (
    <div className={styles.wrapper}>
      <div className={styles.concurrencyViz}>
        <div className={styles.concurrencyHeader}>
          <h3>Throughput 시뮬레이션</h3>
        </div>
        <div style={{ fontSize: '0.72rem', color: 'var(--arch-text-muted)', marginBottom: 14 }}>
          아키텍처 모델 기반 예측 — 실 벤치마크 데이터 + 스레드/태스크 이론값
        </div>
        <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginBottom: 18 }}>
          <div className={styles.sliderGroup}>
            <span>Network RTT:</span>
            <input type="range" min={0} max={RT_STEPS.length - 1} step={1} value={rttIdx}
              onChange={(e) => setRttIdx(Number(e.target.value))} />
            <span className={styles.sliderValue}>{rtt}ms</span>
          </div>
          <div className={styles.sliderGroup}>
            <span>동시 요청:</span>
            <input type="range" min={0} max={CO_STEPS.length - 1} step={1} value={concIdx}
              onChange={(e) => setConcIdx(Number(e.target.value))} />
            <span className={styles.sliderValue}>{conc >= 1000 ? `${conc / 1000}K` : conc}</span>
          </div>
        </div>

        <div className={styles.duoGrid}>
          <div className={`${styles.duoCard} ${styles.duoCardAsync}`}>
            <div className={styles.duoCardTitle}>OFFICIAL ASYNC — run_in_executor</div>
            <div className={styles.duoRow}>
              <span className={styles.duoRowLabel}>Throughput</span>
              <span className={styles.duoRowValue}>{fmtNum(oT)} ops/s</span>
            </div>
            <div className={styles.duoBarTrack}><div className={styles.duoBarFill} style={{ width: `${(oT / mx) * 100}%` }} /></div>
            <div className={styles.duoRow}>
              <span className={styles.duoRowLabel}>Active Threads</span>
              <span className={styles.duoRowValue}>{off.threads}</span>
            </div>
            <div className={styles.duoRow}>
              <span className={styles.duoRowLabel}>Queue 대기</span>
              <span className={styles.duoRowValue} style={{ color: off.queue > 0 ? 'var(--arch-red)' : undefined }}>
                {off.queue >= 1000 ? `${Math.floor(off.queue / 1000)}K+` : off.queue}
              </span>
            </div>
          </div>

          <div className={`${styles.duoCard} ${styles.duoCardRust}`}>
            <div className={styles.duoCardTitle}>AEROSPIKE-PY — Tokio future_into_py</div>
            <div className={styles.duoRow}>
              <span className={styles.duoRowLabel}>Throughput</span>
              <span className={styles.duoRowValue}>{fmtNum(rT)} ops/s</span>
            </div>
            <div className={styles.duoBarTrack}><div className={styles.duoBarFill} style={{ width: `${(rT / mx) * 100}%` }} /></div>
            <div className={styles.duoRow}>
              <span className={styles.duoRowLabel}>Tokio Workers</span>
              <span className={styles.duoRowValue}>{rus.workers}</span>
            </div>
            <div className={styles.duoRow}>
              <span className={styles.duoRowLabel}>Queue 대기</span>
              <span className={styles.duoRowValue} style={{ color: 'var(--arch-green)' }}>0</span>
            </div>
          </div>
        </div>

        <div className={styles.duoResult}>
          <span className={styles.duoResultNum} style={rT < oT ? { color: 'var(--arch-c-async)' } : undefined}>{ratio}&times;</span>
          <span className={styles.duoResultSub}>
            {rT > oT ? 'aerospike-py가 빠름' : rT < oT ? 'Official이 빠름 (localhost 한정)' : '동등'}
          </span>
        </div>
      </div>
    </div>
  );
}

/* ── Beyond Benchmark: Memory Simulation ─────────── */

const MEM_CONC = [10, 100, 500, 1000, 5000];
const POD_LIMIT = 512;

export function MemorySim(): React.ReactElement {
  const [idx, setIdx] = useState(1);
  const conc = MEM_CONC[idx];
  const offMem = conc * 8;
  const rusMem = Math.max(2, Math.ceil(conc * 0.005 + 4));
  const scale = Math.max(offMem, POD_LIMIT);
  const oom = offMem > POD_LIMIT;

  const fmtMB = (m: number) => (m >= 1024 ? `${(m / 1024).toFixed(1)}GB` : `${m}MB`);

  return (
    <div className={styles.wrapper}>
      <div className={styles.concurrencyViz}>
        <div className={styles.concurrencyHeader}>
          <h3>K8s Pod 512MB 제한에서의 동시 처리 한계</h3>
        </div>
        <div style={{ fontSize: '0.72rem', color: 'var(--arch-text-muted)', marginBottom: 14 }}>
          OS 스레드(~8MB 스택) vs Tokio 태스크(~수KB). 동시 요청이 늘어날수록 차이가 극명해집니다.
        </div>
        <div className={styles.sliderGroup} style={{ marginBottom: 18 }}>
          <span>동시 요청:</span>
          <input type="range" min={0} max={MEM_CONC.length - 1} step={1} value={idx}
            onChange={(e) => setIdx(Number(e.target.value))} />
          <span className={styles.sliderValue}>{conc >= 1000 ? `${conc / 1000}K` : conc}</span>
        </div>

        <div className={styles.memSimWrap}>
          <div className={styles.memCol}>
            <div className={styles.memTower}>
              <div className={`${styles.memTowerFill} ${styles.memTowerFillAsync}`}
                style={{ height: `${Math.min(100, (offMem / scale) * 100)}%` }} />
            </div>
            <span className={`${styles.memTowerValue} ${styles.memTowerValueAsync}`}>{fmtMB(offMem)}</span>
            <span className={styles.memTowerLabel}>Official Async</span>
            <span className={styles.memTowerLabel}>(~8MB &times; threads)</span>
            {oom && <span className={styles.memOom}>OOM (&gt;512MB)</span>}
          </div>
          <span className={styles.memTowerVs}>vs</span>
          <div className={styles.memCol}>
            <div className={styles.memTower}>
              <div className={`${styles.memTowerFill} ${styles.memTowerFillRust}`}
                style={{ height: `${Math.max(1, (rusMem / scale) * 100)}%` }} />
            </div>
            <span className={`${styles.memTowerValue} ${styles.memTowerValueRust}`}>{fmtMB(rusMem)}</span>
            <span className={styles.memTowerLabel}>aerospike-py</span>
            <span className={styles.memTowerLabel}>(~수KB &times; tasks)</span>
          </div>
        </div>

        <div className={styles.sliderInsight}>
          {oom
            ? <><b>Pod 512MB 제한 초과!</b> Official async는 동시 {conc}개에서 {fmtMB(offMem)}이 필요해 OOM Kill. aerospike-py는 <b>{fmtMB(rusMem)}</b>로 여유.</>
            : <>동시 {conc}개: Official {fmtMB(offMem)} vs aerospike-py {fmtMB(rusMem)} &rarr; <b>{Math.round(offMem / rusMem)}배</b> 메모리 절감.</>
          }
        </div>
      </div>
    </div>
  );
}

/* ── Beyond Benchmark: GIL p99 Chart ─────────────── */

export function GilChart(): React.ReactElement {
  const canvasRef = React.useRef<HTMLCanvasElement>(null);

  const draw = useCallback(() => {
    const cv = canvasRef.current;
    if (!cv) return;
    const parent = cv.parentElement;
    if (!parent) return;

    const dp = typeof devicePixelRatio !== 'undefined' ? devicePixelRatio : 1;
    const W = parent.clientWidth;
    const H = parent.clientHeight;
    cv.width = W * dp;
    cv.height = H * dp;
    cv.style.width = `${W}px`;
    cv.style.height = `${H}px`;

    const x = cv.getContext('2d');
    if (!x) return;
    x.scale(dp, dp);

    const P = { l: 52, r: 16, t: 14, b: 34 };
    const gW = W - P.l - P.r;
    const gH = H - P.t - P.b;

    const xs = [1, 10, 50, 100, 200, 500, 1000, 2000];
    const oP = xs.map((n) => {
      const base = 0.3;
      const gil = Math.sqrt(Math.min(n, POOL_SIZE)) * 0.7;
      const queue = Math.max(0, n - POOL_SIZE) * 0.018;
      return base + gil + queue;
    });
    const rP = xs.map((n) => 0.25 + Math.log2(Math.max(1, n)) * 0.35);
    const mY = Math.max(...oP) * 1.12;
    const mX = Math.max(...xs);
    const xPos = (v: number) => P.l + (Math.log10(Math.max(1, v)) / Math.log10(mX)) * gW;
    const yPos = (v: number) => P.t + gH - (v / mY) * gH;

    // Detect dark mode
    const isDark = getComputedStyle(document.documentElement).getPropertyValue('--ifm-background-color')?.trim() !== '#ffffff';
    const gridColor = isDark ? 'rgba(37,48,80,.4)' : 'rgba(100,116,139,.15)';
    const labelColor = isDark ? '#566080' : '#94a3b8';

    // Grid
    x.strokeStyle = gridColor;
    x.lineWidth = 0.5;
    for (let v = 0; v <= mY; v += 5) {
      const y = yPos(v);
      x.beginPath(); x.moveTo(P.l, y); x.lineTo(W - P.r, y); x.stroke();
      x.fillStyle = labelColor;
      x.font = '9.5px sans-serif';
      x.textAlign = 'right';
      x.fillText(`${v}ms`, P.l - 6, y + 3);
    }
    x.textAlign = 'center';
    [1, 10, 50, 100, 500, 1000, 2000].forEach((v) => {
      x.fillStyle = labelColor;
      x.font = '9.5px sans-serif';
      x.fillText(v >= 1000 ? `${v / 1000}K` : String(v), xPos(v), H - P.b + 15);
    });
    x.fillText('동시 요청 수', W / 2, H - 3);

    // OOM line
    const oomX = xPos(64);
    x.strokeStyle = 'rgba(248,113,113,.2)';
    x.lineWidth = 1;
    x.setLineDash([3, 3]);
    x.beginPath(); x.moveTo(oomX, P.t); x.lineTo(oomX, P.t + gH); x.stroke();
    x.setLineDash([]);
    x.fillStyle = 'rgba(248,113,113,.5)';
    x.font = 'bold 8px sans-serif';
    x.textAlign = 'left';
    x.fillText('OOM @64', oomX + 3, P.t + 10);

    // Area fills
    function fillArea(pts: number[], color: string) {
      x.fillStyle = color;
      x.beginPath();
      pts.forEach((v, i) => {
        const px = xPos(xs[i]), py = yPos(v);
        i === 0 ? x.moveTo(px, py) : x.lineTo(px, py);
      });
      x.lineTo(xPos(xs[pts.length - 1]), yPos(0));
      x.lineTo(xPos(xs[0]), yPos(0));
      x.closePath();
      x.fill();
    }
    fillArea(oP, 'rgba(99,102,241,.06)');
    fillArea(rP, 'rgba(249,115,22,.06)');

    // Lines
    function drawLine(pts: number[], color: string) {
      x.strokeStyle = color;
      x.lineWidth = 2.5;
      x.lineJoin = 'round';
      x.beginPath();
      pts.forEach((v, i) => {
        const px = xPos(xs[i]), py = yPos(v);
        i === 0 ? x.moveTo(px, py) : x.lineTo(px, py);
      });
      x.stroke();
      x.fillStyle = color;
      pts.forEach((v, i) => {
        const px = xPos(xs[i]), py = yPos(v);
        x.beginPath();
        x.arc(px, py, 3, 0, Math.PI * 2);
        x.fill();
      });
    }
    drawLine(oP, '#6366f1');
    drawLine(rP, '#f97316');

    // End labels
    x.font = 'bold 10px sans-serif';
    x.textAlign = 'left';
    x.fillStyle = '#6366f1';
    x.fillText(`${oP[oP.length - 1].toFixed(1)}ms`, xPos(xs[xs.length - 1]) + 6, yPos(oP[oP.length - 1]) + 4);
    x.fillStyle = '#f97316';
    x.fillText(`${rP[rP.length - 1].toFixed(1)}ms`, xPos(xs[xs.length - 1]) + 6, yPos(rP[rP.length - 1]) + 4);
  }, []);

  React.useEffect(() => {
    draw();
    window.addEventListener('resize', draw);

    // Redraw when parent becomes visible (e.g. tab switch)
    const parent = canvasRef.current?.parentElement;
    let ro: ResizeObserver | undefined;
    if (parent) {
      ro = new ResizeObserver(() => draw());
      ro.observe(parent);
    }

    return () => {
      window.removeEventListener('resize', draw);
      ro?.disconnect();
    };
  }, [draw]);

  return (
    <div className={styles.wrapper}>
      <div className={styles.concurrencyViz}>
        <div className={styles.concurrencyHeader}>
          <h3>p99 Latency vs 동시 요청 수</h3>
        </div>
        <div style={{ fontSize: '0.72rem', color: 'var(--arch-text-muted)', marginBottom: 8 }}>
          아키텍처 모델 기반 예측 — GIL 경합 + 서버 큐잉 효과 반영
        </div>

        <div className={styles.timeline}>
          <div className={styles.timelineItem}>
            <div className={styles.timelineDot} />
            <div className={styles.timelineName} style={{ color: 'var(--arch-c-async)' }}>Official run_in_executor</div>
            <div className={styles.timelineDesc}>
              동시 요청 N개 &rarr; <b>OS 스레드 N개</b>가 GIL 경쟁<br />
              N&uarr; &rarr; GIL 경합 시간&uarr; &rarr; tail latency가 <b>N에 비례</b>해서 악화
            </div>
          </div>
          <div className={styles.timelineItem}>
            <div className={styles.timelineDot} style={{ borderColor: 'var(--arch-rust)' }} />
            <div className={styles.timelineName} style={{ color: 'var(--arch-rust)' }}>aerospike-py future_into_py</div>
            <div className={styles.timelineDesc}>
              동시 요청 N개 &rarr; <b>Tokio 태스크 N개</b> (GIL 불필요)<br />
              GIL 잡는 건 결과 변환 시 워커만 &rarr; 경쟁자 <b>4개 고정</b> &rarr; tail latency 안정
            </div>
          </div>
        </div>

        <div className={styles.chartWrap}><canvas ref={canvasRef} /></div>
        <div className={styles.chartLegend}>
          <span><span className={styles.chartLegendDot} style={{ background: 'var(--arch-c-async)' }} />Official Async (run_in_executor)</span>
          <span><span className={styles.chartLegendDot} style={{ background: 'var(--arch-rust)' }} />aerospike-py (Tokio)</span>
          <span><span className={styles.chartLegendDot} style={{ background: 'var(--arch-red)', opacity: 0.4 }} />512MB OOM 한계선</span>
        </div>
      </div>
    </div>
  );
}

/* ── Beyond Benchmark: Summary Cards ─────────────── */

export function BenchmarkSummary(): React.ReactElement {
  return (
    <div className={styles.wrapper}>
      <div className={styles.summaryStrip}>
        <div className={styles.summaryCard}>
          <div className={styles.summaryCardValue}>~1.3&times;</div>
          <div className={styles.summaryCardLabel}>벤치마크 Throughput</div>
          <div className={styles.summaryCardSub}>localhost, 50 conc</div>
        </div>
        <div className={styles.summaryCard}>
          <div className={styles.summaryCardValue}>5~10&times;</div>
          <div className={styles.summaryCardLabel}>실 운영 Throughput</div>
          <div className={styles.summaryCardSub}>1ms RTT, 500+ conc</div>
        </div>
        <div className={styles.summaryCard}>
          <div className={styles.summaryCardValue}>100&times;+</div>
          <div className={styles.summaryCardLabel}>메모리 효율</div>
          <div className={styles.summaryCardSub}>1K 동시 요청</div>
        </div>
        <div className={styles.summaryCard}>
          <div className={styles.summaryCardValue}>안정</div>
          <div className={styles.summaryCardLabel}>p99 Tail Latency</div>
          <div className={styles.summaryCardSub}>N과 무관</div>
        </div>
      </div>
    </div>
  );
}

export function MemoryViz(): React.ReactElement {
  return (
    <div className={styles.wrapper}>
      <div className={styles.memoryViz}>
        <div className={styles.memoryCircleGroup}>
          <div className={`${styles.memoryCircle} ${styles.memorySyncCircle}`} style={{ width: 100, height: 100, fontSize: '1rem' }}>N/A</div>
          <span className={styles.memoryLabel}>Sync</span>
          <span className={styles.memorySub} style={{ color: 'var(--arch-c-sync)' }}>순차 처리 (동시 불가)</span>
        </div>
        <span className={styles.memVs}>&middot;</span>
        <div className={styles.memoryCircleGroup}>
          <div className={`${styles.memoryCircle} ${styles.memoryAsyncCircle}`} style={{ width: 150, height: 150, fontSize: '1.3rem' }}>8GB</div>
          <span className={styles.memoryLabel}>Async (executor)</span>
          <span className={styles.memorySub} style={{ color: 'var(--arch-c-async)' }}>~8MB &times; 1,000 threads</span>
        </div>
        <span className={styles.memVs}>vs</span>
        <div className={styles.memoryCircleGroup}>
          <div className={`${styles.memoryCircle} ${styles.memoryRustCircle}`} style={{ width: 44, height: 44, fontSize: '0.65rem' }}>15MB</div>
          <span className={styles.memoryLabel}>aerospike-py</span>
          <span className={styles.memorySub} style={{ color: 'var(--arch-rust)' }}>~수KB &times; 1,000 tasks</span>
        </div>
      </div>
    </div>
  );
}
