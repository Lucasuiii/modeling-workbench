"""Build and inspect actual delivery ZIPs from existing contracts, without new hashes.

Archive members retain project-relative paths. This verifies files and bytes, not
that arbitrary programs will run; an isolated execution remains a separate check.
"""
from __future__ import annotations

import json
import os
import tempfile
import zipfile
from pathlib import Path

from canonical_evidence import resolve_official_computation

SOURCE_SUFFIXES = {'.py', '.m', '.r', '.jl', '.ipynb', '.sh'}


def read_object(root: Path, rel: str) -> dict:
    return json.loads((root / rel).read_text(encoding='utf-8'))


def local_file(root: Path, rel: str) -> Path:
    path = (root / rel).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError(f'missing or unsafe delivery dependency: {rel}')
    return path


def live_path(rel: str) -> str:
    parts = Path(rel).parts
    if len(parts) > 3 and parts[0] == 'runs' and parts[2] in {'source', 'inputs', 'outputs'}:
        return Path(*parts[3:]).as_posix()
    return rel


def archive_members(root: Path, manifest: dict) -> dict[str, dict[str, str]]:
    """One membership calculation is used by the packer and by the checker."""
    deliverables = manifest.get('deliverables', {})
    result = {}
    if not any(deliverables.get(role, {}).get('archive') for role in ('computation_source', 'editable_latex_source')):
        return result
    archive_paths = {item.get('archive') for item in deliverables.values() if isinstance(item, dict) and item.get('archive')}
    archive_targets = {(root / rel).resolve() for rel in archive_paths}
    support = set()
    canonical = {}
    declared_editable = set()
    index = root / 'results/RESULTS_INDEX.json'
    if index.exists():
        for run in resolve_official_computation(root, read_object(root, 'results/RESULTS_INDEX.json')):
            for kind in ('source_files', 'formal_inputs', 'claim_bearing_outputs'):
                for rel in run[kind]:
                    member = live_path(str(rel))
                    previous = canonical.get(member)
                    if previous and local_file(root, previous).read_bytes() != local_file(root, rel).read_bytes():
                        raise ValueError(f'conflicting frozen evidence for archive member: {member}')
                    canonical[member] = rel
                    support.add(member)
    for entry in manifest.get('files', []):
        if (root / entry['path']).resolve() in archive_targets:
            continue
        if entry.get('role') == 'editable_latex_source':
            declared_editable.add(entry['path'])
        if entry.get('role') in {'computation_source', 'supporting_evidence'}:
            support.add(entry['path'])
    latex = root / 'paper/LATEX_TEMPLATE_MANIFEST.json'
    editable = set(read_object(root, 'paper/LATEX_TEMPLATE_MANIFEST.json').get('required_files', [])) if latex.exists() else set()
    editable.update(declared_editable)
    receipt_path = root / 'delivery/COMPILE_RECEIPT.json'
    if deliverables.get('editable_latex_source', {}).get('archive') and receipt_path.is_file():
        from provenance import snapshot_matches
        snapshot = read_object(root, 'delivery/COMPILE_RECEIPT.json').get('source_snapshot')
        if not snapshot_matches(root, snapshot):
            raise ValueError('compile source snapshot is stale; recompile before packaging')
        editable.update(snapshot['files'])
    # Figure-generation code is an editable dependency, even when figures already exist.
    for directory in ('paper/figures', 'figures'):
        if (root / directory).is_dir():
            support.update(p.relative_to(root).as_posix() for p in (root / directory).rglob('*')
                           if p.is_file() and p.suffix.lower() in SOURCE_SUFFIXES and '__pycache__' not in p.parts)
    for role, files in [('computation_source', support), ('editable_latex_source', editable | support)]:
        item = deliverables.get(role, {})
        if item.get('archive'):
            members = set(files)
            if item.get('entrypoint'):
                members.add(item['entrypoint'])
            bindings = {}
            for rel in members:
                if Path(rel).is_absolute() or '..' in Path(rel).parts or '\\' in rel:
                    raise ValueError(f'unsafe archive member: {rel}')
                source = canonical.get(rel, rel)
                local_file(root, source)
                bindings[rel] = source
            archive = (root / item['archive']).resolve()
            if not archive.is_relative_to(root.resolve()) or archive.suffix.lower() != '.zip':
                raise ValueError('delivery archive must be a project-local ZIP')
            if any(local_file(root, source) in archive_targets for source in bindings.values()):
                raise ValueError('an archive cannot include itself')
            key = archive.relative_to(root.resolve()).as_posix()
            result.setdefault(key, {}).update(bindings)
    return result


def check_archives(root: Path, manifest: dict) -> list[str]:
    problems = []
    try:
        archives = archive_members(root, manifest)
    except (ValueError, OSError, KeyError) as exc:
        return [str(exc)]
    for rel, members in archives.items():
        try:
            with zipfile.ZipFile(local_file(root, rel)) as archive:
                names = archive.namelist()
                if len(names) != len(set(names)):
                    problems.append(f'{rel}: duplicate member names')
                for name in names:
                    if Path(name).is_absolute() or '..' in Path(name).parts or '\\' in name:
                        problems.append(f'{rel}: unsafe member {name}')
                for extra in sorted(set(names) - set(members)):
                    problems.append(f'{rel}: unexpected member {extra}')
                for member in sorted(members):
                    if member not in names:
                        problems.append(f'{rel}: missing {member}; preserve project-relative directories')
                    elif archive.read(member) != local_file(root, members[member]).read_bytes():
                        problems.append(f'{rel}: stale member {member}')
        except (OSError, ValueError, zipfile.BadZipFile, RuntimeError) as exc:
            problems.append(f'{rel}: {exc}')
    return problems


def build_archives(root: Path, manifest: dict) -> None:
    archives = archive_members(root, manifest)
    for rel, members in archives.items():
        destination = root / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=destination.parent, suffix='.zip')
        os.close(fd)
        try:
            with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as archive:
                for member in sorted(members):
                    archive.write(local_file(root, members[member]), member)
            os.replace(temporary, destination)
        finally:
            Path(temporary).unlink(missing_ok=True)
        print(f'packaged {rel}: {len(members)} files, project-relative paths preserved')
