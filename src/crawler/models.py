"""Public data contracts. Dates remain nullable ISO strings."""
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any
from .config import CrawlerConfig

class Stage(StrEnum):
    DISCOVERY='discovery'
    METADATA='metadata'
    SOURCE='source'
    REFERENCES='references'

class Status(StrEnum):
    PENDING='pending'
    RUNNING='running'
    SUCCEEDED='succeeded'
    NO_TEX='no_tex'
    NOT_FOUND='not_found'
    FAILED='failed'

@dataclass(frozen=True)
class JobKey:
    arxiv_id: str
    stage: Stage
    version: int | None = None
    page_offset: int | None = None
    cycle_id: int = 1
    def as_tuple(self): return (self.arxiv_id,self.version or 0,self.stage.value,self.page_offset or 0)

@dataclass
class PaperMetadata:
    arxiv_id: str
    version: int
    title: str | None = None
    authors: list[str] = field(default_factory=list)
    published: str | None = None
    updated: str | None = None
    abstract: str | None = None
    categories: list[str] = field(default_factory=list)
    journal_ref: str | None = None
    doi: str | None = None
    venue: str | None = None

@dataclass
class VersionMetadata(PaperMetadata):
    pass

@dataclass
class SourceResult:
    status: Status
    compressed_bytes: int
    unpacked_bytes: int
    kept_bytes: int
    tex_count: int
    bib_count: int
    discarded_files: int
    sha256: str

@dataclass
class ReferencePage:
    next: int | None
    references: list[dict[str,Any]]
    unresolved_count: int = 0

@dataclass
class JobResult:
    status: Status
    error_code: str = ''
    error_message: str = ''

@dataclass
class RequestSpec:
    service: str
    url: str
    method: str = 'GET'
    params: dict[str,Any] = field(default_factory=dict)
    stream_target: Path | None = None

@dataclass
class ResponseArtifact:
    status_code: int
    path: Path | None = None
    content: bytes | None = field(default=None,repr=False)

@dataclass
class Event:
    name: str
    fields: dict[str,Any] = field(default_factory=dict)

RunSummary = dict[str,Any]
ExportManifest = dict[str,Any]
