import json
from pathlib import Path


def write_index(
    output_path: Path,
    symbols:    dict,
    callgraph:  dict,
    summaries:  dict,
    vectors:    list,
    filemeta:   dict,
    manifest:   dict,
    agents_md:  str,
) -> None:
    output_path.mkdir(parents=True, exist_ok=True)

    _write_json(output_path / 'symbols.json',   symbols)
    _write_json(output_path / 'callgraph.json', callgraph)
    _write_json(output_path / 'summaries.json', summaries)
    _write_json(output_path / 'vectors.json',   vectors)
    _write_json(output_path / 'filemeta.json',  filemeta)
    _write_json(output_path / 'manifest.json',  manifest)

    agents_path = output_path / 'agents_md.txt'
    agents_path.write_text(agents_md)
    print(f"[write] agents_md.txt")


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, default=str))
    size_kb = path.stat().st_size // 1024
    print(f"[write] {path.name} — {size_kb}KB")
