import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import database, main
from app.database import Base
from app.data_loader import load_csv_into_db

TEST_DB_URL = "sqlite:///./test_leadflow.db"


@pytest.fixture(scope="function")
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", TestSessionLocal)
    monkeypatch.setattr(main, "SessionLocal", TestSessionLocal)

    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    main.app.dependency_overrides[database.get_db] = override_get_db

    csv_path = os.path.join(os.path.dirname(__file__), "..", "data", "leads_seed.csv")
    db = TestSessionLocal()
    load_csv_into_db(csv_path, db)
    db.close()

    with TestClient(main.app) as c:
        yield c

    main.app.dependency_overrides.clear()
