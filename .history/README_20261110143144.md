# SafeBite

## Setup
1. Install Python 3.10+ and the Tesseract OCR program
   - Windows: https://github.com/UB-Mannheim/tesseract/wiki  (set TESSERACT_CMD in .env)
   - macOS: `brew install tesseract zbar`    Linux: `sudo apt install tesseract-ocr libzbar0`
2. python -m venv venv
3. Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process -Force
4. venv\Scripts\activate
5. 
6. python -m pip install -r requirements.txt
7. $env:SMTP_USER=" SENDER E-MAIL ID "
8. $env:SMTP_PASS=" APP PASSWORD "
9. python app.py
10. open:  http://localhost:5000/


SENDER E-MAIL ID: Used to send SOS mail to the emergency e-mail
APP PASSWORD    : Created for specific task 16 digits (not e-mail ID's password)


## Layout
- app.py                       Flask routes + JSON API (/api/scan, /api/history, /api/sos)
- static/js/app.js             browser app: upload, live camera, filters, history, SOS
- static/css/style.css         custom styles (Tailwind comes from the CDN)
- Dockerfile                   one-step deployment (Render, Railway, Fly.io ...)
- database.py                  SQLite (profiles + scan history)
- modules/ocr_engine.py        image clean-up, Tesseract, column/dish rebuild
- modules/barcode_engine.py    pyzbar + OpenCV decoders, check-digit validation
- modules/openfoodfacts.py     product lookup and nutrition
- modules/allergen_engine.py   green/yellow/red rules, disease rules
- modules/sos.py               emergency card (Pillow) and e-mail (smtplib)

## Deploy
`docker build -t safebite . && docker run -p 5000:5000 --env-file .env safebite`
Phone cameras only work on https or localhost, so deploy behind https for live scanning.
