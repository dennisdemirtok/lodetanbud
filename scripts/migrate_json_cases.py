"""
Manuell körning av legacy-migreringen (körs annars automatiskt vid appstart):

    python -m scripts.migrate_json_cases
"""

import asyncio

from app.db import init_db
from app.db_migrate import migrate_legacy_json


async def main() -> None:
    await init_db()
    n = await migrate_legacy_json()
    print(f"Migrerade {n} cases från JSON till databasen.")


if __name__ == "__main__":
    asyncio.run(main())
