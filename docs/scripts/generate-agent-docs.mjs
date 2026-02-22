/**
 * Generates AI-agent-friendly documentation files (llms.txt, llms-full.txt)
 * from existing Docusaurus docs.
 *
 * Strips MDX components (Tabs, TabItem, imports), converts admonitions to
 * blockquotes, and outputs llms.txt standard files in static/.
 *
 * Usage: node scripts/generate-agent-docs.mjs
 */

import { readFileSync, writeFileSync, mkdirSync, readdirSync, statSync, existsSync } from 'fs';
import { dirname, join, extname, relative } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const STATIC_DIR = join(__dirname, '..', 'static');

/**
 * Determine the docs source directory.
 * If versioned docs exist (versions.json), use the latest versioned snapshot.
 * Otherwise, fall back to the current docs/ directory.
 */
function getDocsDir() {
  const versionsFile = join(__dirname, '..', 'versions.json');
  if (existsSync(versionsFile)) {
    const versions = JSON.parse(readFileSync(versionsFile, 'utf-8'));
    if (versions.length > 0) {
      const latestVersion = versions[0];
      const versionedDir = join(__dirname, '..', 'versioned_docs', `version-${latestVersion}`);
      if (existsSync(versionedDir)) {
        return versionedDir;
      }
    }
  }
  return join(__dirname, '..', 'docs');
}

const DOCS_DIR = getDocsDir();
const SITE_URL = 'https://kimsoungryoul.github.io/aerospike-py';
const BASE_URL = '/docs';

// ── File collection ──────────────────────────────────────────────────

function collectMarkdownFiles(dir, files = []) {
  for (const entry of readdirSync(dir)) {
    const fullPath = join(dir, entry);
    const stat = statSync(fullPath);
    if (stat.isDirectory()) {
      collectMarkdownFiles(fullPath, files);
    } else if (extname(entry) === '.md') {
      files.push(fullPath);
    }
    // skip .mdx files (React components)
  }
  return files;
}

// ── Slug generation ──────────────────────────────────────────────────

function buildSlug(filePath) {
  const rel = relative(DOCS_DIR, filePath);            // e.g. "guides/crud.md"
  const parts = rel.replace(/\.md$/, '').split('/');    // ["guides", "crud"]

  if (parts.length === 1) {
    return parts[0]; // top-level: "getting-started", "contributing"
  }

  // Flatten nested paths: integrations/observability/logging → integrations-observability-logging
  return parts.join('-');
}

// ── Transformation pipeline ──────────────────────────────────────────

/** 1. Remove MDX import statements */
function stripImports(content) {
  return content.replace(/^import\s+.*from\s+['"].*['"];?\s*$/gm, '');
}

/** 2. Flatten <Tabs>/<TabItem> into ### headers */
function flattenTabs(content) {
  // Remove <Tabs> and </Tabs>
  content = content.replace(/^\s*<Tabs>\s*$/gm, '');
  content = content.replace(/^\s*<\/Tabs>\s*$/gm, '');

  // Convert <TabItem> opening tags to ### headers
  content = content.replace(
    /^\s*<TabItem\s+value="[^"]*"\s+label="([^"]*)"\s*(?:default)?\s*>\s*$/gm,
    '\n### $1\n'
  );

  // Also handle different attribute ordering
  content = content.replace(
    /^\s*<TabItem\s+label="([^"]*)"\s+value="[^"]*"\s*(?:default)?\s*>\s*$/gm,
    '\n### $1\n'
  );

  // Remove </TabItem>
  content = content.replace(/^\s*<\/TabItem>\s*$/gm, '');

  return content;
}

/** 3. Convert :::tip/:::warning/:::note/:::info/:::danger admonitions to blockquotes */
function processAdmonitions(content) {
  // Match :::type[optional title]\n...\n:::
  const admonitionRegex = /^:::(tip|warning|note|info|danger|caution)(?:\[([^\]]*)\])?\s*\n([\s\S]*?)^:::\s*$/gm;

  return content.replace(admonitionRegex, (_match, type, title, body) => {
    const label = title || type.charAt(0).toUpperCase() + type.slice(1);
    const lines = body.trim().split('\n');
    const quoted = lines.map(line => `> ${line}`).join('\n');
    return `> **${label}:**\n${quoted}`;
  });
}

/** 4. Add descriptive text before mermaid code blocks */
function convertMermaid(content) {
  return content.replace(
    /```mermaid\n([\s\S]*?)```/g,
    (_match, src) => {
      const desc = describeMermaid(src);
      return `> **Diagram:** ${desc}\n\n\`\`\`mermaid\n${src}\`\`\``;
    }
  );
}

function describeMermaid(source) {
  const firstLine = source.trim().split('\n')[0].trim();
  const subgraphs = [...source.matchAll(/subgraph\s+\w+\["([^"]+)"\]/g)]
    .map(m => m[1].replace(/\*\*/g, '').trim());
  const participants = [...source.matchAll(/participant\s+\w+\s+as\s+(.+)$/gm)]
    .map(m => m[1].trim());

  if (firstLine.startsWith('sequenceDiagram')) {
    return participants.length
      ? `Sequence diagram showing interactions between ${participants.join(', ')}.`
      : 'Sequence diagram showing component interactions.';
  }
  if (firstLine.startsWith('flowchart')) {
    return subgraphs.length
      ? `Flowchart showing data flow between ${subgraphs.join(', ')}.`
      : 'Flowchart showing system architecture and data flow.';
  }
  return 'Architecture diagram.';
}

/** 5. Convert relative markdown links to absolute site paths */
function convertLinks(content, filePath) {
  const fileDir = relative(DOCS_DIR, dirname(filePath)); // e.g. "guides", "api", ""

  return content.replace(
    /\[([^\]]*)\]\((\.[^)]+|[^)]*\.(?:md|mdx))\)/g,
    (_match, text, href) => {
      if (href.startsWith('http://') || href.startsWith('https://')) {
        return `[${text}](${href})`;
      }
      // Remove .md/.mdx extension
      let cleanHref = href.replace(/\.mdx?$/, '');

      // Resolve relative to source file directory
      if (cleanHref.startsWith('../') || cleanHref.startsWith('./')) {
        const parts = [...fileDir.split('/').filter(Boolean), ...cleanHref.split('/')];
        const resolved = [];
        for (const part of parts) {
          if (part === '..') resolved.pop();
          else if (part !== '.') resolved.push(part);
        }
        cleanHref = resolved.join('/');
      } else if (fileDir && !cleanHref.startsWith('/')) {
        // Relative path without ./ prefix (e.g. "query-scan.md" in api/)
        cleanHref = fileDir + '/' + cleanHref;
      }

      return `[${text}](${BASE_URL}/${cleanHref})`;
    }
  );
}

/** 6. Strip frontmatter from content */
function stripFrontmatter(content) {
  const fmMatch = content.match(/^---\n([\s\S]*?)\n---\n/);
  return fmMatch ? content.slice(fmMatch[0].length) : content;
}

/** 7. Clean up excessive whitespace */
function cleanWhitespace(content) {
  // Collapse 3+ consecutive newlines to 2
  return content.replace(/\n{3,}/g, '\n\n').trim() + '\n';
}

// ── Main pipeline ────────────────────────────────────────────────────

function getCategory(filePath) {
  const rel = relative(DOCS_DIR, filePath);
  const parts = rel.split('/');
  return parts.length > 1 ? parts[0] : 'general';
}

function buildDocPath(filePath) {
  // Build the Docusaurus docs URL path from source file path
  // e.g. "guides/crud.md" → "guides/crud", "getting-started.md" → "getting-started"
  return relative(DOCS_DIR, filePath).replace(/\.md$/, '');
}

function transformFile(filePath) {
  let content = readFileSync(filePath, 'utf-8');
  const slug = buildSlug(filePath);
  const category = getCategory(filePath);
  let docPath = buildDocPath(filePath);

  // Extract title, description, and slug from original frontmatter
  const fmMatch = content.match(/^---\n([\s\S]*?)\n---\n/);
  const title = fmMatch?.[1]?.match(/^title:\s*(.+)$/m)?.[1]?.trim() || slug;
  const description = fmMatch?.[1]?.match(/^description:\s*(.+)$/m)?.[1]?.trim() || '';
  const fmSlug = fmMatch?.[1]?.match(/^slug:\s*(.+)$/m)?.[1]?.trim();
  if (fmSlug) {
    // Use frontmatter slug (strip leading /) for URL generation
    docPath = fmSlug.replace(/^\//, '');
  }

  content = stripImports(content);
  content = flattenTabs(content);
  content = processAdmonitions(content);
  content = convertMermaid(content);
  content = convertLinks(content, filePath);
  content = stripFrontmatter(content);
  const body = cleanWhitespace(content);

  return { slug, category, docPath, title, description, body };
}

// ── llms.txt generation ──────────────────────────────────────────────

const CATEGORY_ORDER = ['general', 'api', 'guides', 'integrations', 'performance'];
const CATEGORY_TITLES = {
  general: 'Getting Started',
  api: 'API Reference',
  guides: 'Guides',
  integrations: 'Integrations',
  performance: 'Performance',
};

function groupByCategory(entries) {
  const categories = {};
  for (const entry of entries) {
    if (!categories[entry.category]) categories[entry.category] = [];
    categories[entry.category].push(entry);
  }
  return categories;
}

function generateLlmsTxt(entries) {
  const lines = [
    '# aerospike-py',
    '',
    '> High-performance Aerospike Python Client built in Rust (Sync/Async). Provides both synchronous and asynchronous APIs with zero-copy NumPy batch reads, OpenTelemetry tracing, and Prometheus metrics.',
    '',
    `- [Full documentation](${SITE_URL}/llms-full.txt): Complete documentation in a single file`,
    '',
  ];

  const categories = groupByCategory(entries);

  for (const cat of CATEGORY_ORDER) {
    const docs = categories[cat];
    if (!docs) continue;
    lines.push(`## ${CATEGORY_TITLES[cat] || cat}`);
    lines.push('');
    for (const { title, description, docPath } of docs.sort((a, b) => a.slug.localeCompare(b.slug))) {
      const desc = description ? `: ${description}` : '';
      lines.push(`- [${title}](${SITE_URL}/docs/${docPath})${desc}`);
    }
    lines.push('');
  }

  return lines.join('\n');
}

/**
 * Shift markdown heading levels by n (e.g., ## -> ####).
 * Skips headings inside fenced code blocks.
 */
function shiftHeadings(content, shift) {
  const lines = content.split('\n');
  let inCodeBlock = false;
  return lines.map(line => {
    if (line.startsWith('```')) {
      inCodeBlock = !inCodeBlock;
      return line;
    }
    if (inCodeBlock) return line;

    const headingMatch = line.match(/^(#{1,6})\s+(.*)/);
    if (headingMatch) {
      const newLevel = Math.min(headingMatch[1].length + shift, 6);
      return '#'.repeat(newLevel) + ' ' + headingMatch[2];
    }
    return line;
  }).join('\n');
}

function generateLlmsFullTxt(entries) {
  const lines = [
    '# aerospike-py',
    '',
    '> High-performance Aerospike Python Client built in Rust (Sync/Async). Provides both synchronous and asynchronous APIs with zero-copy NumPy batch reads, OpenTelemetry tracing, and Prometheus metrics.',
    '',
  ];

  const categories = groupByCategory(entries);

  for (const cat of CATEGORY_ORDER) {
    const docs = categories[cat];
    if (!docs) continue;
    lines.push(`## ${CATEGORY_TITLES[cat] || cat}`);
    lines.push('');

    for (const { title, description, body } of docs.sort((a, b) => a.slug.localeCompare(b.slug))) {
      lines.push(`### ${title}`);
      if (description) {
        lines.push('');
        lines.push(`> ${description}`);
      }
      lines.push('');
      lines.push(shiftHeadings(body, 2));
      lines.push('');
      lines.push('---');
      lines.push('');
    }
  }

  return lines.join('\n');
}

// ── Entry point ──────────────────────────────────────────────────────

function main() {
  console.log('Generating llms.txt and llms-full.txt...');

  mkdirSync(STATIC_DIR, { recursive: true });

  // Collect and transform
  const mdFiles = collectMarkdownFiles(DOCS_DIR);
  console.log(`Found ${mdFiles.length} .md files (skipping .mdx)`);

  const entries = [];

  for (const filePath of mdFiles) {
    const entry = transformFile(filePath);
    entries.push(entry);
    console.log(`  ✓ ${entry.slug}`);
  }

  // Generate llms.txt and llms-full.txt in static/
  const llmsTxt = generateLlmsTxt(entries);
  writeFileSync(join(STATIC_DIR, 'llms.txt'), llmsTxt, 'utf-8');
  console.log(`  ✓ static/llms.txt`);

  const llmsFullTxt = generateLlmsFullTxt(entries);
  writeFileSync(join(STATIC_DIR, 'llms-full.txt'), llmsFullTxt, 'utf-8');
  console.log(`  ✓ static/llms-full.txt (${(Buffer.byteLength(llmsFullTxt) / 1024).toFixed(1)} KB)`);

  console.log(`\nGenerated llms.txt and llms-full.txt in static/`);
}

main();
