#!/usr/bin/env node
/**
 * 릴리스 시 versions-config.json을 업데이트하는 스크립트.
 * docs:version 실행 후 호출된다.
 *
 * Usage: node docs/scripts/update-version-config.mjs <version>
 * Example: node docs/scripts/update-version-config.mjs 0.1.0
 */
import {readFileSync, writeFileSync} from 'fs';
import {fileURLToPath} from 'url';
import {dirname, join} from 'path';

const version = process.argv[2];
if (!version) {
  console.error('버전을 인자로 제공해주세요. 예: node update-version-config.mjs 0.1.0');
  process.exit(1);
}

const __dirname = dirname(fileURLToPath(import.meta.url));
const configPath = join(__dirname, '..', 'versions-config.json');

const config = JSON.parse(readFileSync(configPath, 'utf8'));

// current (개발 중) → main으로 변경
config.versions.current = {
  label: 'main',
  path: 'next',
  banner: 'unreleased',
};

// 새 릴리스 버전을 latest 위치(root path)에 추가
config.versions[version] = {
  label: version,
  path: '',
  banner: 'none',
};

// lastVersion을 새 릴리스로 설정
config.lastVersion = version;

writeFileSync(configPath, JSON.stringify(config, null, 2) + '\n');
console.log(`✅ versions-config.json 업데이트 완료: v${version} → latest`);
