# OpDevSM — School Management System

A comprehensive, print-ready school management system built with Django.

## 🚀 Key Features
- **Student & Teacher Management**: Unified profiles with photo upload support.
- **Academic Structure**: Flexible Class, Section, and Subject management.
- **Attendance**: Manual and Biometric sync support (ZKTeco compatible).
- **ID Card Module**: CR80 standard PDF generation with bulk printing (4/page A4).
- **Exam & Reporting**: Multi-period weighting system (Quarterly/Term) with automated grade calculation.
- **Finance**: Automated invoicing, payment tracking, and discount management.

## 🛠️ Tech Stack
- **Backend**: Django 4.x
- **Database**: PostgreSQL (Production), SQLite (Local)
- **PDF Generation**: ReportLab
- **Styling**: Vanilla CSS (Custom Brand)
- **Caching**: LocMemCache

## 💻 Local Setup

1. **Clone the repository**:
   ```bash
   git clone <repo-url>
   cd school-vercel
   ```

2. **Setup Virtual Environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment Variables**:
   Create a `.env` file in the root:
   ```env
   DEBUG=True
   SECRET_KEY=your-secret-key
   ATTENDANCE_API_TOKEN=your-biometric-token
   ```

5. **Run Migrations & Start**:
   ```bash
   python manage.py migrate
   python manage.py runserver
   ```

## 🪪 Biometric Gateway
The system includes a gateway endpoint for local attendance machines:
- **Endpoint**: `/attendance/api/sync/`
- **Method**: POST
- **Payload**:
  ```json
  {
    "token": "your-token",
    "logs": [
      {"biometric_id": "101", "timestamp": "2024-05-12 08:30:00"}
    ]
  }
  ```

## 🧪 Running Tests
```bash
python manage.py test finance attendance exams
```

## 🚢 Deployment
Currently configured for deployment on **DigitalOcean** using Gunicorn and Nginx. CI/CD is managed via **GitHub Actions**.
