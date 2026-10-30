"""Arabic NER offset validator: checks character offsets, normalisation drift, clitic and grapheme
boundaries, overlaps and BIO/BIOES/BILUO tags in Arabic entity annotations."""
__version__ = "0.1.0"

from .report import csv_report, share_report, validate  # noqa: E402

__all__ = ["__version__", "validate", "share_report", "csv_report"]
