"""迁移在独立内存数据库上执行，不修改本地 MySQL。"""
import io
from pathlib import Path
import unittest

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from supportflow.db.base import Base
import supportflow.models  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]


class MigrationTests(unittest.TestCase):
    def test_upgrade_matches_models_and_downgrade(self):
        engine = create_engine("sqlite://")
        try:
            with engine.connect() as connection:
                config = Config(str(ROOT / "alembic.ini"))
                config.attributes["connection"] = connection
                command.upgrade(config, "0001_initial")
                connection.exec_driver_sql("INSERT INTO users (username, password_hash, role, is_active, created_at, updated_at) VALUES ('migration-test', 'hash', 'customer', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)")
                command.upgrade(config, "head")
                inspector = inspect(connection)
                self.assertEqual(set(inspector.get_table_names()), set(Base.metadata.tables) | {"alembic_version"})
                self.assertEqual(compare_metadata(MigrationContext.configure(connection), Base.metadata), [])
                for table in Base.metadata.sorted_tables:
                    expected = {str(c.name) for c in table.constraints if c.__class__.__name__ == "CheckConstraint"}
                    actual = {c["name"] for c in inspector.get_check_constraints(table.name)}
                    self.assertEqual(actual, expected, table.name)
                # 再次升级不重建表，也不删除已有数据。
                command.upgrade(config, "head")
                self.assertEqual(connection.exec_driver_sql("SELECT count(*) FROM users").scalar_one(), 1)
                command.downgrade(config, "base")
                self.assertEqual(inspect(connection).get_table_names(), ["alembic_version"])
        finally:
            engine.dispose()

    def test_offline_mysql_sql(self):
        output = io.StringIO()
        config = Config(str(ROOT / "alembic.ini"), output_buffer=output)
        command.upgrade(config, "head", sql=True)
        sql = output.getvalue()
        self.assertEqual(sql.count("CREATE TABLE "), len(Base.metadata.tables) + 1)
        self.assertIn("DATETIME(6)", sql)
        self.assertIn("GENERATED ALWAYS AS", sql)
        self.assertIn("ck_users_userrole", sql)
        self.assertIn("0001_initial", sql)
        self.assertIn("CREATE TABLE auth_sessions", sql)


if __name__ == "__main__":
    unittest.main()
