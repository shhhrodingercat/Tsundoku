import sqlite3
from datetime import date
from pathlib import Path

from .models import ReleaseLine, Volume


class MangaDatabase:
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
    ) -> list[ReleaseLine]:
        pattern = f"%{query}%"

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

        params: list[object] = [
            pattern,
            pattern,
            pattern,
        ]

        if country is not None:
            sql += " AND s.country = ?"
            params.append(country)

        if language is not None:
            sql += " AND s.language = ?"
            params.append(language)

        sql += """
            ORDER BY
                s.name COLLATE NOCASE,
                s.country,
                s.publisher
        """

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        return [
            self._release_line_from_row(row)
            for row in rows
        ]

    def get_release_line(
        self,
        tome_id: str,
    ) -> ReleaseLine | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
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
                WHERE s.tome_id = ?
                """,
                (tome_id,),
            ).fetchone()

            if row is not None:
                return self._release_line_from_row(row)

            redirect = conn.execute(
                """
                SELECT new_tome_id
                FROM id_redirect
                WHERE old_tome_id = ?
                """,
                (tome_id,),
            ).fetchone()

            if redirect is None:
                return None

            row = conn.execute(
                """
                SELECT
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
                WHERE s.tome_id = ?
                """,
                (redirect[0],),
            ).fetchone()

        if row is None:
            return None

        return self._release_line_from_row(row)

    def get_volumes(
        self,
        series_id: int,
    ) -> list[Volume]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    id,
                    gcd_series_id,
                    volume_number,
                    title,
                    release_date,
                    release_date_precision,
                    release_date_type,
                    isbn13,
                    tome_id
                FROM volumes
                WHERE gcd_series_id = ?
                ORDER BY volume_number
                """,
                (series_id,),
            ).fetchall()

        return [
            self._volume_from_row(row)
            for row in rows
        ]

    def get_latest_volume(
        self,
        series_id: int,
        today: date,
    ) -> Volume | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    id,
                    gcd_series_id,
                    volume_number,
                    title,
                    release_date,
                    release_date_precision,
                    release_date_type,
                    isbn13,
                    tome_id
                FROM volumes
                WHERE gcd_series_id = ?
                  AND release_date IS NOT NULL
                  AND release_date <= ?
                ORDER BY
                    release_date DESC,
                    volume_number DESC
                LIMIT 1
                """,
                (series_id, today.isoformat()),
            ).fetchone()

        return self._volume_from_row(row) if row else None

    def get_next_volume(
        self,
        series_id: int,
        today: date,
    ) -> Volume | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    id,
                    gcd_series_id,
                    volume_number,
                    title,
                    release_date,
                    release_date_precision,
                    release_date_type,
                    isbn13,
                    tome_id
                FROM volumes
                WHERE gcd_series_id = ?
                  AND release_date IS NOT NULL
                  AND release_date > ?
                ORDER BY
                    release_date ASC,
                    volume_number ASC
                LIMIT 1
                """,
                (series_id, today.isoformat()),
            ).fetchone()

        return self._volume_from_row(row) if row else None

    def get_published_volume_count(
        self,
        series_id: int,
        today: date,
    ) -> int:
        """Return the number of published volumes."""
        sql = """
            SELECT COUNT(*)
            FROM volumes
            WHERE gcd_series_id = ?
              AND release_date IS NOT NULL
              AND release_date <= ?
        """

        with self._connect() as conn:
            row = conn.execute(
                sql,
                (series_id, today.isoformat()),
            ).fetchone()

        return row[0]

    @staticmethod
    def _release_line_from_row(
        row: tuple,
    ) -> ReleaseLine:
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
    def _volume_from_row(
        row: tuple,
    ) -> Volume:
        release_date = (
            date.fromisoformat(row[4])
            if row[4]
            else None
        )

        return Volume(
            id=row[0],
            series_id=row[1],
            number=row[2],
            title=row[3],
            release_date=release_date,
            release_date_precision=row[5],
            release_date_type=row[6],
            isbn13=row[7],
            tome_id=row[8],
        )
