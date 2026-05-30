"""
Test fixtures for the FastAPI backend.

Adds the api/ directory to sys.path so tests can import production modules
(`database`, `models`, `routers`) using the same bare imports the app itself
uses. Provides:

  - engine     : session-scoped SQLAlchemy engine pointing at the test DB.
  - db_session : per-test transactional session that rolls back on teardown
                 -- so tests are isolated even though they share one schema.
  - client     : FastAPI TestClient with `get_db` overridden to yield the
                 per-test session, so endpoint code sees the same
                 transactional view as the test asserting on it.

The schema setup (alembic upgrade head) lives in the repo-root conftest so
it fires for ingestion tests too.
"""

import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# api/ on sys.path so `from database import ...` etc. resolve. The root
# conftest already set DATABASE_URL before any test imports happen.
API_DIR = Path(__file__).resolve().parent.parent
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))


@pytest.fixture(scope="session")
def engine():
    """Single engine for the whole session -- migrations and tests share it."""
    return create_engine(os.environ["DATABASE_URL"])


@pytest.fixture
def db_session(engine):
    """Per-test transactional session. Rolls back on teardown for isolation."""
    connection = engine.connect()
    transaction = connection.begin()
    Session = sessionmaker(bind=connection, expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client(db_session):
    """FastAPI TestClient with the get_db dependency overridden.

    Uses TestClient without `with` so the lifespan handler doesn't fire --
    that would re-run alembic upgrade head with a CWD pytest doesn't
    control. Lifespan-specific tests construct their own client.
    """
    from fastapi.testclient import TestClient

    from database import get_db
    from main import app

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


# ---------- data factory fixtures ----------
#
# Each fixture inserts straight via the per-test session, so rollback at
# teardown wipes the data. Tests that need a populated DB import these
# directly.


@pytest.fixture
def sample_set(db_session):
    """Insert a single set row and return its dict-shaped data."""
    from datetime import date

    from models.set import Set

    record = Set(
        id="base1",
        name="Base Set",
        series="Base",
        printed_total=102,
        release_date=date(1999, 1, 9),
        symbol_url="https://example.com/symbol.png",
        logo_url="https://example.com/logo.png",
    )
    db_session.add(record)
    db_session.flush()
    return record


@pytest.fixture
def sample_cards(db_session, sample_set):
    """Insert two cards for the sample set."""
    from models.card import Card

    cards = [
        Card(
            id="base1-4",
            set_id=sample_set.id,
            name="Charizard",
            number="4",
            rarity="rare",
            supertype="Pokemon",
            image_url="https://example.com/4.png",
        ),
        Card(
            id="base1-58",
            set_id=sample_set.id,
            name="Pidgey",
            number="58",
            rarity="common",
            supertype="Pokemon",
            image_url=None,
        ),
    ]
    for c in cards:
        db_session.add(c)
    db_session.flush()
    return cards


@pytest.fixture
def sample_multipliers(db_session, sample_set):
    """Seed condition_multipliers rows for the sample set.

    Covers two rarities ('rare', 'common') and two supertypes ('Pokemon',
    'Trainer') with a representative subset of forward transitions. The
    deliberate quirk: 'common' rarity has only 3 transitions seeded
    (NM->LP, NM->MP, LP->MP) so tests can assert that absent transitions
    don't appear in the response rather than appearing as null.
    """
    from datetime import datetime
    from decimal import Decimal

    from models.condition_multiplier import ConditionMultiplier

    rows = [
        # Rare rarity -- full forward set (NM->LP/MP/HP/DMG plus LP->MP).
        dict(grouping_type="rarity", grouping_value="rare",
             from_condition="NM", to_condition="LP", multiplier="0.6000", data_points=50),
        dict(grouping_type="rarity", grouping_value="rare",
             from_condition="NM", to_condition="MP", multiplier="0.4000", data_points=45),
        dict(grouping_type="rarity", grouping_value="rare",
             from_condition="NM", to_condition="HP", multiplier="0.3000", data_points=30),
        dict(grouping_type="rarity", grouping_value="rare",
             from_condition="NM", to_condition="DMG", multiplier="0.2000", data_points=20),
        dict(grouping_type="rarity", grouping_value="rare",
             from_condition="LP", to_condition="MP", multiplier="0.7000", data_points=40),
        # Common rarity -- partial set so missing-transition assertions are possible.
        dict(grouping_type="rarity", grouping_value="common",
             from_condition="NM", to_condition="LP", multiplier="0.7500", data_points=100),
        dict(grouping_type="rarity", grouping_value="common",
             from_condition="NM", to_condition="MP", multiplier="0.5500", data_points=90),
        dict(grouping_type="rarity", grouping_value="common",
             from_condition="LP", to_condition="MP", multiplier="0.7400", data_points=80),
        # Supertype rows.
        dict(grouping_type="supertype", grouping_value="Pokemon",
             from_condition="NM", to_condition="LP", multiplier="0.6500", data_points=120),
        dict(grouping_type="supertype", grouping_value="Trainer",
             from_condition="NM", to_condition="LP", multiplier="0.7000", data_points=60),
    ]

    inserted = []
    for r in rows:
        cm = ConditionMultiplier(
            set_id=sample_set.id,
            grouping_type=r["grouping_type"],
            grouping_value=r["grouping_value"],
            from_condition=r["from_condition"],
            to_condition=r["to_condition"],
            multiplier=Decimal(r["multiplier"]),
            data_points=r["data_points"],
            last_refreshed=datetime(2026, 5, 1, 12, 0),
        )
        db_session.add(cm)
        inserted.append(cm)
    db_session.flush()
    return inserted


@pytest.fixture
def sample_snapshots(db_session, sample_cards):
    """Insert price snapshots covering current + historical for one card."""
    from datetime import date, datetime

    from models.card import PriceSnapshot

    snaps = [
        # Two snapshots for Charizard to exercise dedup -- the older row
        # must be filtered out by DISTINCT ON in the latest-prices endpoint.
        PriceSnapshot(
            card_id="base1-4",
            source="tcgplayer",
            condition="NM",
            variant=None,
            market_price="100.00",
            captured_at=datetime(2026, 4, 1, 12, 0),
            captured_date=date(2026, 4, 1),
        ),
        PriceSnapshot(
            card_id="base1-4",
            source="tcgplayer",
            condition="NM",
            variant=None,
            market_price="120.00",
            captured_at=datetime(2026, 5, 1, 12, 0),
            captured_date=date(2026, 5, 1),
        ),
        # Holofoil variant -- a different (condition, variant) tuple, so it
        # is its own row in the latest-prices output.
        PriceSnapshot(
            card_id="base1-4",
            source="tcgplayer",
            condition="NM",
            variant="holofoil",
            market_price="200.00",
            captured_at=datetime(2026, 5, 1, 12, 0),
            captured_date=date(2026, 5, 1),
        ),
        # Pidgey, single snapshot.
        PriceSnapshot(
            card_id="base1-58",
            source="tcgplayer",
            condition="NM",
            variant=None,
            market_price="0.50",
            captured_at=datetime(2026, 5, 1, 12, 0),
            captured_date=date(2026, 5, 1),
        ),
    ]
    for s in snaps:
        db_session.add(s)
    db_session.flush()
    return snaps
