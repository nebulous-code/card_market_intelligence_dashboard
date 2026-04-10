"""
Database connection setup for the API.

This file is responsible for one thing: establishing how the application
connects to PostgreSQL. Everything that needs to talk to the database --
the route handlers, the migration runner -- imports from here.

The connection string (DATABASE_URL) is read from the .env file at the
project root. It must include sslmode=require because Neon, the hosted
PostgreSQL provider used by this project, enforces encrypted connections.
"""

import os

from dotenv import find_dotenv, load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Load environment variables from the .env file.
# find_dotenv() walks up the directory tree from the current file until it
# finds a .env file, so this works whether the server is started from the
# api/ directory or the project root.
load_dotenv(find_dotenv())

# Read the database connection string from the environment.
# This will raise a KeyError immediately at startup if DATABASE_URL is
# missing, which is intentional -- a missing connection string should be
# a hard failure, not a silent one.
DATABASE_URL = os.environ["DATABASE_URL"]

# Create the SQLAlchemy engine.
# The engine is the object that manages the actual connection to PostgreSQL.
# pool_pre_ping=True tells SQLAlchemy to test each connection before using
# it, which prevents errors caused by stale connections that have been
# dropped by the database server (common with cloud-hosted databases).
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# Create a session factory.
# A session is a short-lived workspace for database operations. Each web
# request gets its own session, performs its queries, and then closes.
# autocommit=False means changes are not saved until explicitly committed.
# autoflush=False means SQLAlchemy will not automatically send pending
# changes to the database before each query.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """
    Base class for all SQLAlchemy database models.

    Every model (Set, Card, PriceSnapshot) inherits from this class.
    SQLAlchemy uses it to keep track of all the tables in the application
    so that tools like Alembic can detect schema changes automatically.
    """
    pass


def get_db():
    """
    FastAPI dependency that provides a database session to a route handler.

    This function is used with FastAPI's dependency injection system. When
    a route handler lists it as a dependency, FastAPI automatically calls
    it and passes the resulting session as a parameter. The session is
    guaranteed to be closed when the request finishes, even if an error
    occurred, because of the try/finally block.

    Yields:
        Session: An active SQLAlchemy database session.
    """
    db = SessionLocal()
    try:
        # Yield the session to the route handler that requested it.
        yield db
    finally:
        # Always close the session when the request is done to return
        # the connection back to the pool.
        db.close()
