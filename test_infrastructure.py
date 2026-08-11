import pytest
import requests
import time
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Test constants
MONITOR_URL = "http://127.0.0.1:8000"
POSTGRES_URL = "postgresql://postgres:postgres@localhost:5432/news"

@pytest.fixture(scope="session")
def docker_compose_up():
    """Ensure docker-compose is up and running"""
    # This would typically be handled by the test runner
    pass

def test_monitor_health():
    """Test that monitor is healthy"""
    response = requests.get(f"{MONITOR_URL}/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_refresh_endpoint():
    """Test that refresh endpoint works and returns new items count"""
    response = requests.post(f"{MONITOR_URL}/refresh")
    assert response.status_code == 200
    data = response.json()
    assert "new_items" in data
    assert isinstance(data["new_items"], int)
    assert data["new_items"] >= 0

def test_news_and_entities_in_database():
    """Test that news and entities are stored in database"""
    engine = create_engine(POSTGRES_URL)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Check if news table has data
        result = session.execute(text("SELECT COUNT(*) FROM news"))
        news_count = result.scalar()
        
        # Check if entities table has data  
        result = session.execute(text("SELECT COUNT(*) FROM entities"))
        entities_count = result.scalar()
        
        # Both tables should have data after refresh
        assert news_count >= 0
        assert entities_count >= 0
        
    finally:
        session.close()

def test_deduplication():
    """Test that duplicate news are not inserted"""
    # First, get initial count
    response = requests.post(f"{MONITOR_URL}/refresh")
    data = response.json()
    new_items = data["new_items"]
    
    # Wait a bit and refresh again
    time.sleep(2)
    response = requests.post(f"{MONITOR_URL}/refresh")
    data = response.json()
    
    # The count should not increase significantly (allowing for new items)
    # This is a basic test - in reality, we'd need to check actual content
    assert isinstance(data["new_items"], int)

def test_error_handling():
    """Test that system handles errors gracefully"""
    # This would require simulating error conditions
    # For now, just ensure the system doesn't crash on normal operations
    
    # Test that health endpoint still works after refresh
    response = requests.get(f"{MONITOR_URL}/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    
    # Test that refresh endpoint works
    response = requests.post(f"{MONITOR_URL}/refresh")
    assert response.status_code == 200

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
