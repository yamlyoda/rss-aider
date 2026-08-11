import logging
from datetime import datetime
from typing import List, Dict, Any
from faststream import FastStream
from faststream.rabbit import RabbitBroker
from pydantic_settings import BaseSettings
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import spacy

# Configuration
class Settings(BaseSettings):
    db_host: str = "postgres"
    db_port: int = 5432
    db_name: str = "news"
    db_user: str = "postgres"
    db_password: str = "password"
    broker_url: str = "amqp://guest:guest@rabbitmq:5672/"
    spacy_model: str = "ru_core_news_sm"

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

class Entity(Base):
    __tablename__ = "entities"
    
    id = Column(Integer, primary_key=True, index=True)
    news_id = Column(Integer, ForeignKey("news.id"))
    label = Column(String)
    text = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

# Create tables
Base.metadata.create_all(bind=engine)

# Load SpaCy model once at startup
try:
    nlp = spacy.load(settings.spacy_model)
    logging.info(f"Successfully loaded SpaCy model: {settings.spacy_model}")
except Exception as e:
    logging.error(f"Failed to load SpaCy model {settings.spacy_model}: {e}")
    raise

# Broker setup
broker = RabbitBroker(settings.broker_url)
app = FastStream(broker)

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def extract_entities(text: str) -> List[Dict[str, str]]:
    """Extract named entities from text using SpaCy"""
    try:
        if not text:
            return []
            
        doc = nlp(text)
        entities = []
        
        for ent in doc.ents:
            entities.append({
                "label": ent.label_,
                "text": ent.text
            })
        
        return entities
    except Exception as e:
        logger.error(f"Error extracting entities: {e}")
        return []

@broker.subscriber("news_queue")
async def process_news(message: Dict[str, Any]):
    """Process news from queue"""
    try:
        logger.info(f"Processing news item: {message['title'][:50]}...")
        
        db = SessionLocal()
        try:
            # Check if news already exists
            existing_news = db.query(News).filter_by(link=message["link"]).first()
            
            if existing_news:
                logger.info(f"News item already exists, skipping: {message['link']}")
                return
            
            # Create news item
            news = News(
                source=message["source"],
                title=message["title"],
                link=message["link"],
                content=message["content"]
            )
            
            db.add(news)
            db.commit()
            db.refresh(news)
            
            # Extract entities
            entities = await extract_entities(message["content"])
            
            # Save entities
            for entity in entities:
                db_entity = Entity(
                    news_id=news.id,
                    label=entity["label"],
                    text=entity["text"]
                )
                db.add(db_entity)
            
            db.commit()
            logger.info(f"Successfully processed news item: {message['title']}")
            
        except Exception as e:
            logger.error(f"Error processing news item: {e}")
            db.rollback()
            raise
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Error in message handler: {e}")
        # Re-raise to let FastStream handle retries
        raise

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("worker:app", host="0.0.0.0", port=8001)
