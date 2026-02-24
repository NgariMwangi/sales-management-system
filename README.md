# Sales Management System

A monolithic Flask web application for managing products, orders, quotations, and deliveries with role-based access control.

## Features

- **Product Management**: CRUD, stock tracking, low-stock alerts, sales history
- **Order Management**: Create orders from catalog or manual items, auto stock deduction, invoices
- **Quotation Management**: Create quotations, convert to orders, validity tracking
- **Delivery Management**: Order-based or standalone deliveries, status tracking, assignment
- **User Management**: Roles (Admin, Manager, Sales, Delivery), authentication, profile
- **Dashboard**: Summary cards, sales trend chart, top products, payment distribution
- **Reports**: Sales, product performance, delivery performance, stock; export PDF/Excel
- **Settings**: Company info, tax rate, currency; Audit log (admin only)

## Tech Stack

- **Backend**: Flask, Flask-SQLAlchemy, Flask-Migrate, Flask-Login, Flask-WTF, Flask-Mail
- **Database**: PostgreSQL
- **Frontend**: Jinja2, Bootstrap 5, Chart.js

## Setup

### 1. Create virtual environment

```bash
python -m venv venv
venv\Scripts\activate   # Windows
# source venv/bin/activate  # Linux/Mac
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Environment variables

Create a `.env` file (or set in shell):

```
FLASK_ENV=development
SECRET_KEY=your-secret-key
DATABASE_URL=postgresql://user:password@localhost:5432/sales_management_dev
# Optional: Flask-Mail
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=your@email.com
MAIL_PASSWORD=app-password
```

### 4. Database

Create the PostgreSQL database, then run migrations:

```bash
flask db upgrade
```

### 5. Create admin user (first run)

```bash
flask shell
```

In the shell:

```python
from app import db
from app.models import User
u = User(username='admin', email='admin@example.com', full_name='Admin', role='admin')
u.set_password('admin123')
db.session.add(u)
db.session.commit()
exit
```

### 6. Run the application

```bash
set FLASK_APP=run.py   # Windows
# export FLASK_APP=run.py  # Linux/Mac
python run.py
# or: flask run
```

Open http://localhost:5000 and log in with the admin user.

## Project Structure

```
├── app/
│   ├── blueprints/     # auth, dashboard, products, orders, quotations, deliveries, reports, users, settings
│   ├── forms/          # Flask-WTF forms
│   ├── models/         # SQLAlchemy models
│   ├── services/       # Business logic (order, quotation, delivery, numbering, audit)
│   └── templates/      # Jinja2 + Bootstrap 5
├── config.py
├── run.py
├── requirements.txt
└── README.md
```

## Roles & Access

| Role    | Products | Orders/Quotations | Deliveries | Reports | Users | Settings | Audit |
|---------|----------|-------------------|------------|---------|-------|----------|-------|
| Admin   | Full     | Full              | Full       | Yes     | Yes   | Yes      | Yes   |
| Manager | Full     | Full              | Full       | Yes     | No    | Yes      | No    |
| Sales   | CRUD     | Create/View       | View       | Yes     | No    | No       | No    |
| Delivery| View     | No                | Assigned   | No      | No    | No       | No    |

## Deployment (Gunicorn + Nginx)

- Use **Gunicorn** as WSGI: `gunicorn -w 4 -b 0.0.0.0:5000 "app:create_app('production')"`
- Set `FLASK_ENV=production` and a strong `SECRET_KEY`
- Configure Nginx as reverse proxy and serve static files
- Use SSL (e.g. Let's Encrypt) and secure cookies (already set in ProductionConfig)

## Testing

```bash
FLASK_ENV=testing pytest
```

Optional: add `weasyprint` for PDF export and ensure PostgreSQL is used for tests via `TEST_DATABASE_URL`.
