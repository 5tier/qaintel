import { existsSync, readdirSync } from "fs";
import { join } from "path";
import { IndexStore } from "./index-store-core";
import type { BranchInfo } from "./types";

function getDefaultBranch(stores: Map<string, IndexStore>): string {
  if (stores.has("main")) return "main";
  if (stores.has("master")) return "master";
  return [...stores.keys()].sort()[0] ?? "main";
}

export class BranchStore {
  private stores = new Map<string, IndexStore>();
  private defaultBranch = "main";

  constructor(private rootPath: string) {}

  async load(): Promise<void> {
    if (existsSync(join(this.rootPath, "manifest.json"))) {
      const store = new IndexStore(this.rootPath);
      await store.load();
      const branch = store.manifest.branch || "main";
      this.stores.set(branch, store);
      this.defaultBranch = branch;
      return;
    }

    const dirs = readdirSync(this.rootPath, { withFileTypes: true }).filter(
      (d) => d.isDirectory() && existsSync(join(this.rootPath, d.name, "manifest.json")),
    );

    for (const dir of dirs) {
      const store = new IndexStore(join(this.rootPath, dir.name));
      await store.load();
      this.stores.set(store.manifest.branch || dir.name, store);
    }
    this.defaultBranch = getDefaultBranch(this.stores);
  }

  resolve(branch?: string): IndexStore {
    const key = branch || this.defaultBranch;
    const store = this.stores.get(key);
    if (!store) {
      const available = [...this.stores.keys()].join(", ");
      throw new Error(`Branch '${key}' is not indexed. Available: ${available || "(none)"}`);
    }
    return store;
  }

  branches(): BranchInfo[] {
    return [...this.stores.entries()].map(([branch, store]) => ({
      branch,
      sha: store.manifest.sha,
      built_at: store.manifest.built_at,
      file_count: store.manifest.file_count,
      is_default: branch === this.defaultBranch,
    }));
  }

  async patch(files: string[], branch: string, indexPath?: string): Promise<void> {
    const store = this.resolve(branch);
    await store.patch(files, indexPath ?? store.indexPath);
  }

  stats(): string {
    const list = [...this.stores.keys()];
    if (list.length === 1) return `[${list[0]}] ${this.stores.get(list[0])!.stats()}`;
    return `${list.length} branch(es): ${list.join(", ")}`;
  }
}
