import { existsSync, readFileSync } from "fs";
import { join } from "path";
import { cosineSimilarity } from "./math";
import type { FileMeta, FileSummary, Manifest, Symbol, VectorEntry } from "./types";

function loadJson<T>(indexPath: string, file: string, fallback: T): T {
  const p = join(indexPath, file);
  if (!existsSync(p)) return fallback;
  return JSON.parse(readFileSync(p, "utf8")) as T;
}

function findBySuffix<T>(source: Record<string, T>, suffixPath: string): T | undefined {
  return Object.entries(source).find(([k]) => k.endsWith(suffixPath))?.[1];
}

export class IndexStore {
  indexPath: string;
  symbols: Record<string, Symbol> = {};
  summaries: Record<string, FileSummary> = {};
  callgraph: Record<string, string[]> = {};
  filemeta: Record<string, FileMeta> = {};
  vectors: VectorEntry[] = [];
  agentsMd = "";
  manifest: Manifest = {};

  constructor(indexPath: string) {
    this.indexPath = indexPath;
  }

  async load(): Promise<void> {
    this.symbols = loadJson(this.indexPath, "symbols.json", {});
    this.summaries = loadJson(this.indexPath, "summaries.json", {});
    this.callgraph = loadJson(this.indexPath, "callgraph.json", {});
    this.filemeta = loadJson(this.indexPath, "filemeta.json", {});
    this.vectors = loadJson(this.indexPath, "vectors.json", []);
    this.manifest = loadJson(this.indexPath, "manifest.json", {});

    const agentsPath = join(this.indexPath, "agents_md.txt");
    this.agentsMd = existsSync(agentsPath) ? readFileSync(agentsPath, "utf8") : "# No AGENTS.md found in this repo.";
  }

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
      ...this.vectors.filter((v) => !staleFiles.has(v.file)),
      ...fresh.vectors.filter((v) => staleFiles.has(v.file)),
    ];

    this.agentsMd = fresh.agentsMd;
    this.manifest = fresh.manifest;
  }

  getSymbol(name: string): Symbol | undefined {
    return this.symbols[name] ?? Object.values(this.symbols).find((s) => s.name?.toLowerCase() === name.toLowerCase());
  }

  searchSymbols(query: string): Symbol[] {
    const q = query.toLowerCase();
    return Object.values(this.symbols).filter((s) => s.name?.toLowerCase().includes(q)).slice(0, 20);
  }

  getFileSummary(filePath: string): FileSummary | undefined {
    return this.summaries[filePath] ?? findBySuffix(this.summaries, filePath);
  }

  getCallersOf(symbolName: string): Array<{ name: string } & Partial<Symbol>> {
    const sym = this.getSymbol(symbolName);
    if (!sym) return [];
    return (sym.callers ?? []).map((name) => ({ name, ...this.getSymbol(name) }));
  }

  getCalleesOf(symbolName: string): Array<{ name: string } & Partial<Symbol>> {
    const sym = this.getSymbol(symbolName);
    if (!sym) return [];
    return (sym.callees ?? []).map((name) => ({ name, ...this.getSymbol(name) }));
  }

  getImpact(filePath: string): string[] {
    const visited = new Set<string>();
    const queue = [filePath];
    while (queue.length) {
      const current = queue.shift()!;
      if (visited.has(current)) continue;
      visited.add(current);
      for (const [file, deps] of Object.entries(this.callgraph)) {
        if (deps.includes(current) && !visited.has(file)) queue.push(file);
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
    return this.vectors
      .map((entry) => ({ ...entry, score: cosineSimilarity(queryVector, entry.vector) }))
      .sort((a, b) => b.score - a.score)
      .slice(0, topK);
  }

  stats(): string {
    return [
      `${Object.keys(this.symbols).length} symbols`,
      `${Object.keys(this.summaries).length} file summaries`,
      `${this.vectors.length} vector chunks`,
      `sha=${this.manifest.sha ?? "unknown"}`,
    ].join(" · ");
  }
}
