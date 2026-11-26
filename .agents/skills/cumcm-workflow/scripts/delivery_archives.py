"""Build and inspect actual delivery ZIPs from existing contracts, without new hashes.

Archive members retain project-relative paths. This verifies files and bytes, not
that arbitrary programs will run; an isolated execution remains a separate check.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from canonical_evidence import resolve_official_computation

INTERNAL_ARCHIVE = '.cumcm/reproduction.zip'
SUPPORT_ROLES = {'computation_source', 'supporting_evidence'}
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


def official_sources(root: Path) -> set[str]:
    if not (root / 'problem/SOURCE_MANIFEST.json').is_file():
        return set()
    sources = read_object(root, 'problem/SOURCE_MANIFEST.json').get('sources', [])
    return {item['path'] for item in sources if isinstance(item, dict)
            and item.get('origin') in {'official', 'organizer_attachment'}}


def is_official(member: str, sources: set[str]) -> bool:
    return member.startswith('problem/official/') or member in sources


def archive_members(root: Path, manifest: dict, *, internal_reproduction: bool = False) -> dict[str, dict[str, str]]:
    """One membership calculation is used by the packer and by the checker."""
    deliverables = manifest.get('deliverables', {})
    result = {}
    archive_paths = {item.get('archive') for item in deliverables.values() if isinstance(item, dict) and item.get('archive')}
    private = (root / INTERNAL_ARCHIVE).resolve()
    declared = archive_paths | {entry['path'] for entry in manifest.get('files', [])}
    if any((root / rel).resolve() == private for rel in declared):
        raise ValueError('internal reproduction ZIP must be separate from delivery archives')
    if not internal_reproduction and not any(deliverables.get(role, {}).get('archive') for role in ('computation_source', 'editable_latex_source')):
        return result
    archive_paths.add(INTERNAL_ARCHIVE)
    archive_targets = {(root / rel).resolve() for rel in archive_paths}
    support = set()
    canonical = {}
    official_paths = official_sources(root)
    excluded = {path for path in manifest.get('excluded_files', []) if isinstance(path, str)}
    declared_support = set()
    declared_editable = set()
    index = root / 'results/RESULTS_INDEX.json'
    if index.exists() and (internal_reproduction or deliverables.get('computation_source', {}).get('archive')):
        for run in resolve_official_computation(root):
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
        if entry.get('role') in SUPPORT_ROLES:
            declared_support.add(entry['path'])
    support.update(declared_support)
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
    # Generating a figure belongs to computation; its rendered file can be a TeX input.
    for directory in ('paper/figures', 'figures'):
        if (root / directory).is_dir():
            support.update(p.relative_to(root).as_posix() for p in (root / directory).rglob('*')
                           if p.is_file() and p.suffix.lower() in SOURCE_SUFFIXES and '__pycache__' not in p.parts)

    def excluded_from_delivery(member: str, allowed: set[str]) -> bool:
        original = live_path(member)
        return member in excluded or original in excluded or (is_official(original, official_paths) and member not in allowed)

    computation = deliverables.get('computation_source', {})
    submission = {path for path in support if not excluded_from_delivery(path, declared_support)}
    packages = [('computation_source', computation, submission),
                ('editable_latex_source', deliverables.get('editable_latex_source', {}), editable)]
    if internal_reproduction:
        packages.append(('internal_reproduction', {'archive': INTERNAL_ARCHIVE, 'entrypoint': computation.get('entrypoint')}, support))
    for role, item, files in packages:
        if item.get('archive'):
            members = set(files)
            if item.get('entrypoint'):
                members.add(item['entrypoint'])
            if role != 'internal_reproduction':
                explicit = declared_editable if role == 'editable_latex_source' else declared_support
                forbidden = sorted(rel for rel in members if excluded_from_delivery(rel, explicit))
                if forbidden:
                    raise ValueError(f'{role} requires files excluded from delivery: {", ".join(forbidden)}')
            bindings = {}
            for rel in members:
                if Path(rel).is_absolute() or '..' in Path(rel).parts or '\\' in rel:
                    raise ValueError(f'unsafe archive member: {rel}')
                source = rel if role == 'editable_latex_source' else canonical.get(rel, rel)
                local_file(root, source)
                bindings[rel] = source
            archive = (root / item['archive']).resolve()
            if not archive.is_relative_to(root.resolve()) or archive.suffix.lower() != '.zip':
                raise ValueError('delivery archive must be a project-local ZIP')
            if any(local_file(root, source) in archive_targets for source in bindings.values()):
                raise ValueError('an archive cannot include itself')
            key = archive.relative_to(root.resolve()).as_posix()
            if key in result and result[key] and bindings and result[key] != bindings:
                raise ValueError(f'declare separate ZIP destinations for different package contents: {key}')
            result.setdefault(key, {}).update(bindings)
    return result


def submitted_members(path: Path) -> list[str]:
    if path.suffix.lower() == '.zip':
        with zipfile.ZipFile(path) as archive:
            return [info.filename for info in archive.infolist() if not info.is_dir()]
    if path.suffix.lower() not in {'.rar', '.7z'}:
        raise ValueError(f'unsupported submission archive: {path.name}')
    # Windows ships libarchive as tar.exe; GNU tar cannot list RAR or 7z.
    binary = shutil.which('bsdtar') or (shutil.which('tar') if os.name == 'nt' else None)
    if binary:
        cmd = [binary, '-tf', str(path)]
    else:
        binary = shutil.which('7zz') or shutil.which('7z')
        if not binary:
            raise ValueError(f'install bsdtar or 7-Zip to inspect {path.name}')
        cmd = [binary, 'l', '-slt', '-ba', str(path)]
    listing = subprocess.run(cmd, capture_output=True, encoding='utf-8', check=True, timeout=60).stdout
    if cmd[1] == '-tf':
        return listing.splitlines()
    return [line.removeprefix('Path = ') for line in listing.splitlines() if line.startswith('Path = ')]


def check_submitted_archives(root: Path, manifest: dict, generated: set[str]) -> list[str]:
    entries = manifest.get('files', [])
    submissions = {item['path'] for item in entries if item.get('role') == 'submission_package'}
    rules = manifest.get('submission', {}).get('rules', {})
    submissions.update(item['path'] for item in rules.get('attachments', []))
    if not submissions:
        return []
    sources = official_sources(root)
    allowed = {item['path'] for item in entries if item.get('role') in SUPPORT_ROLES}
    excluded = {value for value in manifest.get('excluded_files', []) if isinstance(value, str)}
    forbidden = (sources - allowed) | excluded | {INTERNAL_ARCHIVE}
    flat_names = {Path(rel).name for rel in forbidden}
    problems = []
    for rel in sorted(submissions):
        try:
            path = local_file(root, rel)
            if path == (root / INTERNAL_ARCHIVE).resolve():
                raise ValueError('internal reproduction ZIP cannot be submitted')
            if rel in generated:
                continue  # Its full member set and exact bytes are already checked.
            for name in submitted_members(path):
                member = PurePosixPath(name.replace('\\', '/')).as_posix()
                if (member in forbidden or member in flat_names or live_path(member) in forbidden
                        or (is_official(live_path(member), sources) and member not in allowed)):
                    problems.append(f'{rel}: excluded submission member {name}')
        except (ValueError, OSError, subprocess.SubprocessError, zipfile.BadZipFile) as exc:
            problems.append(f'{rel}: {exc}')
    return problems


def check_archives(root: Path, manifest: dict) -> list[str]:
    problems = []
    try:
        archives = archive_members(root, manifest)
    except (ValueError, OSError, KeyError, TypeError, AttributeError) as exc:
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
    try:
        problems.extend(check_submitted_archives(root, manifest, set(archives)))
    except (ValueError, KeyError, TypeError, AttributeError, OSError) as exc:
        problems.append(f'invalid submission archive declarations: {exc}')
    return problems


def build_archives(root: Path, manifest: dict, *, internal_reproduction: bool = False) -> None:
    archives = archive_members(root, manifest, internal_reproduction=internal_reproduction)
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
