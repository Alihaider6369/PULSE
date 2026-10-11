PULSE: AI Desk Posture Monitoring System

PULSE uses your laptop webcam to notice how you sit at your desk, and gently reminds you when you have been in a poor posture for too long.

PULSE is a posture-awareness and wellness tool. It is not a medical device and does not diagnose any disease, spinal problem, or injury.

Features
Live webcam posture detection (no special hardware)
Four posture classes: good, poor (slouch/forward head), lean left, lean right
Warnings after a configurable time in poor posture, with a cooldown and sound
Sessions saved to PostgreSQL with a PULSE Posture Awareness Score
FastAPI backend and a simple web dashboard (summary, history, live status, settings)
Setup (Windows)
Create and activate a virtual environment:
cmd
   python -m venv .venv
   .venv\Scripts\activate.bat
Install the packages:
cmd
   pip install -r ml\requirements.txt
   pip install -r backend\requirements.txt
   pip install requests
Create backend\.env with your database URL:
text
   DATABASE_URL=postgresql+psycopg://pulse_user:YOUR_PASSWORD@localhost:5432/pulse_db
Run migrations:
cmd
   cd backend
   alembic upgrade head
   cd ..
Download the pose model:
cmd
   python ml\scripts\download_model.py
Usage
Start the backend: cd backend then uvicorn app.main:app --reload
In another terminal, start the monitor: python monitor\monitor.py
Open the dashboard: http://127.0.0.1:8000/
Press Q in the camera window to stop.
Limitations
Trained on data from one person, so accuracy on others may be lower.
Lighting, camera angle, and partial body visibility affect detection.
Slouching and forward head are merged, because a front webcam cannot separate them reliably.
This is a posture-awareness tool, not a medical device.
Team
Ali Haider (BS Data Science)