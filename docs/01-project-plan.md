# PULSE: Project Plan

**PULSE** is an AI-powered desk posture monitoring system that uses a laptop webcam.

> PULSE is a posture-awareness / wellness tool. It is NOT a medical device
> and does not diagnose any disease, spinal problem, or injury.

## 1. Architecture

```
Webcam -> OpenCV -> MediaPipe PoseLandmarker -> landmarks
   -> pulse_features.py (shared feature module)
   -> saved ML model (joblib) -> posture class + probability
   -> temporal logic (smoothing, warning timer, cooldown)
   -> feedback (on-screen + sound) + events to FastAPI
   -> FastAPI -> PostgreSQL -> web dashboard
```

Key rule: the webcam and the ML model run in a local Python app
(`monitor/`). The browser dashboard only shows data and settings.
Frames are processed locally and are never saved or uploaded.

## 2. Decisions

| Topic | Decision |
|---|---|
| Python | 3.13 (MediaPipe 1.1.0 tested OK) |
| Pose API | MediaPipe Tasks API (PoseLandmarker); old `mp.solutions` is not available |
| ML input | Landmark-based features, not raw images |
| Models to compare | Dummy baseline, Logistic Regression, Decision Tree, Random Forest, SVM, Gradient Boosting |
| Evaluation | Split by recording session (avoid data leakage) |
| Metrics | Accuracy, precision, recall, macro-F1, confusion matrix |
| Database | PostgreSQL 17 + SQLAlchemy + Alembic |
| Backend | FastAPI (routers, schemas, services, models) |
| Frontend | Plain HTML + CSS + JavaScript + Chart.js |
| Users | Single default user for MVP |

## 3. Posture classes (starting plan)

1. Good Posture
2. Slouching
3. Forward Head
4. Leaning (Left / Right, tested separately)
5. No Person: rule-based using landmark visibility, not an ML class

If the data shows two classes cannot be separated from a front-facing
webcam, we merge them and document why.

## 4. PULSE Posture Awareness Score

score = good_seconds / (good_seconds + poor_seconds) * 100

"No person" time is excluded. This is a project-specific indicator,
not a medical measurement.

## 5. Database tables

- users
- sessions
- posture_events
- settings

Daily/weekly stats are computed from sessions and posture_events with SQL.

## 6. Privacy rules

- No webcam video is stored or uploaded.
- Only derived posture data (class, confidence, timestamps) is saved.
- The user can stop monitoring at any time.
- No passwords in code; use a .env file (never committed).

## 7. Phases

1. Planning
2. Environment + folder structure
3. Webcam + MediaPipe proof of concept
4. Feature extraction
5. Dataset collection
6. EDA + preprocessing
7. Model training + evaluation
8. Real-time prediction
9. Temporal logic + feedback
10. PostgreSQL
11. FastAPI backend
12. Dashboard
13. Integration
14. Testing + bug fixing
15. README + GitHub
16. Demo preparation

## 8. Known risks

- Camera angle and lighting affect landmark quality.
- Front-facing webcam may not separate slouching from forward head.
- Model may overfit to one user; needs varied sessions.
- Only one app can use the webcam at a time.
- Live video inside the dashboard is the trickiest integration part.

## 9. MVP scope

In: webcam pose, shared features, data collector, EDA, model comparison,
live prediction, warnings with cooldown, sessions in PostgreSQL,
FastAPI, 5-page dashboard, tests, README.

Out (future): calibration, deep learning, mobile app, hardware feedback,
multi-user login.