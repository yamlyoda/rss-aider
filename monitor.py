import asyncio
import logging
from datetime import datetime
from typing import List, Dict, Any
from faststream import FastStream
from faststream.rabbit import RabbitBroker
from pydantic_settings import BaseSettings
import feedparser
import httpx
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Configuration
class Settings(BaseSettings):
    db_host: str = "postgres"
    db_port: int = 5432
    db_name: str = "news"
    db_user: str = "postgres"
    db_password: str = "password"
    broker_url: str = "amqp://guest:guest@rabbitmq:5672/"
    rss_feeds: str = "https://news.yandex.ru/index.rss,https://lenta.ru/rss,https://rg.ru/xml/rss.xml"

settings = Settings()

# Database setup
DATABASE_URL = f"postgresql://{settings.db_user}:{settings.db_password}@{settings.db_host}:{settings.db_port}/{settings.db_name}"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Database models
class News(Base):
    __tablename__ = "news"
    
    id = Column(Integer, primary_key=True, index=True)
    source = Column(String, index=True)
    title = Column(String)
    link = Column(String, unique=True, index=True)
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

# Create tables
Base.metadata.create_all(bind=engine)

# Broker setup
broker = RabbitBroker(settings.broker_url)
app = FastStream(broker)

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# RSS parsing and publishing functions
async def fetch_rss_feed(feed_url: str) -> List[Dict[str, Any]]:
    """Fetch and parse RSS feed"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(feed_url, timeout=10.0)
            response.raise_for_status()
            
            parsed = feedparser.parse(response.text)
            
            # Check if parsing was successful
            if parsed.bozo and parsed.bozo_exception:
                logger.warning(f"Feed {feed_url} has bozo errors: {parsed.bozo_exception}")
            
            articles = []
            
            for entry in parsed.entries:
                try:
                    article = {
                        "source": feed_url,
                        "title": entry.get("title", ""),
                        "link": entry.get("link", ""),
                        "content": entry.get("summary", ""),
                        "published": entry.get("published", "")
                    }
                    # Skip articles without essential fields
                    if article["link"] and article["title"]:
                        articles.append(article)
                except Exception as e:
                    logger.warning(f"Error processing entry from {feed_url}: {e}")
                    continue
            
            return articles
    except httpx.RequestError as e:
        logger.error(f"Network error fetching RSS feed {feed_url}: {e}")
        return []
    except feedparser.ParseError as e:
        logger.error(f"Parsing error for RSS feed {feed_url}: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error fetching RSS feed {feed_url}: {e}")
        return []

async def publish_news_to_queue(news_list: List[Dict[str, Any]]):
    """Publish news to queue"""
    new_items_count = 0
    
    for article in news_list:
        # Check if article already exists
        db = SessionLocal()
        try:
            existing = db.query(News).filter_by(link=article["link"]).first()
            if not existing:
                # Create and publish new news item
                await broker.publish(article, queue="news_queue")
                new_items_count += 1
        except Exception as e:
            logger.error(f"Error checking/publishing article {article['link']}: {e}")
        finally:
            db.close()
    
    return new_items_count

@app.http("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok"}

@app.http("/refresh", methods=["POST"])
async def refresh_feeds():
    """Force refresh RSS feeds and publish new items"""
    logger.info("Starting manual refresh of RSS feeds")
    
    rss_urls = settings.rss_feeds.split(",")
    all_articles = []
    
    # Fetch all feeds concurrently
    tasks = [fetch_rss_feed(url.strip()) for url in rss_urls]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Error fetching feed: {result}")
        else:
            all_articles.extend(result)
    
    # Publish new items to queue
    new_items_count = await publish_news_to_queue(all_articles)
    
    logger.info(f"Manual refresh completed. Published {new_items_count} new items")
    return {"new_items": new_items_count}

# Background task for periodic RSS polling
async def periodic_polling():
    """Periodically poll RSS feeds every 5 minutes"""
    while True:
        try:
            logger.info("Starting periodic RSS polling")
            
            rss_urls = settings.rss_feeds.split(",")
            all_articles = []
            
            # Fetch all feeds concurrently
            tasks = [fetch_rss_feed(url.strip()) for url in rss_urls]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"Error fetching feed: {result}")
                else:
                    all_articles.extend(result)
            
            # Publish new items to queue
            new_items_count = await publish_news_to_queue(all_articles)
            
            logger.info(f"Periodic polling completed. Published {new_items_count} new items")
            
        except Exception as e:
            logger.error(f"Error in periodic polling: {e}")
        
        # Wait 5 minutes
        await asyncio.sleep(300)

# Start background task
@app.after_startup
async def start_background_tasks():
    """Start background tasks after app startup"""
    asyncio.create_task(periodic_polling())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("monitor:app", host="0.0.0.0", port=8000)
