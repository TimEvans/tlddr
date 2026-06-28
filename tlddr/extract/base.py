from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from tlddr.models import ExtractedDoc


@dataclass(frozen=True)
class ExtractContext:
    asset_dir: Path


Extractor = Callable[[Path, ExtractContext], ExtractedDoc]
