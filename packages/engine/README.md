# nba-cba-engine

A deterministic rules engine for the 2023 NBA Collective Bargaining Agreement.
Give it payrolls and a proposed trade; it returns whether the trade is
permitted, which rule each violation breaks — cited to the Article and Section —
and what the verdict had to assume because no source says.

It is the part of [NBA CBA Analyzer](https://github.com/ankurbhatia28/nbacbaanalyzer)
that decides, packaged on its own. The app puts a language model in front of it
to read questions and quote the Agreement; the model never decides a rule, and
this package imports no model client at all.

## Install

Python 3.12 or later. No dependencies.

```bash
pip install "nba-cba-engine @ git+https://github.com/ankurbhatia28/nbacbaanalyzer#subdirectory=packages/engine"
```

It is published from GitHub only, not PyPI. The import name is `engine`.

## Example

```python
from engine import ApronStatus, classify
from engine.salary_matching import standard
from engine.season import Season

season = Season(
    season_id="2026-2027",
    salary_cap=166_000_000,
    tax_level=201_690_000,
    first_apron=210_690_000,
    second_apron=223_690_000,
    non_taxpayer_mle=15_139_000,
    taxpayer_mle=6_102_000,
    room_mle=9_425_000,
    bi_annual_exception=5_511_000,
)

# A team sends out a $30M player. How much salary may it take back?
below = standard(30_000_000, season, post_apron_salary=205_000_000)
print(below.amount, below.citation.short)  # 30250000 Art. VII §6(j)(1)(i)

# The same trade from a team that would end up over the First Apron:
# Art. VII §6(j)(3) removes the $250,000 allowance.
above = standard(30_000_000, season, post_apron_salary=215_000_000)
print(above.amount, above.note)

print(classify(215_000_000, 166_000_000, 201_690_000, 210_690_000, 223_690_000))
```

```
30250000 Art. VII §6(j)(1)(i)
30000000 allowance removed: Art. VII §6(j)(3)
first_apron
```

Every figure is an argument: thresholds change each season, so the engine holds
none of them. For whole trades, build `TeamState`s and a `Trade` and call
`engine.validate_trade`; `engine.team_trade_constraints` answers "what limits
this team?" with no deal proposed.

## What it covers

- **Salary matching** — the Standard, Aggregated, Transition, Expanded and Room
  traded player exceptions, and the allowance that disappears above the First
  Apron (Art. VII §6(j)).
- **Team salary** — cap, tax and apron totals, which differ: cap holds count
  toward room but not toward the aprons (Art. VII §2(e)(1)).
- **Aprons and hard caps** — the Transaction Restrictions Table, and the
  ceilings a transaction triggers.
- **Trade validation** — multi-team trades leg by leg, roster limits, the trade
  window, no-trade clauses, draft pick rules (the Stepien rule), poison pills.
- **Maximum salaries**, cap holds, dead money and Bird rights.

## Unknown is not zero

Trade kickers, no-trade clauses and guarantees are three-valued: present,
absent, or **unknown**. A verdict that rests on an unknown says so, through an
`AssumptionLog`, rather than treating a missing value as "none". Most public
contract data does not carry these fields, so this is the common case, not the
edge.

## Tested

197 tests, including the Agreement's own worked examples and property-based
tests at every threshold boundary. Type-checked with `mypy --strict`.

## License

MIT. The Collective Bargaining Agreement itself is not included.
