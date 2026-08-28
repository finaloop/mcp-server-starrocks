"""
Unit tests for the STARROCKS_INIT_COMMAND -> mysql.connector init_command mapping.

Pure-function tests, no StarRocks cluster required.

Run with: pytest tests/test_init_command.py -v
"""

import os
from unittest.mock import patch

from src.mcp_server_starrocks.db_client import DBClient, _build_mysql_init_command_options


class TestBuildMysqlInitCommandOptions:
    def test_unset_returns_empty(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('STARROCKS_INIT_COMMAND', None)
            assert _build_mysql_init_command_options() == {}

    def test_blank_returns_empty(self):
        with patch.dict(os.environ, {'STARROCKS_INIT_COMMAND': '   '}):
            assert _build_mysql_init_command_options() == {}

    def test_set_returns_init_command(self):
        with patch.dict(os.environ, {'STARROCKS_INIT_COMMAND': "SET warehouse = 'wh1'"}):
            assert _build_mysql_init_command_options() == {'init_command': "SET warehouse = 'wh1'"}

    def test_value_is_stripped(self):
        with patch.dict(os.environ, {'STARROCKS_INIT_COMMAND': "  SET warehouse = 'wh1'\n"}):
            assert _build_mysql_init_command_options() == {'init_command': "SET warehouse = 'wh1'"}


class TestDBClientInitCommand:
    def test_connection_params_include_init_command(self):
        with patch.dict(os.environ, {'STARROCKS_INIT_COMMAND': "SET warehouse = 'wh1'"}):
            os.environ.pop('STARROCKS_URL', None)
            os.environ.pop('STARROCKS_FE_ARROW_FLIGHT_SQL_PORT', None)
            client = DBClient()
            assert client.connection_params['init_command'] == "SET warehouse = 'wh1'"

    def test_connection_params_omit_init_command_when_unset(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('STARROCKS_INIT_COMMAND', None)
            os.environ.pop('STARROCKS_URL', None)
            os.environ.pop('STARROCKS_FE_ARROW_FLIGHT_SQL_PORT', None)
            client = DBClient()
            assert 'init_command' not in client.connection_params
