"""Proposed loupe4py contract; declarations only, not an implemented module."""

from dataclasses import dataclass
from typing import Literal, TypedDict


class Params(TypedDict):
    document: str
    offset: int


@dataclass(frozen=True, slots=True)
class Document:
    session_id: str
    document_id: str
    uri: str


@dataclass(frozen=True, slots=True)
class ByteRange:
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class Origin:
    document: Document
    revision: int
    space: Literal["source", "expansion"]
    expansion_id: str | None


@dataclass(frozen=True, slots=True)
class HoverItem:
    code: str
    path: str | None
    doc: str | None


@dataclass(frozen=True, slots=True)
class Hover:
    origin: Origin
    range: ByteRange
    items: tuple[HoverItem, ...]


@dataclass(frozen=True, slots=True)
class Diagnostic:
    origin: Origin
    range: ByteRange
    severity: Literal["error", "warning", "hint"]
    message: str
    unnecessary: bool


@dataclass(frozen=True, slots=True)
class NavigationTarget:
    origin: Origin
    full_range: ByteRange
    focus_range: ByteRange


class AnalysisCancelledError(RuntimeError): ...
class StaleContextError(RuntimeError): ...
class ForeignContextError(ValueError): ...
class DocumentNotFoundError(LookupError): ...
class AnalysisError(RuntimeError): ...


class Analysis:
    """Host-created, read-only context for one script; no public constructor."""

    @property
    def session_id(self) -> str: ...
    @property
    def context_id(self) -> str: ...
    @property
    def revision(self) -> int: ...

    def check_cancelled(self) -> None: ...
    def document(self, uri: str, /) -> Document: ...
    def text(self, document: Document, /, *, range: ByteRange | None = None) -> str: ...
    def hover(self, document: Document, offset: int, /) -> Hover | None: ...
    def diagnostics(self, document: Document, /) -> tuple[Diagnostic, ...]: ...
    def definition(self, document: Document, offset: int, /) -> tuple[NavigationTarget, ...]: ...
