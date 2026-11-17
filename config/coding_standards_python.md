# Python Coding Standards

Use these standards for durable Python cells in this project.

## General style

- Use mature check, modelling, and Plotly cells in the project as the local style template.
- Prefer readable, explicit code over clever one-liners.
- Keep imports minimal and centralised in the library/setup cell where possible.
- Add explanatory comments suitable for handover to a junior colleague.
- Keep comments business-readable and specific; avoid narrating obvious syntax.
- Group related statements into logical code blocks and place a concise explanatory comment immediately above each block.
- Explain the block's purpose, the transformation it performs, and any business or downstream behaviour that is not obvious from the code alone.
- Comment the block as a whole rather than narrating each individual statement.
- Keep implementation detail beside the block that implements it; do not place transformation-specific explanations in an earlier **Input** or **Overview** section.
- Add a block-level comment in **Output** describing the durable artefact's grain, ordering, and intended downstream or display use.
- Add a block-level comment in **Cleanup** stating which construction-only objects are removed and which durable outputs are intentionally retained.

```python
# Convert the ordered configuration keys into the source list iterated downstream, then initialise
# the durable registry populated by the enrichment loop below.
MONITORED_SOURCE_NAMES = list(_MONITORED_SOURCES_CONFIG)
MONITORED_SOURCES      = {}

# Copy each source's configured metadata into the durable registry and add its short source label.
# Derive FQN from the database, schema and object so the full name cannot drift from its parts.
for _source_name in MONITORED_SOURCE_NAMES:
    ...
```

This supplements the existing requirement for business-readable comments by defining where comments should sit and the level of logic they should explain.

### Function summaries

- Place a concise 1–2-line comment immediately above each def line, stating the function’s purpose and, where useful, its return value or side effect.
- Keep the comment high-level; document parameters, assumptions, and edge cases in the function docstring.

## Cell structure

Structure larger durable cells with these sections:

```python
# -------------------------------------------- Overview --------------------------------------------
# --------------------------------------------- Input ----------------------------------------------
# ------------------------------------------- Main Code --------------------------------------------
# --------------------------------------------- Output ---------------------------------------------
# -------------------------------------------- Cleanup ---------------------------------------------
```

Under **Overview**, add one or two concise comments describing:

- the purpose of the cell
- the output grain or display intent
- any important filtering or scaffolding behaviour

### Cell structure spacing

- Insert three empty lines before each section-title divider. This keeps durable cells visually consistent and makes each section easy to identify when scanning longer code.
- Keep one empty line between a section-title divider and its first comment or statement.

```python
# Cell logic above



# --------------------------------------------- Output ---------------------------------------------

DURABLE_OUTPUT = transformed_data
```

### Compact nested objects

- For nested dictionaries, open the inner object on the same line as its key.
- Align subsequent leading-comma fields beneath the first field in that inner object.
- Keep the closing delimiters on the final field line where the result remains readable.

```python
SOURCE_CONFIG = {
    'V_GROSS_MARGIN' : {'DATABASE'             : 'INSIGHT_COMMERCIAL'
                       ,'SCHEMA'               : 'LIVE_TRADING_POV'
                       ,'OBJECT'               : 'V_GROSS_MARGIN'
                       ,'DATE_COLUMN'          : 'TRANSACTION_DATE_UTC'
                       ,'ARRIVAL_DEADLINE_UTC' : '05:25:00'}}
```

## Function docstring spacing

- In function definitions, leave one empty line between the function signature and its docstring, and one empty line between the docstring and the first executable statement. This visually isolates the docstring for easy scanning while keeping it as the function's first statement.
- Apply the same spacing to single-line and multi-line docstrings.

```python
def authority_key(value):

    """Return a normalised matching key for an authority name."""

    return normalise_authority_name(value)
```

## Multiline indentation and delimiters

- Use leading commas for multiline:
  - function arguments
  - lists
  - dictionaries
  - tuples
  - chained function parameters
- Place the opening delimiter immediately before the first item, argument, key, or expression.
- Do not place an opening delimiter on a line by itself.
- Align continuation lines with the first item following the opening delimiter.
- Start every subsequent item, argument, or key with a leading comma and no whitespace after the comma.
- Place the closing delimiter immediately after the final item; do not place it on a separate line.
- Apply the same pattern consistently to lists, dictionaries, tuples, function calls, dataframe indexing, method chains, and nested structures.
- For nested structures, apply the indentation rule independently at each nesting level.
- Vertically align dictionary `:` separators where practical.
- Vertically align keyword-argument `=` signs within related multiline function calls.
- Where a line would become excessively long, prioritise readability while retaining leading commas and consistent continuation alignment.
- Keep every closing delimiter (`)`, `]`, or `}`) on the same line as the final item or expression it closes. Never place a closing delimiter by itself on a new line.
- For nested structures, append all closing delimiters to the final expression, in order from innermost to outermost.
- Break lines between items or arguments—not between the final item or expression and its closing delimiter.
- If the final line is too long, reflow or simplify the preceding expression; do not move a closing delimiter to a new line just to shorten it.


```python
values = ["first_value"
         ,"second_value"
         ,"third_value"]

result = function_name(first_argument
                      ,second_argument = second_value
                      ,third_argument  = third_value)

mapping = {"first_key"   : first_value
          ,"second_key"  : second_value
          ,"third_key"   : third_value}

filtered = (source_dataframe
            .loc[lambda df: df["STATUS"].eq("Active")
                ,selected_columns]
            .copy())

missing_columns = sorted(
    required_columns.difference(available_columns))
```

## Spacing and alignment

- Add spaces around keyword-argument equals signs, for example:
  - `axis = 1`
  - `utc = True`
  - `as_index = False`
- Align equals signs in assignment blocks where variables are conceptually related.

```python
start_date  = pd.Timestamp("2026-05-18")
end_date    = pd.Timestamp.today()
date_column = "OBSERVATION_DATE"
```

- Use compact parenthesised pandas chains, with each method on its own aligned line where this improves readability.

### Compact parenthesised chains

- Start a parenthesised expression on the assignment line rather than placing the opening delimiter on a line by itself.
- Align each continuation locally with the expression it continues, including comprehensions and dataframe indexers.

```python
MONITORED_SOURCES_REGISTRY = (pd.DataFrame([MONITORED_SOURCES[name]
                                            for name in MONITORED_SOURCE_NAMES])
                              .loc[:,['SOURCE'
                                     ,'FQN'
                                     ,'DATE_COLUMN'
                                     ,'ARRIVAL_DEADLINE_UTC'
                                     ,'DESCRIPTION']])
```

## Naming

- Use private temporary variable names with leading underscores for intermediate objects, for example:
  - `_daily`
  - `_scaffold`
  - `_ratings`
- Use uppercase constants for reusable style and configuration values, for example:
  - `HEX_BG`
  - `HEX_PANEL`
  - `HEX_TEXT`
- Keep durable output variables uppercase and domain-specific, for example:
  - `CHECK__THREADS_CONVERSATION_LINKS`
- For modelling functions, keep helper functions verb-first and domain-specific, with clear inputs and returned artefacts.

## Check cells

- Produce a durable dataframe output.
- Use clear uppercase output columns such as `CHECK`, `TOTAL_SUBMISSIONS`, and `CHECK_PASSED`.
- Use `display(...)` for the validation table.
- Avoid printing as the main output unless the cell is explicitly a validation/check cell and text output is intentional.

## Plotly cells

- Use Plotly Express unless Graph Objects are clearly needed.
- Define Hex dark-theme constants in **Input**.
- Use `fig.update_traces(...)` for hover, marker, and line details.
- Use `fig.update_layout(...)` for styling.
- Use clear labels and hover templates.
- Preserve explicit category ordering where order matters.
- Use `fig.show()` in the **Output** section.
- Delete `fig` in **Cleanup** unless the figure object is intentionally needed downstream.

## Date and category charts

- Build explicit scaffolds where zero-value periods or categories should still appear.
- Preserve category ordering with `category_orders` and the axis `categoryarray`.

## Outputs and cleanup

- Keep durable outputs that are useful downstream.
- Delete temporary objects explicitly in **Cleanup** sections using `del`.
- Do not use `globals().pop()` cleanup loops.