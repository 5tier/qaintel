# QAIntel Indexer Contract

`qaintel` indexes local filesystem paths only. It does not clone repositories,
read provider credentials, own Azure job state, or authorize hosted users.

## CLI

Full index:

```bash
python -m indexer.index --repo /repo --output /index --full
```

Incremental index:

```bash
python -m indexer.index --repo /repo --output /index --diff oldSha..newSha
```

## Inputs

- `/repo`: readable local git checkout prepared by the caller.
- `/index`: writable local index directory. For incremental runs, the caller
  should hydrate this directory with the previous index before starting.
- model provider env vars from `indexer/config.py`.

## Outputs

The indexer writes JSON index files into `/index`, including:

- `manifest.json`
- `symbols.json`
- `summaries.json`
- `callgraph.json`
- `filemeta.json`
- `vectors.json`
- `agents_md.txt`

## Exit Codes

- `0`: indexing succeeded.
- non-zero: caller should mark the hosted index job as failed and surface the error.
