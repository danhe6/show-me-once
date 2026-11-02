# Show Me Once

**A camera coach that helps special-education students learn everyday life skills, step by step, and turns every practice into IEP-ready data for their teacher.**

> Built for the Meta Global AI Developer Hackathon (Oct 26 – Nov 4, 2026) · Indie track · Solo entry
> Everything in this repo was written during the event. The full build log is in [`docs/DEVLOG.md`](docs/DEVLOG.md).

---

## The problem

Students with intellectual and developmental disabilities learn life skills (making tea, folding laundry, packing a bag) through **task analysis**: a skill is broken into small steps, and the teacher records, for every step of every practice, how much help the student needed. That record feeds the student's IEP (Individualized Education Program), which U.S. law requires to include measurable goals and regular progress reports ([34 CFR §300.320](https://www.ecfr.gov/current/title-34/section-300.320)).

In practice, this means **one adult standing next to one student with a clipboard**. When special-ed teachers on r/specialed told us what would make their lives easier, the answers were consistent:

- data collection and progress monitoring take too much time and are still done on paper
- teachers act as the "integration layer" between systems that don't talk to each other
- they want tools that are fast, modern, free, accessible (visuals, captions, read-aloud) and age-appropriate
- they are tired of "AI slop": tools that make things up

Step-by-step video prompting is proven to work for these skills ([systematic review, 24 studies](https://link.springer.com/article/10.1007/s41252-022-00273-7)), but only about a quarter of special-ed teachers use it, mostly because making the materials takes too long ([survey](https://pure.psu.edu/en/publications/teacher-and-video-modeling-a-survey-of-use-and-perspectives/)).

## What Show Me Once does

**For the student:** the phone stands on the table, facing them. It asks *"Hi Maya! What do you want to do today?"* The student says "um, I want tea" (or taps a card). The coach checks the table (*"I see the mug and the tea bag. Can you bring the kettle?"*), then watches through the camera and talks them through the task, one small step at a time. Both hands stay free.

**For the teacher:** one sentence ("make a cup of tea") becomes a reviewed task analysis. Every practice, whether the teacher was in the room or not, lands in a standard data sheet with prompt codes, camera-verified steps, and a progress note they can paste into their IEP system.

### Key features

| | |
|---|---|
| **Live coaching, not a quiz** | The coach sends the last 3 camera frames (≈0.6 s apart) so it understands *motion*: it says what it sees ("You are filling the kettle at the sink") and gives the next small action. It talks sparingly and never says "wrong". |
| **Any sensible order** | Real tasks don't have one fixed order. The coach knows each step's real dependencies (you can open the tea bag before or after filling the kettle, but you can't pour before the water boils). It recognises which step the student is doing and only stops them when something must come first. Teachers can switch a task to "same order every time" for students who need routine. |
| **No skipping, no self-reporting** | A step is complete only when the camera sees the finished state twice in a row, or a teacher confirms it. There is no "I did it" button. Skipped steps, wrong items and unsafe actions are flagged on the data sheet. |
| **Teacher sees it live** | A "Practicing now" panel shows who is practicing, which step, what the camera sees, and alerts (asked for help, stuck, tried to skip, unsafe). The teacher can confirm a step remotely. |
| **One safety rule set** | Heat, blades, electricity near water and cleaning chemicals are defined once ([`src/safety.py`](src/safety.py)). The same rules shape how steps are written, what the camera stops ("Stop. Put it down. Wait for your teacher."), and which steps need the teacher nearby. Tasks involving medication or power tools are refused. |
| **IEP-ready data** | AFIRM-style task-analysis data sheet (I / IS / VB / G / M / P codes), % independent per session, mastery (3 consecutive independent sessions), one-line session notes for systems like SpedTrack, CSV export, printable sheet. Teachers can tap-record a lesson by hand, and their edits always win. |
| **Teacher's own voice** | Teachers can record each step in their own voice; otherwise the device's most natural voice is used. |
| **Photos optional** | Default tasks need no pictures at all: the coach talks and watches. Teachers can add a real photo per step, which is also used as the camera's reference. AI-drawn cards exist as an opt-in draft. |

## Multi-agent design

Every agent does a real job, numbers are always computed by code, and nothing changes without the teacher.

```
 Student practices
        │
 ┌──────▼──────┐   live, 1–3 s per check
 │   Coach     │   Muse Spark: watches frames, recognises the step,
 │   agent     │   gives hints, answers questions, checks the table
 └──────┬──────┘
        │ every judgment is logged
 ┌──────▼──────┐   plain code, no AI
 │   Monitor   │   per step: checks, % "can't see", latency, skips, unsafe
 └──────┬──────┘
        │ problem steps
 ┌──────▼──────┐   Muse Wonder
 │   Tuner     │   proposes ONE fix: rewrite what "done" looks like,
 │   agent     │   split the step, move the phone, add a photo
 └──────┬──────┘
        │ teacher taps Apply / Dismiss
 ┌──────▼──────┐   Muse Wonder
 │  Analyst    │   progress report + next-week plan + one IEP line,
 │   agent     │   using only facts computed by code
 └─────────────┘
```

Example from a test run: the Monitor flagged *"Put tea bag in mug"* (camera couldn't see the step 60% of the time). The Tuner worked out that a tea bag inside a mug is invisible to the camera and proposed *"Drop tea bag into mug, tag out."* with the camera checking for the tag over the rim. After the teacher applied it, the data sheet stayed aligned.

The chain runs automatically after every practice session. Each action appears on the task's **Agents** tab as a timeline.

## Meta models used

| Model | What it does here |
|---|---|
| **Muse Spark 1.3** | Live coaching: understands what the student is doing from 3 frames, decides done / working / too early / wrong / unsafe; checks the table before starting; answers the student's spoken questions about the current step; matches "what do you want to do today?" to an approved task; reads controls and labels from a teacher's photo. |
| **Muse Wonder 1.0** | Writes the task analysis with special-ed rules (one action per step, ≤ 8 words, a visible end state, safety technique) and self-checks it; infers which steps really depend on which; Tuner and Analyst agents. |
| **Muse Voice Transcribe 1.0** | Students say what they want to do and ask questions out loud; push-to-talk, no typing. |
| **Muse Image 1.0** | Optional AI-drafted step cards, checked by Spark against the safety rules before a teacher can approve them. |

## Honest limits

- **Not yet tested with real students.** Testing so far was done by the developer at a kitchen counter. Feedback from special-ed teachers on Reddit shaped the design, but no classroom pilot has happened.
- **No formal accuracy benchmark yet.** Smoke tests with real model calls are in the repo (`smoke_*.py`); each live check takes about 1.2–2.8 s. Recognition depends on the phone seeing the hands and items clearly. That is why every step can also be confirmed by a teacher, and why the Monitor and Tuner exist.
- **Not a medical, therapy or behavior tool.** No diagnosis, no scoring of the person, no video stored. Only one small still per completed step is saved as evidence for the teacher.
- Single-classroom prototype: no accounts or multi-device sync. Data is stored as JSON files on the machine running the server.

## Run it

Requires Python 3.11+ and a Meta Model API key.

```bash
pip install -r requirements.txt
echo "MODEL_API_KEY=your_key_here" > .env
uvicorn app:app --port 8000
```

- Student view: `http://localhost:8000/#learn` · Teacher view: `http://localhost:8000/#care`
- Phones need HTTPS for the camera and microphone. `python serve.py start` starts the app plus a temporary Cloudflare tunnel with a random access token, and prints the phone link. `python serve.py stop` shuts both down.
- A sample task (make a cup of tea) and three sample students are included in `data/coach/`.

## Repo map

```
app.py              FastAPI backend: tasks, practice sessions, live panel, data sheet, agents
src/coach.py        Coach agent: task analysis, live watching (fixed + flexible order), table check, Q&A
src/agents.py       Monitor (code), Tuner and Analyst (Wonder)
src/safety.py       The one safety rule set used everywhere
src/spark.py        Meta Model API client (OpenAI-compatible)
static/index.html   The whole front end (student + teacher), no build step
serve.py            App + HTTPS tunnel for phone testing
smoke_*.py          Smoke tests with real model calls
docs/DEVLOG.md      Build log: every change, why, and how to roll it back
```

## License

MIT
