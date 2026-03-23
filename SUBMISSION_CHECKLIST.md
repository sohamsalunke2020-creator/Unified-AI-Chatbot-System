# Internship Submission Checklist (10-Day Zero-Surprise Plan)

Use this checklist exactly in order. Mark each item as done only when the expected output appears.

## 0) One-time setup (Day 1)

1. Open PowerShell in `D:\ChatBot`
2. Activate environment:

```powershell
& .\.venv-5\Scripts\Activate.ps1
```

3. Confirm interpreter:

```powershell
python -c "import sys; print(sys.executable)"
```

Expected: path includes `.venv-5\Scripts\python.exe`.

## 1) Dependency sanity check (Day 1, then before final submission)

Run:

```powershell
python -c "import streamlit, faiss, sentence_transformers, transformers, torch, pandas, requests, arxiv, PIL; print('deps ok')"
```

Expected: `deps ok` and no traceback.

## 2) Full task verification (Tasks 1-6)

Run:

```powershell
python verify_tasks.py
```

Expected final line:

```text
Overall: PASS
```

Also verify there are 6 PASS lines:
- Task 1 (KB)
- Task 2 (Multi-Modal)
- Task 3 (Medical Q&A)
- Task 4 (Domain Expert)
- Task 5 (Sentiment)
- Task 6 (Multi-language)

Task 2 submission note:
- Treat Gemini as the implemented Google multimodal model for current Google AI requirements.
- Do not claim a separate PaLM integration; PaLM is deprecated.

Task 3 submission note:
- Task 3 now uses MedQuAD-first retrieval with built-in medical safety fallback.
- In the UI, medical answers show `SOURCE MEDQUAD` or `SOURCE BUILT-IN`.
- For MedQuAD-backed answers, the matched MedQuAD question is shown in the metadata panel.


## 3) Streamlit app launch smoke test

Run:

```powershell
python -m streamlit run ui\streamlit_app.py --server.port 8502
```

Expected:
- `You can now view your Streamlit app in your browser.`
- URL shown as `http://127.0.0.1:8502`

Then open browser and test one query per task.

## 4) Manual output proof (collect screenshots)

Take one screenshot each for:
1. Task 1 answer (knowledge-base style answer)
2. Task 2 image analysis response
3. Task 2 image generation response
4. Task 3 MedQuAD-backed response showing `SOURCE MEDQUAD`
5. Task 4 research/domain explanation
6. Task 5 sentiment output containing sentiment/confidence
7. Task 6 language detection + translation output
8. Final `Overall: PASS` terminal output

Store in: `D:\ChatBot\assets\submission_proof\`

## 5) Stability checks (run on Day 8, 9, and 10)

Run these three commands each day:

```powershell
python verify_tasks.py
python -m streamlit run ui\streamlit_app.py --server.port 8502
python -c "from chatbot_main import UnifiedChatbot; b=UnifiedChatbot(lazy_init=True); print('bot init ok')"
```

If all three run without traceback, your build is stable for submission.

## 6) GitHub upload checklist (Day 10)

1. Check changes:

```powershell
git status
```

2. Add files:

```powershell
git add .
```

3. Commit:

```powershell
git commit -m "Final internship submission: tasks 1-6 verified"
```

4. Push:

```powershell
git push origin <your-branch>
```

5. Confirm on GitHub:
- README visible
- `verify_tasks.py` present
- `SUBMISSION_CHECKLIST.md` present
- screenshots/evidence uploaded

## 7) Emergency fallback if anything fails

If a check fails close to deadline:
1. Re-run `python verify_tasks.py`
2. Copy the exact traceback/error line
3. Fix only the failing module (avoid broad refactors)
4. Re-run full verification until `Overall: PASS`
5. Commit immediately after green run

This process minimizes risk and prevents deadline blockers.
