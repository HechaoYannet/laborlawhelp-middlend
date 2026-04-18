import argparse
import asyncio

import asyncpg


async def rollback(database_url: str, anonymous_id: str, user_id: str) -> None:
    conn = await asyncpg.connect(database_url)
    try:
        async with conn.transaction():
            cases_updated = await conn.execute(
                """
                UPDATE cases
                SET user_id = NULL,
                    owner_type = 'anonymous',
                    updated_at = NOW()
                WHERE anonymous_id = $1
                  AND user_id = $2
                """,
                anonymous_id,
                user_id,
            )
            sessions_updated = await conn.execute(
                """
                UPDATE sessions
                SET user_id = NULL,
                    last_active_at = NOW()
                WHERE anonymous_id = $1
                  AND user_id = $2
                """,
                anonymous_id,
                user_id,
            )
            print(f"cases: {cases_updated}")
            print(f"sessions: {sessions_updated}")
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Rollback anonymous to user migration")
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--anonymous-id", required=True)
    parser.add_argument("--user-id", required=True)
    args = parser.parse_args()

    asyncio.run(rollback(args.database_url, args.anonymous_id, args.user_id))


if __name__ == "__main__":
    main()
