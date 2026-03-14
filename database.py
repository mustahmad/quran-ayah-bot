"""
Модуль для работы с PostgreSQL базой данных на Railway.
Сохраняет историю запросов пользователей и найденных аятов.
"""

import os
import asyncpg
from datetime import datetime

_pool = None


async def get_pool():
    """Получает пул соединений к PostgreSQL."""
    global _pool
    if _pool is None:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            print("⚠️ DATABASE_URL не установлен, БД не подключена")
            return None
        _pool = await asyncpg.create_pool(database_url, min_size=1, max_size=5)
    return _pool


async def init_db():
    """Создаёт таблицы если их нет."""
    pool = await get_pool()
    if not pool:
        return

    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                first_seen TIMESTAMP DEFAULT NOW(),
                last_active TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS search_history (
                id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(user_id),
                query_text TEXT,
                query_type TEXT,
                found_surah INTEGER,
                found_ayah INTEGER,
                found_surah_name TEXT,
                match_score INTEGER,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_search_user_id ON search_history(user_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_search_created ON search_history(created_at)
        """)

    print("✅ База данных инициализирована")


async def save_user(user_id: int, username: str, first_name: str, last_name: str):
    """Сохраняет или обновляет пользователя."""
    pool = await get_pool()
    if not pool:
        return

    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (user_id, username, first_name, last_name, first_seen, last_active)
            VALUES ($1, $2, $3, $4, NOW(), NOW())
            ON CONFLICT(user_id) DO UPDATE SET
                username = $2,
                first_name = $3,
                last_name = $4,
                last_active = NOW()
        """, user_id, username, first_name, last_name)


async def save_search(user_id: int, query_text: str, query_type: str,
                      found_surah: int = None, found_ayah: int = None,
                      found_surah_name: str = None, match_score: int = None):
    """Сохраняет поисковый запрос в историю."""
    pool = await get_pool()
    if not pool:
        return

    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO search_history
            (user_id, query_text, query_type, found_surah, found_ayah,
             found_surah_name, match_score)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
        """, user_id, query_text, query_type, found_surah, found_ayah,
              found_surah_name, match_score)


async def get_user_history(user_id: int, limit: int = 10) -> list:
    """Получает историю поиска пользователя."""
    pool = await get_pool()
    if not pool:
        return []

    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT * FROM search_history
            WHERE user_id = $1
            ORDER BY created_at DESC
            LIMIT $2
        """, user_id, limit)
        return [dict(row) for row in rows]


async def get_stats() -> dict:
    """Получает общую статистику бота."""
    pool = await get_pool()
    if not pool:
        return {"total_users": 0, "total_searches": 0, "top_surahs": []}

    async with pool.acquire() as conn:
        total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
        total_searches = await conn.fetchval("SELECT COUNT(*) FROM search_history")

        top_surahs = await conn.fetch("""
            SELECT found_surah, found_surah_name, COUNT(*) as cnt
            FROM search_history
            WHERE found_surah IS NOT NULL
            GROUP BY found_surah, found_surah_name
            ORDER BY cnt DESC
            LIMIT 5
        """)

        return {
            "total_users": total_users,
            "total_searches": total_searches,
            "top_surahs": [(row["found_surah"], row["found_surah_name"], row["cnt"]) for row in top_surahs],
        }


async def close_db():
    """Закрывает пул соединений."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
