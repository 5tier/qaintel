export interface Symbol {
  name?: string;
  file: string;
  line?: number;
  kind?: string;
  exported?: boolean;
  callers?: string[];
  callees?: string[];
  signature?: string;
}

export interface FileSummary {
  summary?: string;
  exports?: string[];
  risks?: string;
  test_hint?: string;
  changed_at?: string;
}

export interface FileMeta {
  lines?: number;
  commits?: number;
  authors?: string[];
  last_changed?: string;
  created_at?: string;
  created_by?: string;
  created_message?: string;
  commit_log?: Array<{ date: string; author: string; message: string }>;
}

export interface VectorEntry {
  file: string;
  text?: string;
  vector: number[];
  score?: number;
}

export interface Manifest {
  sha?: string;
  branch?: string;
  built_at?: string;
  file_count?: number;
}

export interface BranchInfo {
  branch: string;
  sha?: string;
  built_at?: string;
  file_count?: number;
  is_default: boolean;
}
