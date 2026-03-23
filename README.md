# WebScraper AI

A full-stack Django web scraping pipeline with AI-powered analysis.

## Features

- Scrape any website — WordPress, React, PHP, plain HTML
- Sitemap discovery (robots.txt + sitemap.xml + fallback link crawl)
- Adjustable scrape depth (1-10 slider)
- PDF report generation
- AI key-value extraction (rule-based + OpenAI GPT)
- Export to JSON, CSV, Excel
- Scheduled scraping with change detection
- Page browser with multi-page selection and analysis
- Full dashboard UI

## Tech Stack

- **Backend**: Django 4.x, Django REST Framework
- **Task Queue**: Celery + Redis
- **Database**: PostgreSQL
- **Scraping**: Scrapy, Playwright (JS sites)
- **PDF**: ReportLab
- **AI**: LangChain + OpenAI
- **Export**: openpyxl (Excel), CSV, JSON
- **Infrastructure**: Docker + Docker Compose

## Quick Start
```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/webscraper-ai.git
cd webscraper-ai

# Copy environment file
cp .env.example .env
# Edit .env with your values

# Build and start
docker compose build
docker compose up -d

# Run migrations
docker compose exec django python manage.py migrate
docker compose exec django python manage.py createsuperuser

# Open dashboard
# http://localhost:8000/
```

## Project Structure
```
scraper_project/
├── app/
│   ├── config/          # Django settings, URLs, Celery config
│   └── scraper/         # Main app — models, views, tasks
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```
