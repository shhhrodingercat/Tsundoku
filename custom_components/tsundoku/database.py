import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path

from .models import ReleaseLine, Volume


class MangaDatabase:
    """Read manga release metadata from the local SQLite database."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(
            f"file:{self.path.as_posix()}?mode=ro",
            uri=True,
        )

    def search_release_lines(
        self,
        query: str,
        *,
        country: str | None = None,
        language: str | None = None,
        limit: int = 100,
    ) -> list[ReleaseLine]:
        """Search release lines, prioritizing exact and prefix matches."""
        query = query.strip()
        if not query:
            return []

        pattern = f"%{query}%"
        prefix = f"{query}%"
        sql = """
            SELECT DISTINCT
                s.gcd_series_id,
                s.tome_id,
                s.name,
                s.local_name,
                s.publisher,
                s.language,
                s.country,
                s.medium,
                s.volume_count,
                s.status
            FROM series AS s
            LEFT JOIN series_alias AS a
                ON a.gcd_series_id = s.gcd_series_id
            WHERE s.medium = 'manga'
              AND s.tome_id IS NOT NULL
              AND (
                    s.name LIKE ?
                    OR s.local_name LIKE ?
                    OR a.alias LIKE ?
              )
        """
        params: list[object] = [pattern, pattern, pattern]

        if country:
            sql += " AND s.country = ?"
            params.append(country)
        if language:
            sql += " AND s.language = ?"
            params.append(language)

        sql += """
            ORDER BY
                CASE
                    WHEN lower(s.name) = lower(?) THEN 0
                    WHEN lower(s.name) LIKE lower(?) THEN 1
                    WHEN lower(s.local_name) = lower(?) THEN 2
                    WHEN lower(s.local_name) LIKE lower(?) THEN 3
                    ELSE 4
                END,
                s.name COLLATE NOCASE,
                s.country,
                s.publisher
            LIMIT ?
        """
        params.extend([query, prefix, query, prefix, max(1, min(limit, 500))])

        with closing(self._connect()) as conn:
            rows = conn.execute(sql, params).fetchall()

        return [self._release_line_from_row(row) for row in rows]

    def get_release_line(self, tome_id: str) -> ReleaseLine | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT
                    s.gcd_series_id, s.tome_id, s.name, s.local_name,
                    s.publisher, s.language, s.country, s.medium,
                    s.volume_count, s.status
                FROM series AS s
                WHERE s.tome_id = ?
                """,
                (tome_id,),
            ).fetchone()

            if row is not None:
                return self._release_line_from_row(row)

            redirect = conn.execute(
                "SELECT new_tome_id FROM id_redirect WHERE old_tome_id = ?",
                (tome_id,),
            ).fetchone()
            if redirect is None:
                return None

            row = conn.execute(
                """
                SELECT
                    s.gcd_series_id, s.tome_id, s.name, s.local_name,
                    s.publisher, s.language, s.country, s.medium,
                    s.volume_count, s.status
                FROM series AS s
                WHERE s.tome_id = ?
                """,
                (redirect[0],),
            ).fetchone()

        return self._release_line_from_row(row) if row else None

    def get_volumes(self, series_id: int) -> list[Volume]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT
                    id, gcd_series_id, volume_number, title,
                    release_date, release_date_precision, release_date_raw,
                    release_date_type, isbn13, tome_id
                FROM volumes
                WHERE gcd_series_id = ?
                ORDER BY volume_number
                """,
                (series_id,),
            ).fetchall()
        return [self._volume_from_row(row) for row in rows]

    def get_latest_volume(self, series_id: int, today: date) -> Volume | None:
        """Return the latest volume known to have been published.

        Coarse dates are considered published only when their whole month/year
        is in the past. This avoids treating an imprecise current-month date as
        proof that a volume has already appeared.
        """
        current_month = today.strftime("%Y-%m")
        current_year = str(today.year)
        with closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT
                    id, gcd_series_id, volume_number, title,
                    release_date, release_date_precision, release_date_raw,
                    release_date_type, isbn13, tome_id
                FROM volumes
                WHERE gcd_series_id = ?
                  AND (
                        (release_date IS NOT NULL AND release_date <= ?)
                        OR (
                            release_date IS NULL
                            AND release_date_type = 'published'
                            AND (
                                (release_date_precision = 'month'
                                 AND release_date_raw < ?)
                                OR
                                (release_date_precision = 'year'
                                 AND release_date_raw < ?)
                            )
                        )
                  )
                ORDER BY
                    COALESCE(
                        release_date,
                        CASE
                            WHEN release_date_precision = 'month'
                                THEN release_date_raw || '-99'
                            WHEN release_date_precision = 'year'
                                THEN release_date_raw || '-99-99'
                            ELSE release_date_raw
                        END
                    ) DESC,
                    volume_number DESC
                LIMIT 1
                """,
                (series_id, today.isoformat(), current_month, current_year),
            ).fetchone()
        return self._volume_from_row(row) if row else None

    def get_next_volume(self, series_id: int, today: date) -> Volume | None:
        """Return the next dated or future month-precision release.

        A month-precision release is eligible when its month is current or
        future and its milestone is not marked as already published.
        """
        current_month = today.strftime("%Y-%m")
        with closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT
                    id, gcd_series_id, volume_number, title,
                    release_date, release_date_precision, release_date_raw,
                    release_date_type, isbn13, tome_id
                FROM volumes
                WHERE gcd_series_id = ?
                  AND (
                        (release_date IS NOT NULL AND release_date > ?)
                        OR (
                            release_date IS NULL
                            AND release_date_precision = 'month'
                            AND release_date_raw >= ?
                            AND COALESCE(release_date_type, 'unknown') != 'published'
                        )
                  )
                ORDER BY
                    COALESCE(release_date, release_date_raw || '-01') ASC,
                    CASE WHEN release_date IS NOT NULL THEN 0 ELSE 1 END ASC,
                    volume_number ASC
                LIMIT 1
                """,
                (series_id, today.isoformat(), current_month),
            ).fetchone()
        return self._volume_from_row(row) if row else None

    def get_published_volume_count(self, series_id: int, today: date) -> int:
        """Count volumes with a known past publication date."""
        with closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT COUNT(*)
                FROM volumes
                WHERE gcd_series_id = ?
                  AND (
                        (release_date IS NOT NULL AND release_date <= ?)
                        OR (
                            release_date IS NULL
                            AND release_date_type = 'published'
                            AND (
                                (release_date_precision = 'month'
                                 AND release_date_raw < ?)
                                OR
                                (release_date_precision = 'year'
                                 AND release_date_raw < ?)
                            )
                        )
                  )
                """,
                (
                    series_id,
                    today.isoformat(),
                    today.strftime("%Y-%m"),
                    str(today.year),
                ),
            ).fetchone()
        return int(row[0]) if row else 0

    @staticmethod
    def _release_line_from_row(row: tuple) -> ReleaseLine:
        return ReleaseLine(
            id=row[0],
            tome_id=row[1],
            name=row[2],
            local_name=row[3],
            publisher=row[4],
            language=row[5],
            country=row[6],
            medium=row[7],
            volume_count=row[8],
            status=row[9],
        )

    @staticmethod
    def _volume_from_row(row: tuple) -> Volume:
        release_date = date.fromisoformat(row[4]) if row[4] else None
        return Volume(
            id=row[0],
            series_id=row[1],
            number=row[2],
            title=row[3],
            release_date=release_date,
            release_date_precision=row[5],
            release_date_raw=row[6],
            release_date_type=row[7],
            isbn13=row[8],
            tome_id=row[9],
        )
