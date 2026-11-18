# Internal demo script (step 17)

Goal: show "one scenario runs end to end" in about 5 minutes.

1. `uvicorn ups.api.main:app` and open http://127.0.0.1:8000.
2. Point out the disclaimer banner, then start **Website redesign**.
3. Click **Next event**. Show the event feed and the decision prompt with its different options.
4. Choose an option. Show the notice (what changed) and the measures moving.
5. Keep going to day 28 (use Next event). Show the final health screen.
6. Click **Explain outcomes** to show the log, then **Replay**, then **Reset and play again**.
7. Optional: open http://127.0.0.1:8000/api/docs and show the same run through the API.

Rehearse once before presenting. Have a second browser tab on a different scenario ready in case someone asks to see extensibility.
