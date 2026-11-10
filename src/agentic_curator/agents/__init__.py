"""The agent roster.

    OrchestratorAgent     plans, fans out, assembles  (owns no files)
    YearAgent             one instance per year        (fingerprints a slice)
    DocumentAgent         text + PDF -> subject keys
    DuplicateAgent        identical and near-identical documents
    PhotoDuplicateAgent   perceptually identical photos
    ConsolidatorAgent     merge same-subject documents, verified
    DeletionAgent         the only one that may move a file

Add a seventh by writing a class with `handles = ("your.kind",)` and
registering it in `runtime.py`. Nothing else has to change.
"""

from .consolidator_agent import ConsolidatorAgent
from .deletion_agent import DeletionAgent
from .document_agent import DocumentAgent
from .duplicate_agent import DuplicateAgent
from .orchestrator import OrchestratorAgent
from .photo_agent import PhotoDuplicateAgent
from .year_agent import YearAgent

__all__ = [
    "ConsolidatorAgent",
    "DeletionAgent",
    "DocumentAgent",
    "DuplicateAgent",
    "OrchestratorAgent",
    "PhotoDuplicateAgent",
    "YearAgent",
]
