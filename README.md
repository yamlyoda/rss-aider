# News Monitoring System

An event-driven system for monitoring news from RSS feeds, extracting named entities using SpaCy, and storing results in PostgreSQL.

## Architecture

```
RSS Feeds → Monitor (Poller + API) → Queue (RabbitMQ) → Worker (NER + DB Storage)
```

## Features

- Polls multiple RSS feeds every 5 minutes
- Manual refresh endpoint (`POST /refresh`)
- Duplicate detection and prevention
- Named Entity Recognition using SpaCy
- PostgreSQL storage with proper schema
- Idempotent operations
- Error handling and logging

## Requirements

- Docker and docker-compose
- Python 3.12+
- uv package manager

## Setup

1. Clone the repository
2. Create `.env` file based on `.env.example`
3. Run `docker-compose up --build`

## Configuration

All configuration is done through environment variables in `.env`:

```
DB_HOST=postgres
DB_PORT=5432
DB_NAME=news
DB_USER=postgres
DB_PASSWORD=password
BROKER_URL=amqp://guest:guest@rabbitmq:5672/
RSS_FEEDS=https://news.yandex.ru/index.rss,https://lenta.ru/rss,https://rg.ru/xml/rss.xml
SPACY_MODEL=ru_core_news_sm
```

## Endpoints

### Monitor Service (port 8000)

- `GET /health` - Health check
- `POST /refresh` - Force refresh RSS feeds and return number of new items

### Worker Service (port 8001)

- Processes messages from the queue automatically

## Database Schema

### news table
- id (primary key)
- source (string)
- title (string)
- link (unique string)
- content (text)
- created_at (datetime)

### entities table
- id (primary key)
- news_id (foreign key to news)
- label (string)
- text (string)
- created_at (datetime)

## Methodology Observations

### Plan/Act Approach
The system was designed using a two-step approach:
1. **Plan**: Design the event-driven architecture with clear separation of concerns
2. **Act**: Implement each component independently

This approach helped in:
- Avoiding tight coupling between services
- Enabling independent scaling of monitor and worker
- Making it easier to test components separately

### Checkpoints and Rollback
Throughout development, git checkpoints were used to:
- Save working versions before major changes
- Quickly rollback when issues were discovered
- Maintain a clear history of implementation steps

### Latency Considerations
The event-driven approach added some latency due to:
- Message queuing overhead
- Network communication between services
- Database write operations

However, this was acceptable for the use case since real-time processing wasn't critical.

## Running the System

1. Start all services: `docker-compose up --build`
2. Check health: `curl http://localhost:8000/health`
3. Force refresh: `curl -X POST http://localhost:8000/refresh`
4. View results in database:
   ```bash
   docker-compose exec postgres psql -U postgres -d news -c \
     "SELECT n.source, n.title, e.label, e.text FROM news n JOIN entities e ON e.news_id = n.id ORDER BY n.created_at DESC LIMIT 20;"
   ```

## Testing

The system can be tested using the endpoints described in `TESTS.md`:
- `docker-compose up` should start all services
- `/health` endpoint should return `{"status":"ok"}`
- `/refresh` should return number of new items
- Database should contain news and entities after processing
