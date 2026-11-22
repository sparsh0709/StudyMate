# Evaluation Summary

_Generated from `tests/evaluation_results.csv` (32 rows). Only executed rows are counted._

## Result matrix

| test_id   | title                                               | n/a (validator)   | v1      | v2      | v3      |
|:----------|:----------------------------------------------------|:------------------|:--------|:--------|:--------|
| TC01      | Normal lecture notes — binary search                |                   | NOT RUN | NOT RUN | NOT RUN |
| TC02      | Sorting algorithm notes                             |                   | NOT RUN | NOT RUN | NOT RUN |
| TC03      | Operating system notes — CPU scheduling             |                   | NOT RUN | NOT RUN | NOT RUN |
| TC04      | Long lecture notes — computer networks (4 lectures) |                   | NOT RUN | NOT RUN | NOT RUN |
| TC05      | Very short lecture notes — stack (one line)         |                   | NOT RUN | NOT RUN | NOT RUN |
| TC06      | Bullet points only — DBMS normalization             |                   | NOT RUN | NOT RUN | NOT RUN |
| TC07      | Notes with repeated information — hashing           |                   | NOT RUN | NOT RUN | NOT RUN |
| TC08      | Notes with missing definitions — deadlocks          |                   | NOT RUN | NOT RUN | NOT RUN |
| TC09      | Empty input                                         | PASS              |         |         |         |
| TC10      | Random / irrelevant text                            |                   | NOT RUN | NOT RUN | NOT RUN |
| TC11      | Over-length input (> 40,000 characters)             | PASS              |         |         |         |
| TC12      | Prompt injection inside notes — queues              |                   | NOT RUN | NOT RUN | NOT RUN |

## Result counts by prompt version

| prompt_version   |   NOT RUN |   PASS |
|:-----------------|----------:|-------:|
| n/a (validator)  |         0 |      2 |
| v1               |        10 |      0 |
| v2               |        10 |      0 |
| v3               |        10 |      0 |

## Metrics

No API-based results yet. Run `python run_evaluation.py` with an OPENAI_API_KEY set, then run this script again.
