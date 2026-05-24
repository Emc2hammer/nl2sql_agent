# Public Release Package

- `csv/`: all tables exported as CSV
- `question_bank.json`: official preliminary question set
- `schema_overview.md`: schema hints and hidden-rule boundaries
- `schema_annotated.sql`: DDL with table and field comments for semantic reading
- `table_dictionary.csv`: table and column inventory
- `relationship_map.csv`: major join paths
- `../table_relationships.md`: grouped table relationship summary
- `../relationship_er.mmd`: Mermaid ER diagram source
- `../table_keys.csv`: PK/FK inventory
- `../join_paths.md`: typical join paths for question design

Submission format: one JSON per question under `submit/`, named `<question_id>.json`.
- `generated_sql`: generated SQL string.
- `result`: SQL result as an array of row objects.
- `explanation`: text explanation of the generation logic.
- `insights`: at least two text insights with numbers, grounded in the query result and cross-checked against the full dataset.

Insights must be analytical findings such as ranking, share, gap, average comparison, trend, or empty-result analysis.
They must not be SQL walkthroughs, rule restatements, or generic business claims.
