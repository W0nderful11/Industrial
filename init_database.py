#!/usr/bin/env python3
"""
Simple database initialization script.
Creates all necessary tables if they don't exist.
"""

import asyncio
import sys
import os
from pathlib import Path

# Add project root directory to PYTHONPATH
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Set environment variable for correct imports
os.environ['PYTHONPATH'] = str(project_root)

print(f"Added path to PYTHONPATH: {project_root}")
print(f"Current working directory: {os.getcwd()}")

try:
    from database.database import ORM
    from database.models import Base
    print("[OK] Imports successful")
except ImportError as e:
    print(f"[ERROR] Import error: {e}")
    sys.exit(1)

async def init_database():
    """Initialize database - create all tables"""
    print("Starting database initialization...")
    
    orm = ORM()
    
    try:
        # Initialize repositories
        print("Initializing ORM...")
        await orm.create_repos()
        
        if not orm.engine:
            print("[ERROR] Failed to create database engine")
            return False
            
        print("[OK] ORM initialized successfully")
        
        # Create all tables
        print("Creating tables...")
        async with orm.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        print("[OK] All tables created successfully!")
        return True
        
    except Exception as e:
        print(f"[ERROR] Database initialization error: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        if orm.engine:
            await orm.engine.dispose()
            print("Database connection closed")

if __name__ == "__main__":
    print("=" * 50)
    print("iOS BOT DATABASE INITIALIZATION")
    print("=" * 50)
    
    success = asyncio.run(init_database())
    
    if success:
        print("Database initialization completed successfully!")
    else:
        print("Database initialization failed!")
        sys.exit(1) 