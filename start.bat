@echo off
call venv\Scripts\activate
start "" http://localhost:5000
python app.py
