"""CRDT type identifiers."""

from enum import Enum


class CrdtType(str, Enum):
    GCOUNTER = "gcounter"
    PNCOUNTER = "pncounter"
    ORSET = "orset"
    MVREGISTER = "mvregister"
