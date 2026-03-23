## Task 3 Submission Note

Task 3 now uses MedQuAD-first retrieval with a built-in medical safety fallback.

- `SOURCE MEDQUAD` indicates the answer came from the best matching MedQuAD question-answer pair.
- `SOURCE BUILT-IN` indicates the answer came from curated internal medical guidance used for safety-oriented, urgent-care, or fallback scenarios.
- For MedQuAD-backed answers, the UI shows `SOURCE MEDQUAD`, displays the matched MedQuAD question in the metadata area, and includes `Matched MedQuAD Question` in the References panel.

This keeps the medical chatbot aligned with the MedQuAD dataset requirement while preserving safe fallback behavior for high-priority medical prompts.