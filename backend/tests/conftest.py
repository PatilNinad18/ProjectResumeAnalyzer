import os
import sys

# Ensure Cython C-extensions in SQLAlchemy are disabled to prevent Windows Application Control DLL blocks
os.environ["DISABLE_SQLALCHEMY_CEXT"] = "1"

# Route all tests to an isolated test database so tests never pollute the dev database (jd_agent.db)
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_isolated.db")
os.environ.setdefault("LLM_PROVIDER", "mock")
