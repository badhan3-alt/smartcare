"""Private storage and bounded PDF structure checks, not PDF sanitization."""

import os
import re
import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


MAX_REPORT_SIZE = 10 * 1024 * 1024
REPORT_EXTENSIONS = {'.pdf'}


@deconstructible
class PrivateReportStorage(FileSystemStorage):
    @property
    def base_location(self):
        return settings.SMARTCARE_REPORT_ROOT

    @property
    def location(self):
        return os.path.abspath(self.base_location)

    def url(self, name):
        raise ValueError('Medical reports require an authenticated download.')


def report_upload_path(instance, filename):
    # Keep patient names and user-supplied filenames out of filesystem paths.
    extension = Path(filename).suffix.lower()
    return f'reports/{uuid.uuid4().hex}{extension}'


def validate_report_file(upload):
    extension = Path(upload.name).suffix.lower()
    if extension not in REPORT_EXTENSIONS:
        raise ValidationError('Upload a PDF file. Images and other file types are not accepted.')
    if upload.size == 0:
        raise ValidationError('The report file is empty.')
    if upload.size > MAX_REPORT_SIZE:
        raise ValidationError('The report must be 10 MB or smaller.')

    # Reject renamed/truncated files using the required PDF header and final xref.
    # Do not decompress streams or execute/parse PDF actions during validation.
    # Browser isolation is still required: structure checks do not sanitize PDFs.
    try:
        upload.seek(0)
        header = upload.read(16)
        if not re.match(rb'%PDF-(?:1\.[0-7]|2\.0)(?:\r\n|[\r\n])', header):
            raise ValidationError('The file contents do not match a PDF document.')
        upload.seek(max(0, upload.size - 2048))
        footer = upload.read(2048)
        final_xref = re.search(rb'startxref\s+([0-9]{1,10})\s+%%EOF[\x00\t\n\f\r ]*$', footer)
        if final_xref is None:
            raise ValidationError('The PDF is incomplete or has an invalid document structure.')
        xref_offset = int(final_xref.group(1))
        if xref_offset >= upload.size:
            raise ValidationError('The PDF contains an invalid cross-reference offset.')
        upload.seek(xref_offset)
        xref = upload.read(4096)
        is_table = xref.startswith(b'xref') and b'trailer' in footer
        is_stream = (
            re.match(rb'[0-9]+\s+[0-9]+\s+obj\b', xref)
            and re.search(rb'/Type\s*/XRef\b', xref)
        )
        if not (is_table or is_stream):
            raise ValidationError('The PDF contains an invalid cross-reference structure.')
    finally:
        upload.seek(0)
