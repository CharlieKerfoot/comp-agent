from __future__ import annotations

import csv
from pathlib import Path


class ValidationError(Exception):
    pass


class OutputValidator:
    def validate(self, output_path: str, submission_format: str) -> tuple[bool, str]:
        path = Path(output_path)

        if not path.exists():
            return False, f"Output file not found: {output_path}"

        if path.stat().st_size == 0:
            return False, "Output file is empty"

        # Try CSV validation if format mentions csv
        if "csv" in submission_format.lower():
            return self._validate_csv(path, submission_format)

        # For non-CSV, just check file exists and is non-empty
        return True, "Output file exists and is non-empty"

    def _validate_csv(self, path: Path, format_desc: str) -> tuple[bool, str]:
        try:
            with open(path) as f:
                reader = csv.reader(f)
                header = next(reader, None)
                if header is None:
                    return False, "CSV file has no header row"

                row_count = sum(1 for _ in reader)
                if row_count == 0:
                    return False, "CSV file has header but no data rows"

                return True, f"CSV valid: {len(header)} columns, {row_count} rows"
        except csv.Error as e:
            return False, f"CSV parsing error: {e}"
        except Exception as e:
            return False, f"Validation error: {e}"
