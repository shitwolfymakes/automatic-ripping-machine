"""Shared in-memory fake `AsyncSession` for router tests.

Routes mostly do `select(Model).where(col(Model.id) == X)` then `scalar_one_or_none()`,
sometimes `select(Model.id, Model.field)` with `.all()`. This fake keys rows by
`(table_name, id)` and matches `where(col(Field) == value)` clauses recorded on
the SQLAlchemy `Select` AST.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from sqlalchemy.sql import Select
from sqlalchemy.sql.elements import BinaryExpression


def _all_filters(stmt: Select) -> list[BinaryExpression]:
    out: list[BinaryExpression] = []
    crit = stmt.whereclause
    if crit is None:
        return out
    if hasattr(crit, "clauses"):
        out.extend(crit.clauses)
    else:
        out.append(crit)
    return out


def _extract_values(right: Any) -> list[Any] | None:
    """Pull the literal value(s) from the right side of a comparison clause.

    Handles ordinary `BindParameter` (``==``) and `BindParameterClauseList`
    used by ``in_(...)``.
    """
    if hasattr(right, "value") and not hasattr(right, "clauses"):
        return [right.value]
    clauses = getattr(right, "clauses", None)
    if clauses is not None:
        return [c.value for c in clauses if hasattr(c, "value")]
    element = getattr(right, "element", None)
    if element is not None and hasattr(element, "clauses"):
        return [c.value for c in element.clauses if hasattr(c, "value")]
    return None


def _matches(row: Any, filters: list[BinaryExpression]) -> bool:
    for clause in filters:
        col_name = getattr(getattr(clause, "left", None), "name", None)
        if col_name is None:
            return False
        right = getattr(clause, "right", None)
        op_name = getattr(clause, "operator", None)
        op_repr = getattr(op_name, "__name__", "") if op_name else ""
        actual = getattr(row, col_name, None)
        if op_repr == "in_op":
            # `in_(...)` collapses the list into a single BindParameter whose
            # `.value` is the list itself.
            collection = getattr(right, "value", None)
            if not isinstance(collection, (list, tuple, set)):
                return False
            if actual not in collection:
                return False
        elif op_repr == "lt":
            values = _extract_values(right)
            if values is None or actual is None:
                return False
            try:
                if not (actual < values[0]):
                    return False
            except TypeError:
                return False
        elif op_repr == "gt":
            values = _extract_values(right)
            if values is None or actual is None:
                return False
            try:
                if not (actual > values[0]):
                    return False
            except TypeError:
                return False
        else:
            values = _extract_values(right)
            if values is None or actual != values[0]:
                return False
    return True


def _table_for_stmt(stmt: Select) -> str | None:
    froms = stmt.get_final_froms()
    if froms:
        first = froms[0]
        name = getattr(first, "name", None)
        if isinstance(name, str):
            return name
    for c in stmt.selected_columns:
        tbl = getattr(c, "table", None)
        if tbl is not None:
            return tbl.name
    return None


class _Result:
    def __init__(self, rows: list[Any], scalar_columns: list[str] | None = None) -> None:
        self.rows = rows
        self.scalar_columns = scalar_columns

    def scalar_one_or_none(self) -> Any | None:
        if not self.rows:
            return None
        return self.rows[0]

    def scalar_one(self) -> Any:
        return self.rows[0]

    def scalars(self) -> "_Scalars":
        return _Scalars(self.rows)

    def first(self) -> Any | None:
        return self.rows[0] if self.rows else None

    def all(self) -> list[Any]:
        if self.scalar_columns:
            named = []
            for r in self.rows:
                t = MagicMock()
                for c in self.scalar_columns:
                    setattr(t, c, getattr(r, c, None))
                named.append(t)
            return named
        return self.rows


class _Scalars:
    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows

    def all(self) -> list[Any]:
        return self.rows


class FakeSession:
    """In-memory async session keyed by (table_name, id).

    Test fixtures push rows into `self.rows[table_name] = [obj, ...]` ahead of
    time; the fake matches `select`/`where`/`order_by` against those rows
    using attribute equality.
    """

    def __init__(self) -> None:
        self.rows: dict[str, list[Any]] = {}
        self.committed = 0
        self.deleted: list[Any] = []
        self.added: list[Any] = []
        self.flushed = 0
        self.commit_raises: Exception | None = None

    def add(self, obj: Any) -> None:
        self.added.append(obj)
        # Auto-extend the relevant table so subsequent reads see the new row.
        tbl = obj.__class__.__tablename__
        self.rows.setdefault(tbl, []).append(obj)

    def add_all(self, objs: list[Any]) -> None:
        for o in objs:
            self.add(o)

    async def delete(self, obj: Any) -> None:
        self.deleted.append(obj)
        tbl = obj.__class__.__tablename__
        self.rows.setdefault(tbl, [])
        self.rows[tbl] = [r for r in self.rows[tbl] if r is not obj]

    async def commit(self) -> None:
        if self.commit_raises is not None:
            raise self.commit_raises
        self.committed += 1

    async def rollback(self) -> None:
        return None

    async def flush(self) -> None:
        self.flushed += 1

    async def refresh(self, _obj: Any) -> None:
        return None

    async def execute(self, stmt: Any) -> _Result:
        if not isinstance(stmt, Select):
            return _Result([])

        table = _table_for_stmt(stmt)
        rows = list(self.rows.get(table, [])) if table else []
        filters = _all_filters(stmt)
        rows = [r for r in rows if _matches(r, filters)]

        # Heuristic: `select(Model)` exposes >=5 columns (every model field);
        # `select(Model.id, Model.name)` has 1-3. Treat the small case as a
        # column projection so `.all()` returns row-tuples with named attrs.
        col_names = [c.name for c in stmt.selected_columns]
        scalar_cols = col_names if 0 < len(col_names) < 5 else None
        return _Result(rows, scalar_columns=scalar_cols)
