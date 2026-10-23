import os
import sys

# Ensure Cython C-extensions in SQLAlchemy are disabled to prevent Windows Application Control DLL blocks
os.environ["DISABLE_SQLALCHEMY_CEXT"] = "1"
