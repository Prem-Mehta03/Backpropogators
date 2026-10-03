"""Offline Phase C checks, preservation audit and timestamp-only repeated-run comparison.

No fetch, deletion, environment creation, hosted API, Git mutation or publication.
Full discovery is recorded separately and remains blocked when teammate inputs are absent.
"""
import hashlib
import importlib
import json
from pathlib import Path
import re
import subprocess
import sys
from time import perf_counter

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluation.role4.logger import write_json

DOCS = ROOT / 'docs/role4'
OUTPUT = ROOT / 'evaluation/logs/role4/midproject'
CHANGED_EXISTING = {
    'evaluation/role4/behavioral.py', 'evaluation/role4/evaluator.py',
    'evaluation/role4/integration/adapters/sensorimotor_adapter.py',
    'evaluation/role4/integration/runner.py', 'evaluation/role4/integration/trace_recorder.py',
    'evaluation/role4/reference_layers/procedural_reference.py',
}


def execute(name, command):
    start = perf_counter()
    process = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    record = {'name': name, 'command': command, 'exit_code': process.returncode,
              'wall_seconds': round(perf_counter() - start, 3), 'stdout': process.stdout, 'stderr': process.stderr}
    print(f"{name}: exit {process.returncode}, wall {record['wall_seconds']}s")
    return record


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stable(value):
    if isinstance(value, dict):
        return {k: stable(v) for k, v in value.items() if k not in {'timestamp', 'evaluated_at'}}
    if isinstance(value, list):
        return [stable(v) for v in value]
    return value


def parse_artifacts(directory):
    parsed = {}
    for path in sorted(directory.iterdir()):
        if path.suffix == '.json':
            parsed[path.name] = json.loads(path.read_text(encoding='utf-8'))
        elif path.suffix == '.jsonl':
            parsed[path.name] = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
    return parsed


def main():
    baseline = json.loads((DOCS / 'phase_c_baseline.json').read_text(encoding='utf-8'))
    python_stdlib = str(ROOT.parent / '.venv/Scripts/python.exe')
    checks = []
    commands = [(c['name'], c['command']) for c in baseline['checks']]
    for name, command in commands:
        checks.append(execute(name, command))
    checks.append(execute('midproject_all', [python_stdlib, '-B', '-S', 'scripts/run_role4_midproject.py']))
    first = parse_artifacts(OUTPUT)
    checks.append(execute('midproject_repeat', [python_stdlib, '-B', '-S', 'scripts/run_role4_midproject.py']))
    second = parse_artifacts(OUTPUT)
    differences = [name for name in sorted(set(first) | set(second)) if stable(first.get(name)) != stable(second.get(name))]
    checks.append(execute('midproject_selected', [python_stdlib, '-B', '-S', 'scripts/run_role4_midproject.py',
                                                '--scenario', 'S07', '--output-dir', str(OUTPUT / 'selected_S07')]))
    selected = parse_artifacts(OUTPUT / 'selected_S07')
    summary = second['build_summary.json']
    original_paths = subprocess.check_output(['git', '-c', f'safe.directory={ROOT.as_posix()}', 'ls-files'], cwd=ROOT, text=True).splitlines()
    changed = [p for p, old in baseline['before']['clone'].items() if not (ROOT / p).is_file() or digest(ROOT / p) != old]
    source = ROOT.parent / 'I_Agent_Project'
    source_changed = [p for p, old in baseline['before']['source'].items() if not (source / p).is_file() or digest(source / p) != old]
    original_changed = [p for p in original_paths if p in changed]
    historical = [p for p in baseline['before']['clone'] if p.startswith('docs/role4/')]
    historical_changed = [p for p in historical if p in changed]
    imports = {}
    for name in ('evaluation.role4.midproject', 'evaluation.role4.integration.runner',
                 'evaluation.role4.reference_layers.abstention_reference', 'procedural.llm_client',
                 'tests.role4.test_midproject', 'tests.procedural.scripted_llm'):
        imports[name] = str(Path(importlib.import_module(name).__file__).resolve())
    import_ok = all(Path(p).is_relative_to(ROOT) for p in imports.values())
    proposed = (DOCS / 'proposed_commit_files_cumulative.txt').read_text(encoding='utf-8').splitlines()
    credential_findings, excluded_findings = [], []
    credential_pattern = re.compile(r'(?:sk-[A-Za-z0-9_-]{20,}|gsk_[A-Za-z0-9]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)')
    for relative in proposed:
        path = ROOT / relative
        if any(part in {'.git', '__pycache__', '.pytest_cache', '.venv', 'node_modules'} for part in path.relative_to(ROOT).parts) or \
                path.name == '.env' or relative.startswith('evaluation/logs/'):
            excluded_findings.append(relative)
        if path.is_file() and credential_pattern.search(path.read_text(encoding='utf-8')):
            credential_findings.append(relative)
    caches = [str(p.relative_to(ROOT)) for p in ROOT.rglob('*') if p.is_dir() and p.name in {'__pycache__', '.pytest_cache'} and '.git' not in p.parts]
    diff = execute('git_diff_check', ['git', '-c', f'safe.directory={ROOT.as_posix()}', 'diff', '--check'])
    checks.append(diff)
    packet = second['human_review_packet.json']
    reviews_pending = len(packet['responses']) == 5 and all(r['status'] == 'not_reviewed' and r['reviewer'] is None and
                                                           all(c['rating'] is None for c in r['criteria']) for r in packet['responses'])
    counts = {}
    for record in checks:
        match = re.search(r'(\d+) passed', record['stdout']) or re.search(r'Ran (\d+) tests', record['stderr'])
        if match:
            counts[record['name']] = int(match.group(1))
    success = all(c['exit_code'] == 0 for c in checks if c['name'] != 'full') and not differences and \
        not source_changed and not original_changed and not historical_changed and set(changed) == CHANGED_EXISTING and \
        not credential_findings and not excluded_findings and not caches and import_ok and reviews_pending and summary['all_expectations_met']
    verification = {'phase': 'C', 'date': '2026-10-03', 'checks': checks, 'test_counts': counts,
                    'collection_status': 'BLOCKED' if next(c['exit_code'] for c in checks if c['name'] == 'full') else 'PASS',
                    'baseline_role4': 144, 'baseline_teammate': 10, 'baseline_available': 154,
                    'new_test_methods': counts.get('role4', 0) - 144,
                    'parsed_primary_artifacts': sorted(second), 'parsed_selected_artifacts': sorted(selected),
                    'repeat_ignored_keys': ['timestamp', 'evaluated_at'], 'repeat_differences': differences,
                    'imports': imports, 'imports_inside_clone': import_ok, 'changed_existing_files': changed,
                    'unexpected_existing_changes': sorted(set(changed) - CHANGED_EXISTING),
                    'original_teammate_files_checked': len(original_paths), 'original_teammate_files_changed': original_changed,
                    'historical_source_files_checked': len(baseline['before']['source']), 'historical_source_changes': source_changed,
                    'historical_phase_ab_document_changes': historical_changed, 'registry_unchanged': 'tests/role4/scenarios.json' not in changed,
                    'proposed_contribution_files': len(proposed), 'credential_pattern_findings': credential_findings,
                    'excluded_material_findings': excluded_findings, 'cache_directories': caches,
                    'human_reviews_pending': reviews_pending, 'automated_phase_c_verified': success,
                    'team_release_gate_passed': False,
                    'branch': subprocess.check_output(['git', '-c', f'safe.directory={ROOT.as_posix()}', 'branch', '--show-current'], cwd=ROOT, text=True).strip(),
                    'head': subprocess.check_output(['git', '-c', f'safe.directory={ROOT.as_posix()}', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                    'fetched_origin_main': subprocess.check_output(['git', '-c', f'safe.directory={ROOT.as_posix()}', 'rev-parse', 'origin/main'], cwd=ROOT, text=True).strip()}
    write_json(DOCS / 'phase_c_verification.json', verification)
    print(f"Phase C automated verification: {success}; full team discovery: {verification['collection_status']}")
    return 0 if success else 1


if __name__ == '__main__':
    raise SystemExit(main())
