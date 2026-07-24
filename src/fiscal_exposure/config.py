"""Configuration.

Every path, column name and analysis parameter lives in ``config/config.yaml``
rather than in code, so that a result can be traced back to the exact inputs and
settings that produced it. Nothing in this package reads a hard-coded path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = Path("config/config.yaml")


def _resolve(root: Path, value: str) -> Path:
    p = Path(value)
    return p if p.is_absolute() else (root / p)


@dataclass(frozen=True)
class Paths:
    root: Path
    raw: Path
    interim: Path
    figures: Path
    tables: Path
    manifest: Path

    @classmethod
    def from_dict(cls, root: Path, d: dict[str, Any]) -> Paths:
        return cls(
            root=root,
            raw=_resolve(root, d["raw"]),
            interim=_resolve(root, d["interim"]),
            figures=_resolve(root, d["figures"]),
            tables=_resolve(root, d["tables"]),
            manifest=_resolve(root, d["manifest"]),
        )

    def ensure(self) -> None:
        for p in (self.raw, self.interim, self.figures, self.tables):
            p.mkdir(parents=True, exist_ok=True)
        self.manifest.parent.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class ExposureCfg:
    """Where the AI exposure scores come from and how to read them.

    ``occ_col`` and ``score_col`` may be left null in the config, in which case
    :mod:`fiscal_exposure.exposure` will attempt to detect them and report what
    it found. Once the real schema is known they should be pinned explicitly.
    """

    source: str
    file_glob: str
    occ_col: str | None = None
    score_col: str | None = None
    occ_code_kind: str = "onet_soc"  # onet_soc | soc2018 | cps_occ
    score_range: tuple[float, float] = (0.0, 1.0)


@dataclass(frozen=True)
class CPSCfg:
    source: str  # ipums | census
    file_glob: str
    weight_col: str
    occ_col: str
    wage_col: str
    year_col: str
    min_age: int = 16
    max_age: int = 99
    require_positive_wage: bool = True


@dataclass(frozen=True)
class CrosswalkCfg:
    source: str
    file_glob: str
    from_col: str
    to_col: str
    weight_col: str | None = None  # OES employment, for many-to-one aggregation


@dataclass(frozen=True)
class AnalysisCfg:
    n_quantiles: int = 4
    quantile_weight: str = "employment"  # employment | occupation
    treatment_cutoffs: list[float] = field(
        default_factory=lambda: [0.50, 0.60, 0.70, 0.75, 0.90, 0.95]
    )
    zero_exposure_threshold: float = 0.0
    payroll_taxable_max: float | None = None  # SSA contribution and benefit base
    seed: int = 20260726


@dataclass(frozen=True)
class Config:
    paths: Paths
    exposure: ExposureCfg
    cps: CPSCfg
    crosswalk: CrosswalkCfg
    analysis: AnalysisCfg
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> Config:
    """Load and validate the project configuration."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"No config at {path}. Copy config/config.example.yaml to {path}."
        )
    with path.open("r", encoding="utf-8") as fh:
        d = yaml.safe_load(fh)

    root = path.resolve().parent.parent
    cfg = Config(
        paths=Paths.from_dict(root, d["paths"]),
        exposure=ExposureCfg(**d["exposure"]),
        cps=CPSCfg(**d["cps"]),
        crosswalk=CrosswalkCfg(**d["crosswalk"]),
        analysis=AnalysisCfg(**d.get("analysis", {})),
        raw=d,
    )
    cfg.paths.ensure()
    return cfg
