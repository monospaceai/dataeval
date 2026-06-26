"""Property and execution-soundness tests for the AST canonicalization pass.

Hypothesis generates SQLGlot expression trees over a fixed schema
`t(a int, b int, c int, x double, y double, flag boolean)`, wraps each into a
`SELECT <numeric> FROM t WHERE <bool>`, and asserts four properties:

- idempotence: re-normalizing an already-normalized tree is a fixpoint;
- recall: a meaning-preserving mutation is confirmed `equivalent`;
- soundness on preserving mutations: a confirmed meaning-preserving mutation executes
  identically on every one of many randomized DuckDB datasets;
- soundness on breaking mutations: a confirmed possibly-meaning-changing mutation still
  executes identically, so a confirmed-but-divergent pair (over-merging) fails the suite.

Dataset value pools are deliberately moderate: the execution oracle tolerates float `+`/`*`
reassociation and constant folding (the pass accepts these), so extreme magnitudes would flag
that accepted imprecision as a spurious divergence.
"""

import math
import random

import duckdb
import pytest
import sqlglot
from hypothesis import assume, given, settings
from hypothesis import strategies as st
from sqlglot import exp

from evaldata.scorers.semantic_equivalence import _normalize_tree

_DIALECT = "databricks"
_INT_COLS = ("a", "b", "c")
_DBL_COLS = ("x", "y")
_LITERALS = (0, 1, -1, 0.0, 1.0, -1.0, 0.5, -2.5, 3.25)

_INT_VALUES: tuple[int | None, ...] = (-3, -2, -1, 0, 1, 2, 3, 4, 5, None)
_DBL_VALUES: tuple[float | None, ...] = (0.0, 1.0, -1.0, 0.5, -2.5, 3.25, None)
_BOOL_VALUES: tuple[bool | None, ...] = (True, False, None)

_ROWS_PER_DATASET = 8
_DATASETS = 20


def _literal(value: int | float) -> exp.Expression:
    """Build a numeric literal node from `value`."""
    return exp.Literal.number(repr(value))


_RENDER_PARENT = (
    exp.Add,
    exp.Sub,
    exp.Mul,
    exp.Div,
    exp.And,
    exp.Or,
    exp.Not,
    exp.BitwiseAnd,
    exp.BitwiseOr,
    exp.BitwiseXor,
)


def _faithful_sql(query: exp.Select) -> str:
    """Render `query` to SQL that re-parses to the same tree, parenthesizing every operator.

    Hand-built and mutated trees carry no precedence metadata, so unparenthesized output can
    re-parse to a different meaning; wrapping every operator operand in an explicit `Paren`
    keeps the rendering unambiguous.
    """
    rendered = query.copy()
    edits = [
        (node, key, child)
        for node in rendered.walk()
        for key in ("this", "expression")
        if isinstance((child := node.args.get(key)), _RENDER_PARENT) and not isinstance(node, (exp.Paren, exp.Alias))
    ]
    for node, key, child in edits:
        node.set(key, exp.Paren(this=child))
    return rendered.sql(dialect=_DIALECT)


@st.composite
def _numeric(draw: st.DrawFn, depth: int) -> exp.Expression:
    """Draw a numeric expression over the schema's columns and literal pool."""
    if depth <= 0:
        leaf = draw(st.integers(min_value=0, max_value=2))
        if leaf == 0:
            return exp.column(draw(st.sampled_from(_INT_COLS)))
        if leaf == 1:
            return exp.column(draw(st.sampled_from(_DBL_COLS)))
        return _literal(draw(st.sampled_from(_LITERALS)))
    op = draw(st.sampled_from((exp.Add, exp.Sub, exp.Mul, exp.Div)))
    return op(this=draw(_numeric(depth - 1)), expression=draw(_numeric(depth - 1)))


@st.composite
def _bitwise(draw: st.DrawFn) -> exp.Expression:
    """Draw a single-operator bitwise chain over the integer columns.

    One operator (`&`, `|`, or `^`) drives the whole chain: mixing operators of equal
    precedence would change meaning under reordering, so a uniform chain keeps every
    permutation meaning-preserving.
    """
    op = draw(st.sampled_from((exp.BitwiseAnd, exp.BitwiseOr, exp.BitwiseXor)))
    columns = draw(st.lists(st.sampled_from(_INT_COLS), min_size=2, max_size=4))
    chain = exp.column(columns[0])
    for name in columns[1:]:
        chain = op(this=chain, expression=exp.column(name))
    return chain


@st.composite
def _comparison(draw: st.DrawFn) -> exp.Expression:
    """Draw a comparison or an `IN` membership test over numeric expressions."""
    if draw(st.booleans()):
        members = [_literal(value) for value in draw(st.lists(st.sampled_from(_LITERALS), min_size=1, max_size=4))]
        return exp.In(this=draw(_numeric(1)), expressions=members)
    op = draw(st.sampled_from((exp.EQ, exp.NEQ, exp.GT, exp.LT, exp.GTE, exp.LTE)))
    return op(this=draw(_numeric(1)), expression=draw(_numeric(1)))


@st.composite
def _boolean(draw: st.DrawFn, depth: int) -> exp.Expression:
    """Draw a boolean expression over comparisons, `AND`/`OR`/`NOT`."""
    if depth <= 0:
        return draw(_comparison())
    kind = draw(st.integers(min_value=0, max_value=3))
    if kind == 0:
        return draw(_comparison())
    if kind == 1:
        return exp.And(this=draw(_boolean(depth - 1)), expression=draw(_boolean(depth - 1)))
    if kind == 2:
        return exp.Or(this=draw(_boolean(depth - 1)), expression=draw(_boolean(depth - 1)))
    return exp.Not(this=draw(_boolean(depth - 1)))


@st.composite
def _query(draw: st.DrawFn) -> exp.Select:
    """Draw a `SELECT <numeric|bitwise> FROM t WHERE <bool>` query."""
    projection = draw(_bitwise()) if draw(st.booleans()) else draw(_numeric(2))
    return exp.select(exp.alias_(projection, "n")).from_("t").where(draw(_boolean(2)))


def _ast_equivalent(left: exp.Expression, right: exp.Expression) -> bool:
    """Whether the AST pass confirms two trees as equivalent.

    Normalization runs on the trees directly; round-tripping through SQL text would drop
    precedence parens and re-parse to a different tree.
    """
    return _normalize_tree(left, _DIALECT) == _normalize_tree(right, _DIALECT)


def _mutate(query: exp.Select, choose: st.DataObject, *, scope: str = "any") -> exp.Select | None:
    """Apply one meaning-preserving commutative mutation, or `None` if none applies.

    The target site and any permutation are drawn from `choose` so failures replay and shrink.

    Args:
        query: The query to mutate.
        choose: The Hypothesis data object the target and permutation are drawn from.
        scope: `"projection"` restricts targets to the SELECT list; `"any"` allows the whole
            query.

    Returns:
        The mutated query, or `None` if no eligible site exists.
    """
    mutated = query.copy()
    root = mutated.selects[0] if scope == "projection" else mutated
    candidates = [node for node in root.walk() if _is_mutable(node)]
    if not candidates:
        return None
    target = choose.draw(st.sampled_from(candidates))
    if isinstance(target, (exp.Add, exp.Mul)):
        left, right = target.left, target.right
        target.set("this", right.copy())
        target.set("expression", left.copy())
    elif isinstance(target, exp.In):
        members = choose.draw(st.permutations([member.copy() for member in target.expressions]))
        target.set("expressions", list(members))
    else:
        parts = choose.draw(st.permutations([part.copy() for part in target.flatten()]))
        cls = type(target)
        rebuilt = parts[0]
        for part in parts[1:]:
            rebuilt = cls(this=rebuilt, expression=part)
        target.replace(rebuilt)
    return mutated


def _is_mutable(node: exp.Expression) -> bool:
    """Whether `node` is a site a meaning-preserving commutative mutation can target."""
    if isinstance(node, (exp.Add, exp.Mul)):
        return _is_swappable_binary(node)
    if isinstance(node, exp.In):
        return len(node.expressions) > 1
    return _is_permutable_chain(node)


def _is_atom(node: exp.Expression | None) -> bool:
    """Whether `node` is a leaf: a column, a numeric literal, or a negated literal."""
    if isinstance(node, exp.Column):
        return True
    return isinstance(node, exp.Literal) or (isinstance(node, exp.Neg) and isinstance(node.this, exp.Literal))


def _is_swappable_binary(node: exp.Add | exp.Mul) -> bool:
    """Whether swapping `node`'s operands is a pure binary commute the pass confirms.

    Both operands must be leaves and the parent must not be the same operator; swapping a link
    of a longer `+`/`*` chain reassociates it, which the pass does not confirm.
    """
    return _is_atom(node.left) and _is_atom(node.right) and not isinstance(node.parent, type(node))


_CHAIN_TYPES = (exp.And, exp.Or, exp.BitwiseAnd, exp.BitwiseOr, exp.BitwiseXor)


def _is_permutable_chain(node: exp.Expression) -> bool:
    """Whether `node` is an associative-commutative chain whose permutation the pass confirms.

    The node must be the root of its operator chain (parent is a different operator) and every
    flattened part must be a non-connective leaf; permuting a chain whose parts are themselves
    the opposite connective reorders the CNF distribution, which the pass does not confirm.
    """
    if not isinstance(node, _CHAIN_TYPES) or isinstance(node.parent, type(node)):
        return False
    return not any(isinstance(part, _CHAIN_TYPES) for part in node.flatten())


_OTHER_INT_COLS = {name: tuple(c for c in _INT_COLS if c != name) for name in _INT_COLS}
_OTHER_LITERALS = {repr(value): tuple(other for other in _LITERALS if other != value) for value in _LITERALS}


_NEGATE = {exp.EQ: exp.NEQ, exp.NEQ: exp.EQ, exp.GT: exp.LTE, exp.LTE: exp.GT, exp.LT: exp.GTE, exp.GTE: exp.LT}


def _breaking_mutations(node: exp.Expression) -> list[tuple[str, object]]:
    """Meaning-changing rewrites of `node`, each a family label paired with a callable that
    builds the replacement.

    Rewrites stay near-identical to the original so the canonicalizer is exercised rather than
    returning unknown on shape alone. Labels let the caller weight families evenly, so a rare
    high-signal family is not drowned out by abundant ones.
    """
    if isinstance(node, exp.Add):
        return [("op", lambda: exp.Sub(this=node.left.copy(), expression=node.right.copy()))]
    if isinstance(node, exp.Mul):
        return [("op", lambda: exp.Div(this=node.left.copy(), expression=node.right.copy()))]
    if isinstance(node, (exp.Sub, exp.Div)):
        cls = type(node)
        return [
            ("op", lambda: exp.Add(this=node.left.copy(), expression=node.right.copy())),
            ("swap", lambda: cls(this=node.right.copy(), expression=node.left.copy())),
        ]
    if isinstance(node, exp.Column) and (others := _OTHER_INT_COLS.get(node.name)):
        return [("column", lambda other=name: exp.column(other)) for name in others]
    if isinstance(node, exp.Literal) and not node.is_string and (others := _OTHER_LITERALS.get(node.name)):
        return [("literal", lambda other=value: _literal(other)) for value in others]
    if isinstance(node, exp.In) and node.expressions:
        return [("in", lambda i=index: _drop_in_member(node, i)) for index in range(len(node.expressions))]
    if (flipped := _NEGATE.get(type(node))) is not None:
        return [("compare", lambda: flipped(this=node.this.copy(), expression=node.expression.copy()))]
    return []


def _drop_in_member(node: exp.In, index: int) -> exp.Expression:
    """Return a copy of `node` with the `IN`-list member at `index` removed, or `FALSE` if empty."""
    members = [member.copy() for i, member in enumerate(node.expressions) if i != index]
    if not members:
        return exp.false()
    return exp.In(this=node.this.copy(), expressions=members)


def _mutate_breaking(query: exp.Select, choose: st.DataObject) -> exp.Select | None:
    """Apply one possibly-meaning-changing mutation to `query`, or `None` if none applies.

    A family is drawn before a site within it, so every family gets equal weight regardless of
    its site count. Some rewrites are coincidentally meaning-preserving (e.g. `a - 0`), which is
    fine: the soundness property only asserts when the pass confirms.
    """
    mutated = query.copy()
    by_family: dict[str, list[tuple[exp.Expression, object]]] = {}
    for node in mutated.walk():
        for family, mutation in _breaking_mutations(node):
            by_family.setdefault(family, []).append((node, mutation))
    if not by_family:
        return None
    family = choose.draw(st.sampled_from(sorted(by_family)))
    target, mutation = choose.draw(st.sampled_from(by_family[family]))
    replacement = mutation()
    if target is mutated:
        return replacement if isinstance(replacement, exp.Select) else None
    target.replace(replacement)
    return mutated


# Absolute float tolerance mirroring `ComparisonConfig.float_tolerance`; float `+`/`*`
# reassociation can differ in the last ULP, so single-column results are compared within it.
_FLOAT_TOLERANCE = 1e-9


def _sort_key(value: object) -> tuple[int, float]:
    """Order a single-column cell NULL/NaN-last for a stable pairwise comparison."""
    if value is None:
        return (2, 0.0)
    if isinstance(value, float) and math.isnan(value):
        return (1, 0.0)
    return (0, float(value))


def _cells_agree(left: object, right: object) -> bool:
    """Whether two single-column cells agree: floats within tolerance, else exact (NULL/NaN-aware)."""
    if left is None or right is None:
        return left is right
    left_special = isinstance(left, float) and not math.isfinite(left)
    right_special = isinstance(right, float) and not math.isfinite(right)
    if left_special or right_special:
        return left == right or (left_special and right_special and repr(left) == repr(right))
    if isinstance(left, float) or isinstance(right, float):
        return abs(float(left) - float(right)) <= _FLOAT_TOLERANCE
    return left == right


def _results_agree(left: list[tuple[object, ...]], right: list[tuple[object, ...]]) -> bool:
    """Whether two single-column result sets agree order-independently, floats within tolerance."""
    if len(left) != len(right):
        return False
    left_sorted = sorted((row[0] for row in left), key=_sort_key)
    right_sorted = sorted((row[0] for row in right), key=_sort_key)
    return all(_cells_agree(a, b) for a, b in zip(left_sorted, right_sorted, strict=True))


def _random_row(rng: random.Random) -> tuple[object, ...]:
    """Draw one randomized dataset row for the fixed schema."""
    return (
        rng.choice(_INT_VALUES),
        rng.choice(_INT_VALUES),
        rng.choice(_INT_VALUES),
        rng.choice(_DBL_VALUES),
        rng.choice(_DBL_VALUES),
        rng.choice(_BOOL_VALUES),
    )


def _connection() -> duckdb.DuckDBPyConnection:
    """Open an in-process DuckDB with the fixed schema table `t`."""
    connection = duckdb.connect()
    connection.execute("CREATE TABLE t(a INTEGER, b INTEGER, c INTEGER, x DOUBLE, y DOUBLE, flag BOOLEAN)")
    return connection


def _seed_dataset(connection: duckdb.DuckDBPyConnection, where: str, rng: random.Random) -> None:
    """Replace `t`'s rows with a fresh dataset that exercises `where` (not constant across rows).

    Resamples until the predicate is neither all-true nor all-false over the rows, so a
    distinguishing predicate is actually reached.
    """
    connection.execute("DELETE FROM t")
    for _ in range(64):
        rows = [_random_row(rng) for _ in range(_ROWS_PER_DATASET)]
        connection.executemany("INSERT INTO t VALUES (?, ?, ?, ?, ?, ?)", rows)
        kept = connection.execute(f"SELECT count(*) FROM t WHERE {where}").fetchone()[0]
        if 0 < kept < _ROWS_PER_DATASET:
            return
        connection.execute("DELETE FROM t")
    connection.executemany(
        "INSERT INTO t VALUES (?, ?, ?, ?, ?, ?)", [_random_row(rng) for _ in range(_ROWS_PER_DATASET)]
    )


def _run(connection: duckdb.DuckDBPyConnection, query: exp.Select) -> list[tuple[object, ...]]:
    """Transpile `query` to DuckDB and return its rows."""
    duck_sql = sqlglot.transpile(_faithful_sql(query), read=_DIALECT, write="duckdb")[0]
    return connection.execute(duck_sql).fetchall()


def _where_sql(query: exp.Select) -> str:
    """Render `query`'s `WHERE` predicate as DuckDB SQL, parenthesized faithfully."""
    predicate = exp.select(exp.Literal.number("1")).from_("t").where(query.args["where"].this.copy())
    transpiled = sqlglot.transpile(_faithful_sql(predicate), read=_DIALECT, write="duckdb")[0]
    return sqlglot.parse_one(transpiled, dialect="duckdb").args["where"].this.sql(dialect="duckdb")


def _assert_execution_agrees(left: exp.Select, right: exp.Select, seed: int = 0, datasets: int = _DATASETS) -> None:
    """Run both queries over many randomized datasets; any result divergence is a hard failure.

    Args:
        left: The first query.
        right: The second query, expected to agree with `left`.
        seed: The dataset RNG seed, varied per example for dataset diversity.
        datasets: How many randomized datasets to compare over.
    """
    connection = _connection()
    try:
        rng = random.Random(seed)
        where = _where_sql(left)
        for _ in range(datasets):
            _seed_dataset(connection, where, rng)
            assert _results_agree(_run(connection, left), _run(connection, right))
    finally:
        connection.close()


@pytest.mark.unit
class TestCanonicalizationProperties:
    @settings(deadline=None, max_examples=300)
    @given(_query())
    def test_normalization_is_a_tree_fixpoint(self, query: exp.Select) -> None:
        try:
            once = _normalize_tree(query, _DIALECT)
        except ArithmeticError:
            return
        assert _normalize_tree(once, _DIALECT) == once

    @settings(deadline=None, max_examples=100)
    @given(_query(), st.data())
    def test_projection_mutation_is_confirmed(self, query: exp.Select, choose: st.DataObject) -> None:
        # Mutating only the SELECT list isolates the commutative rewrite from boolean absorption
        # in the WHERE, where predicates equal only after canonicalization get deduplicated
        # before the pass can unify them.
        mutated = _mutate(query, choose, scope="projection")
        assume(mutated is not None)
        try:
            confirmed = _ast_equivalent(query, mutated)
        except ArithmeticError:
            assume(False)
        assert confirmed

    @settings(deadline=None, max_examples=40)
    @given(_query(), st.data())
    def test_confirmed_pairs_execute_identically(self, query: exp.Select, choose: st.DataObject) -> None:
        mutated = _mutate(query, choose)
        assume(mutated is not None)
        try:
            confirmed = _ast_equivalent(query, mutated)
        except ArithmeticError:
            assume(False)
        if confirmed:
            _assert_execution_agrees(query, mutated, choose.draw(st.integers()))

    @settings(deadline=None, max_examples=300)
    @given(_query(), st.data())
    def test_confirmed_breaking_mutation_executes_identically(self, query: exp.Select, choose: st.DataObject) -> None:
        # Soundness: the pass only ever confirms, so any confirmed breaking mutation must agree
        # on execution; a confirmed pair that diverges is over-merging. Most breaking mutations
        # make the pass return unknown (no execution), so only the rare confirmed pair runs. An
        # over-merge surfaces on a single distinguishing row, so few datasets suffice.
        mutated = _mutate_breaking(query, choose)
        assume(mutated is not None)
        try:
            confirmed = _ast_equivalent(query, mutated)
        except ArithmeticError:
            assume(False)
        if confirmed:
            _assert_execution_agrees(query, mutated, choose.draw(st.integers()), datasets=4)
