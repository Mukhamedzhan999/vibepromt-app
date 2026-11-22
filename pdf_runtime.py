"""Serialize PyMuPDF access across auditing and export in the same process."""

from threading import Lock

PDF_LOCK = Lock()
