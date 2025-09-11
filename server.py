from typing import Dict, Optional
from litestar import Litestar, get, post
from mdict.mdict_db import MdictDb
import os
import sys


# Path to the LDOCE dictionary
LDOCE_PATH = "./static/LongmanDictionaryOfContemporaryEnglish6thEnEn.mdx"

# Global database instance
mdict_db_instance: Optional[MdictDb] = None


async def startup_handler() -> None:
    """Initialize database on server startup"""
    global mdict_db_instance
    if not os.path.exists(LDOCE_PATH):
        print(f"Error: Dictionary not found at {LDOCE_PATH}")
        sys.exit(1)
    
    print(f"Initializing database with dictionary: {LDOCE_PATH}")
    mdict_db_instance = MdictDb(LDOCE_PATH)
    print("Database initialized")


async def shutdown_handler() -> None:
    """Clean up database on server shutdown"""
    print("Server shutting down")


@get(path="/health")
async def health_check() -> Dict[str, str]:
    return {"status": "healthy"}


@post(path="/query")
async def query_word(data: Dict[str, str]) -> str:
    word = data["word"]
    # TODO: Implement MDX/MDD word lookup functionality
    return f"Definition for '{word}' not implemented yet"




app = Litestar(
    route_handlers=[health_check, query_word],
    on_startup=[startup_handler],
    on_shutdown=[shutdown_handler],
)


def main():
    """Main function to run the server"""
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()