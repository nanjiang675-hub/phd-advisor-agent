# Data sources

## University scope

`input/schools.csv` contains institutions at rank 100 or better in the **2025 U.S. News Best National Universities** list. Ties mean the file contains 104 institutions, not exactly 100 rows.

Verification source: [HeinOnline summary PDF](https://heinonline.org/HeinDocs/USNewsTop100Universities.pdf), labelled “2025 U.S. News Best 100 Universities Ranking”. The project records this as a scope filter only. U.S. News does not sponsor or endorse this project.

Users should replace the file when using a different edition or a list obtained under different terms. Do not silently relabel the 2025 list as 2026.

## Faculty and admissions evidence

The crawler reads public university department and faculty pages supplied in `input/schools.csv` or discovered through a configured search provider. Each extracted recruiting status stores:

- the exact source URL;
- the relevant evidence excerpt;
- the retrieval time;
- whether verification came from rules, a model, or a human reviewer;
- a confidence score.

`unknown` never means “not recruiting,” and `suspected_open` is not shown as confirmed until reviewed.
