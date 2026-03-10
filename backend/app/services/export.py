"""Data export service."""

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

import structlog

logger = structlog.get_logger()


class ExportFormat:
    """Supported export formats."""

    CSV = "csv"
    JSON = "json"
    PARQUET = "parquet"


class DataExporter:
    """Service for exporting data in various formats."""

    def export_to_json(
        self,
        data: list[dict[str, Any]],
        pretty: bool = False,
    ) -> str:
        """Export data to JSON format."""
        if pretty:
            return json.dumps(data, indent=2, default=str)
        return json.dumps(data, default=str)

    def export_to_csv(
        self,
        data: list[dict[str, Any]],
        include_headers: bool = True,
    ) -> str:
        """Export data to CSV format."""
        import csv
        import io

        if not data:
            return ""

        output = io.StringIO()

        # Get all fieldnames from all records
        fieldnames = set()
        for record in data:
            fieldnames.update(record.keys())
        fieldnames = sorted(fieldnames)

        writer = csv.DictWriter(output, fieldnames=fieldnames)

        if include_headers:
            writer.writeheader()

        for record in data:
            # Convert complex types to strings
            row = {}
            for key, value in record.items():
                if isinstance(value, (dict, list)):
                    row[key] = json.dumps(value)
                elif isinstance(value, datetime):
                    row[key] = value.isoformat()
                else:
                    row[key] = value
            writer.writerow(row)

        return output.getvalue()

    async def export_to_parquet(
        self,
        data: list[dict[str, Any]],
        file_path: str,
    ) -> bool:
        """Export data to Parquet format (requires pyarrow)."""
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError:
            logger.error("pyarrow_not_installed")
            return False

        if not data:
            return False

        # Convert to Arrow table
        # This is simplified - real implementation would handle nested types
        table = pa.Table.from_pylist(data)

        # Write to parquet
        pq.write_table(table, file_path)

        logger.info("data_exported_parquet", file_path=file_path, rows=len(data))
        return True


class ColdStorageManager:
    """Manager for cold storage (long-term archive)."""

    def __init__(
        self,
        hot_days: int = 7,
        warm_days: int = 30,
        archive_path: str = "/data/archive",
    ) -> None:
        self.hot_days = hot_days
        self.warm_days = warm_days
        self.archive_path = archive_path

    def should_archive(self, created_at: datetime) -> bool:
        """Check if data should be archived."""
        age = datetime.now(UTC) - created_at
        return age.days > self.warm_days

    async def archive_data(
        self,
        data: list[dict[str, Any]],
        partition_key: str,
    ) -> str | None:
        """Archive data to cold storage."""
        import os

        if not data:
            return None

        # Create partition path
        date_str = datetime.now(UTC).strftime("%Y/%m/%d")
        partition_path = os.path.join(
            self.archive_path,
            partition_key,
            date_str,
        )

        os.makedirs(partition_path, exist_ok=True)

        # Write to parquet
        file_name = f"{datetime.now(UTC).strftime('%H%M%S')}.parquet"
        file_path = os.path.join(partition_path, file_name)

        exporter = DataExporter()
        success = await exporter.export_to_parquet(data, file_path)

        if success:
            logger.info(
                "data_archived",
                file_path=file_path,
                records=len(data),
            )
            return file_path

        return None

    async def retrieve_archived_data(
        self,
        partition_key: str,
        start_date: datetime,
        end_date: datetime,
    ) -> list[dict[str, Any]]:
        """Retrieve data from cold storage."""
        import os

        try:
            import pyarrow.parquet as pq
        except ImportError:
            logger.error("pyarrow_not_installed")
            return []

        data = []

        # Iterate through date range
        current = start_date
        while current <= end_date:
            date_path = os.path.join(
                self.archive_path,
                partition_key,
                current.strftime("%Y/%m/%d"),
            )

            if os.path.exists(date_path):
                for filename in os.listdir(date_path):
                    if filename.endswith(".parquet"):
                        file_path = os.path.join(date_path, filename)
                        try:
                            table = pq.read_table(file_path)
                            data.extend(table.to_pylist())
                        except Exception as e:
                            logger.warning(
                                "archive_read_error",
                                file_path=file_path,
                                error=str(e),
                            )

            current += timedelta(days=1)

        return data


# Need to import timedelta
from datetime import timedelta


# Global instances
data_exporter = DataExporter()
cold_storage_manager = ColdStorageManager()
