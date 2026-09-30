"""Fail-closed command-line verification for the private live launch."""
import asyncio
import json

from sqlalchemy import select

from app.core.database import AsyncSessionLocal, engine
from app.core.redis import redis_client
from app.models.user import User
from app.services.launch_readiness import private_launch_readiness


async def main() -> int:
    try:
        await redis_client.connect()
        async with AsyncSessionLocal() as db:
            users = (await db.execute(select(User))).scalars().all()
            if len(users) != 1:
                print(json.dumps({"ready_for_live": False, "blockers": [
                    f"Private mode requires exactly one owner; found {len(users)}"
                ]}, indent=2))
                return 1
            report = await private_launch_readiness(db, users[0].id)
            print(json.dumps(report, indent=2, default=str))
            return 0 if report["ready_for_live"] else 1
    except Exception as exc:
        print(json.dumps({"ready_for_live": False, "blockers": [str(exc)]}, indent=2))
        return 1
    finally:
        await redis_client.disconnect()
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
