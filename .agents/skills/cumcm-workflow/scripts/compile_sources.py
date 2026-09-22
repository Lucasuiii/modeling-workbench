"""Resolve project inputs observed by the TeX recorder, excluding its outputs."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def runtime_roots() -> list[Path]:
    """Only installed TeX trees and operating-system fonts may remain external."""
    roots = [Path(p) for p in ('/System/Library/Fonts', '/Library/Fonts', '/usr/share/fonts', '/usr/local/share/fonts')]
    roots.extend([Path.home() / 'Library/Fonts', Path.home() / '.local/share/fonts'])
    if os.environ.get('WINDIR'):
        roots.append(Path(os.environ['WINDIR']) / 'Fonts')
    kpsewhich = shutil.which('kpsewhich')
    if kpsewhich:
        for var in ('TEXMFROOT', 'TEXMFDIST', 'TEXMFDEBIAN', 'TEXMFLOCAL', 'TEXMFSYSVAR', 'TEXMFSYSCONFIG', 'TEXMFVAR', 'TEXMFHOME'):
            result = subprocess.run([kpsewhich, '-var-value=' + var], capture_output=True, text=True, check=False, timeout=30)
            value = result.stdout.strip()
            if result.returncode == 0 and value and Path(value).is_absolute():
                roots.append(Path(value).resolve())
    return [root.resolve() for root in roots]


def observed_sources(root: Path, work_dir: Path, fls: Path, external_roots: list[Path]) -> set[str]:
    if not fls.is_file():
        raise ValueError('TeX recorder output is missing; cannot bind actual sources')
    inputs, outputs = set(), set()
    for line in fls.read_text(encoding='utf-8', errors='strict').splitlines():
        kind, _, value = line.partition(' ')
        if kind not in {'INPUT', 'OUTPUT'} or not value:
            continue
        path = (work_dir / value).resolve()
        (inputs if kind == 'INPUT' else outputs).add(path)
    if not inputs:
        raise ValueError('TeX recorder contains no inputs')
    for path in inputs & outputs:
        if path.is_relative_to(root) and path.suffix.lower() in {'.tex', '.sty', '.cls', '.bib', '.bbl', '.png', '.jpg', '.jpeg'}:
            raise ValueError(f'editable input was also written during compilation: {path}')
    sources = set()
    for path in inputs - outputs:
        if path.is_relative_to(root):
            if not path.is_file():
                raise ValueError(f'compiled input is missing: {path}')
            sources.add(path.relative_to(root).as_posix())
        elif not any(path.is_relative_to(base) for base in external_roots):
            raise ValueError(f'external project dependency must be copied into the project: {path}')
    return sources
