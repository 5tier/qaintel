import { readFileSync, existsSync, readdirSync } from 'fs';
import { join } from 'path';

interface Symbol {
  name?: string;
  file: string;
  line?: number;
  kind?: string;
  exported?: boolean;
  callers?: string[];
  callees?: string[];
  signature?: string;
}

interface FileSummary {
  summary?: string;
  exports?: string[];
  risks?: string;
  test_hint?: string;
  changed_at?: string;
}

interface FileMeta {
  lines?: number;
  commits?: number;
  authors?: string[];
  last_changed?: string;
  created_at?: string;
  created_by?: string;
  created_message?: string;
  commit_log?: Array<{ date: string; author: string; message: string }>;
}

interface VectorEntry {
  file: string;
  text?: string;
  vector: number[];
  score?: number;
}

interface Manifest {
  sha?: string;
  branch?: string;
  built_at?: string;
  file_count?: number;
}

export type { Symbol, FileSummary, FileMeta, VectorEntry, Manifest };

export class IndexStore {
  indexPath: string;
  symbols: Record<string, Symbol>;
  summaries: Record<string, FileSummary>;
  callgraph: Record<string, string[]>;
  filemeta: Record<string, FileMeta>;
  vectors: VectorEntry[];
  agentsMd: string;
  manifest: Manifest;

  constructor(indexPath: string) {
    this.indexPath = indexPath;
    this.symbols = {};
    this.summaries = {};
    this.callgraph = {};
    this.filemeta = {};
    this.vectors = [];
    this.agentsMd = '';
    this.manifest = {};
  }

  async load(): Promise<void> {
    const load = <T>(file: string, fallback: T): T => {
      const p = join(this.indexPath, file);
      if (!existsSync(p)) return fallback;
      return JSON.parse(readFileSync(p, 'utf8')) as T;
    };

    this.symbols   = load<Record<string, Symbol>>('symbols.json', {});
    this.summaries = load<Record<string, FileSummary>>('summaries.json', {});
    this.callgraph = load<Record<string, string[]>>('callgraph.json', {});
    this.filemeta  = load<Record<string, FileMeta>>('filemeta.json', {});
    this.vectors   = load<VectorEntry[]>('vectors.json', []);
    this.manifest  = load<Manifest>('manifest.json', {});

    const agentsPath = join(this.indexPath, 'agents_md.txt');
    this.agentsMd = existsSync(agentsPath)
      ? readFileSync(agentsPath, 'utf8')
      : '# No AGENTS.md found in this repo.';
  }

  // Hot-patch: reload index entries for a specific set of changed files.
  // Called by the incremental indexer after each push — no server restart needed.
  async patch(changedFiles: string[], indexPath: string): Promise<void> {
    const fresh = new IndexStore(indexPath);
    await fresh.load();

    for (const file of changedFiles) {
      for (const [name, sym] of Object.entries(fresh.symbols)) {
        if (sym.file === file) this.symbols[name] = sym;
      }
      if (fresh.summaries[file]) this.summaries[file] = fresh.summaries[file];
      if (fresh.callgraph[file]) this.callgraph[file] = fresh.callgraph[file];
      if (fresh.filemeta[file]) this.filemeta[file] = fresh.filemeta[file];
    }

    const staleFiles = new Set(changedFiles);
    this.vectors = [
      ...this.vectors.filter(v => !staleFiles.has(v.file)),
      ...fresh.vectors.filter(v => staleFiles.has(v.file)),
    ];

    this.agentsMd = fresh.agentsMd;
    this.manifest = fresh.manifest;
  }

  getSymbol(name: string): Symbol | undefined {
    return this.symbols[name]
      ?? Object.values(this.symbols).find(s =>
          s.name?.toLowerCase() === name.toLowerCase()
        );
  }

  searchSymbols(query: string): Symbol[] {
    const q = query.toLowerCase();
    return Object.values(this.symbols)
      .filter(s => s.name?.toLowerCase().includes(q))
      .slice(0, 20);
  }

  getFileSummary(filePath: string): FileSummary | undefined {
    return this.summaries[filePath]
      ?? Object.entries(this.summaries)
          .find(([k]) => k.endsWith(filePath))?.[1];
  }

  getCallersOf(symbolName: string): Array<{ name: string } & Partial<Symbol>> {
    const sym = this.getSymbol(symbolName);
    if (!sym) return [];
    return (sym.callers ?? []).map(name => ({ name, ...this.getSymbol(name) }));
  }

  getCalleesOf(symbolName: string): Array<{ name: string } & Partial<Symbol>> {
    const sym = this.getSymbol(symbolName);
    if (!sym) return [];
    return (sym.callees ?? []).map(name => ({ name, ...this.getSymbol(name) }));
  }

  getImpact(filePath: string): string[] {
    const visited = new Set<string>();
    const queue = [filePath];
    while (queue.length) {
      const current = queue.shift()!;
      if (visited.has(current)) continue;
      visited.add(current);
      for (const [file, deps] of Object.entries(this.callgraph)) {
        if (deps.includes(current) && !visited.has(file)) {
          queue.push(file);
        }
      }
    }
    visited.delete(filePath);
    return [...visited];
  }

  getFileChurnInfo(filePath: string): FileMeta | null {
    return this.filemeta[filePath] ?? null;
  }

  getHighChurnFiles(limit = 10): Array<{ path: string } & FileMeta> {
    return Object.entries(this.filemeta)
      .sort(([, a], [, b]) => (b.commits ?? 0) - (a.commits ?? 0))
      .slice(0, limit)
      .map(([path, meta]) => ({ path, ...meta }));
  }

  semanticSearch(queryVector: number[], topK = 8): VectorEntry[] {
    const scored = this.vectors.map(entry => ({
      ...entry,
      score: cosineSimilarity(queryVector, entry.vector),
    }));
    return scored.sort((a, b) => b.score - a.score).slice(0, topK);
  }

  stats(): string {
    return [
      `${Object.keys(this.symbols).length} symbols`,
      `${Object.keys(this.summaries).length} file summaries`,
      `${this.vectors.length} vector chunks`,
      `sha=${this.manifest.sha ?? 'unknown'}`,
    ].join(' · ');
  }
}

function cosineSimilarity(a: number[], b: number[]): number {
  if (!a || !b || a.length !== b.length) return 0;
  let dot = 0, normA = 0, normB = 0;
  for (let i = 0; i < a.length; i++) {
    dot   += a[i] * b[i];
    normA += a[i] * a[i];
    normB += b[i] * b[i];
  }
  return dot / (Math.sqrt(normA) * Math.sqrt(normB) + 1e-8);
}

// ─── BranchStore ──────────────────────────────────────────────────────────────

export interface BranchInfo {
  branch:     string;
  sha?:       string;
  built_at?:  string;
  file_count?: number;
  is_default: boolean;
}

/**
 * Loads one IndexStore per indexed branch and routes queries to the right one.
 *
 * Layout expected on disk (multi-branch):
 *   rootPath/
 *     main/          ← branch slug
 *       manifest.json  { branch: "main", ... }
 *       symbols.json
 *       ...
 *     feature-payments/
 *       manifest.json  { branch: "feature/payments", ... }
 *       ...
 *
 * Backward-compat (flat / single-branch):
 *   rootPath/
 *     manifest.json
 *     symbols.json
 *     ...
 *
 * In flat mode the branch name is taken from manifest.branch (or "main").
 */
export class BranchStore {
  private stores  = new Map<string, IndexStore>();
  private default = 'main';
  private flat    = false;   // true when rootPath itself is the index

  constructor(private rootPath: string) {}

  async load(): Promise<void> {
    // ── Flat / backward-compat mode ──────────────────────────────────────────
    if (existsSync(join(this.rootPath, 'manifest.json'))) {
      this.flat = true;
      const store = new IndexStore(this.rootPath);
      await store.load();
      const branch = store.manifest.branch || 'main';
      this.stores.set(branch, store);
      this.default = branch;
      return;
    }

    // ── Multi-branch mode ────────────────────────────────────────────────────
    const dirs = readdirSync(this.rootPath, { withFileTypes: true })
      .filter(d => d.isDirectory() && existsSync(join(this.rootPath, d.name, 'manifest.json')));

    for (const dir of dirs) {
      const store = new IndexStore(join(this.rootPath, dir.name));
      await store.load();
      // Use the branch name stored in the manifest (preserves slashes like feature/foo)
      const branch = store.manifest.branch || dir.name;
      this.stores.set(branch, store);
    }

    // Default: prefer main → master → first alphabetically
    this.default = this.stores.has('main')   ? 'main'
                 : this.stores.has('master') ? 'master'
                 : [...this.stores.keys()].sort()[0] ?? 'main';
  }

  /**
   * Return the IndexStore for the requested branch.
   * Throws a descriptive error if the branch is not indexed.
   */
  resolve(branch?: string): IndexStore {
    const key = branch || this.default;
    const store = this.stores.get(key);
    if (!store) {
      const available = [...this.stores.keys()].join(', ');
      throw new Error(`Branch '${key}' is not indexed. Available: ${available || '(none)'}`);
    }
    return store;
  }

  branches(): BranchInfo[] {
    return [...this.stores.entries()].map(([branch, store]) => ({
      branch,
      sha:        store.manifest.sha,
      built_at:   store.manifest.built_at,
      file_count: store.manifest.file_count,
      is_default: branch === this.default,
    }));
  }

  /**
   * Hot-patch a branch's index after an incremental re-index.
   * indexPath overrides where to read fresh data from — defaults to the branch's INDEX_PATH.
   */
  async patch(files: string[], branch: string, indexPath?: string): Promise<void> {
    const store = this.resolve(branch);
    await store.patch(files, indexPath ?? store.indexPath);
  }

  stats(): string {
    const list = [...this.stores.keys()];
    if (list.length === 1) return `[${list[0]}] ${this.stores.get(list[0])!.stats()}`;
    return `${list.length} branch(es): ${list.join(', ')}`;
  }
}
