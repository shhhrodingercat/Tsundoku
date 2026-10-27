import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path
from urllib.parse import quote

from .models import ReleaseLine, Volume

# SQLite limits the number of variables of a query: stay well below it.
_ID_CHUNK = 500


class MangaDatabase:
    """Read manga release metadata from the local SQLite database."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        encoded_path = quote(str(self.path.resolve()), safe="/:")
        return sqlite3.connect(f"file:{encoded_path}?mode=ro", uri=True)

    def get_search_filter_options(self) -> tuple[list[str], list[str]]:
        """Return market/edition and language codes present in searchable manga."""
        with closing(self._connect()) as conn:
            countries = conn.execute(
                """
                SELECT DISTINCT country
                FROM series
                WHERE medium = 'manga'
                  AND tome_id IS NOT NULL
                  AND country IS NOT NULL
                  AND TRIM(country) != ''
                ORDER BY country COLLATE NOCASE
                """
            ).fetchall()
            languages = conn.execute(
                """
                SELECT DISTINCT language
                FROM series
                WHERE medium = 'manga'
                  AND tome_id IS NOT NULL
                  AND language IS NOT NULL
                  AND TRIM(language) != ''
                ORDER BY language COLLATE NOCASE
                """
            ).fetchall()
        return (
            [row[0] for row in countries],
            [row[0] for row in languages],
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

        # Treat user input literally: '%' and '_' are SQL LIKE wildcards.
        escaped_query = query.replace("!", "!!").replace("%", "!%").replace("_", "!_")
        pattern = f"%{escaped_query}%"
        prefix = f"{escaped_query}%"
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
                    s.name LIKE ? ESCAPE '!'
                    OR s.local_name LIKE ? ESCAPE '!'
                    OR a.alias LIKE ? ESCAPE '!'
              )
        """
        params: list[object] = [pattern, pattern, pattern]

        if country:
            sql += " AND UPPER(s.country) = UPPER(?)"
            params.append(country.strip())
        if language:
            sql += " AND LOWER(s.language) = LOWER(?)"
            params.append(language.strip())

        sql += """
            ORDER BY
                CASE
                    WHEN lower(s.name) = lower(?) THEN 0
                    WHEN lower(s.name) LIKE lower(?) ESCAPE '!' THEN 1
                    WHEN lower(s.local_name) = lower(?) THEN 2
                    WHEN lower(s.local_name) LIKE lower(?) ESCAPE '!' THEN 3
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

    def get_series_ids_with_exact_dates(self, series_ids: list[int]) -> set[int]:
        """Return the series that have at least one volume with an exact day.

        Only those can have events in the calendar: volumes dated to a month or
        a year have no day to put an event on.
        """
        found: set[int] = set()
        with closing(self._connect()) as conn:
            for start in range(0, len(series_ids), _ID_CHUNK):
                chunk = series_ids[start : start + _ID_CHUNK]
                placeholders = ",".join("?" * len(chunk))
                rows = conn.execute(
                    f"""
                    SELECT DISTINCT gcd_series_id
                    FROM volumes
                    WHERE release_date IS NOT NULL
                      AND gcd_series_id IN ({placeholders})
                    """,
                    chunk,
                ).fetchall()
                found.update(row[0] for row in rows)
        return found

    def get_dated_volumes(
        self,
        series_id: int,
        start: date,
        end: date | None = None,
        limit: int | None = None,
    ) -> list[Volume]:
        """Return the volumes with an exact release date from ``start``.

        ``end`` is excluded and ``None`` means no end. Volumes dated to a month
        or a year are never returned.
        """
        sql = """
            SELECT
                id, gcd_series_id, volume_number, title,
                release_date, release_date_precision, release_date_raw,
                release_date_type, isbn13, tome_id
            FROM volumes
            WHERE gcd_series_id = ?
              AND release_date IS NOT NULL
              AND release_date >= ?
        """
        params: list[object] = [series_id, start.isoformat()]
        if end is not None:
            sql += " AND release_date < ?"
            params.append(end.isoformat())
        sql += " ORDER BY release_date, volume_number"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(max(1, limit))
        with closing(self._connect()) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._volume_from_row(row) for row in rows]

    def get_month_volumes(self, series_id: int, month: str) -> list[Volume]:
        """Return the volumes releasing in a month, given as ``YYYY-MM``.

        These are the volumes with an exact day in that month and the ones dated
        to the month only. Exact days come first.
        """
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT
                    id, gcd_series_id, volume_number, title,
                    release_date, release_date_precision, release_date_raw,
                    release_date_type, isbn13, tome_id
                FROM volumes
                WHERE gcd_series_id = ?
                  AND (
                        (release_date IS NOT NULL AND substr(release_date, 1, 7) = ?)
                        OR (
                            release_date IS NULL
                            AND release_date_precision = 'month'
                            AND release_date_raw = ?
                        )
                  )
                ORDER BY
                    COALESCE(release_date, release_date_raw || '-99'),
                    volume_number
                """,
                (series_id, month, month),
            ).fetchall()
        return [self._volume_from_row(row) for row in rows]

    def get_latest_volume(self, series_id: int, today: date) -> Volume | None:
        """Return the latest volume known to have been published.

        A volume with an exact date is published from the day after its release,
        so that on the release day it is still the next volume and automations
        can act on it. Coarse dates are considered published only when their
        whole month/year is in the past. This avoids treating an imprecise
        current-month date as proof that a volume has already appeared.
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
                        (release_date IS NOT NULL AND release_date < ?)
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
        """Return the next dated or current/future month-precision release.

        A volume with an exact date stays the next one through its release day.
        A month-precision volume stays the next one for its whole month, whatever
        the dataset says about it, and stops being the next one when the following
        month starts.
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
                        (release_date IS NOT NULL AND release_date >= ?)
                        OR (
                            release_date IS NULL
                            AND release_date_precision = 'month'
                            AND release_date_raw >= ?
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
                        (release_date IS NOT NULL AND release_date < ?)
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
