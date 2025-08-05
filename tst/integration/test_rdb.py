from utils_json import DEFAULT_MAX_PATH_LIMIT, DEFAULT_STORE_PATH
from json_test_case import JsonTestCase
from valkeytests.conftest import resource_port_tracker
import logging, os, pathlib
import pytest
from error_handlers import ErrorStringTester

logging.basicConfig(level=logging.DEBUG)

class TestRdb(JsonTestCase):

    def setup_data(self):
        client = self.server.get_new_client()
        client.config_set(
            'json.max-path-limit', DEFAULT_MAX_PATH_LIMIT)
        # Need the following line when executing the test against a running Valkey.
        # Otherwise, data from previous test cases will interfere current test case.
        client.execute_command("FLUSHDB")

        # Load strore sample JSONs. We use strore.json as input to create a document key. Then, use
        # strore_compact.json, which does not have indent/space/newline, to verify correctness of serialization.
        with open(DEFAULT_STORE_PATH, 'r') as file:
            self.data_store = file.read()
        assert b'OK' == client.execute_command(
            'JSON.SET', 'store', '.', self.data_store)

    @pytest.fixture(autouse=True)
    def setup_test(self, setup):
        # Check if we should use external server
        use_external = os.environ.get("VALKEY_EXTERNAL_SERVER", "false").lower() == "true"
        
        if use_external:
            # Use external server
            external_host = os.environ.get("VALKEY_HOST", "localhost")
            external_port = int(os.environ.get("VALKEY_PORT", "6379"))
            self.server, self.client = self.create_server(
                testdir=self.testdir,
                bind_ip=external_host,
                port=external_port,
                external_server=True
            )
        else:
            # Original local server setup
            server_path = f"{os.path.dirname(os.path.realpath(__file__))}/.build/binaries/{os.environ['SERVER_VERSION']}/valkey-server"
            args = {'loadmodule': os.getenv('MODULE_PATH'), "enable-debug-command": "local", 'enable-protected-configs': 'yes'}
            self.server, self.client = self.create_server(testdir=self.testdir, server_path=server_path, args=args)

        self.error_class = ErrorStringTester
        self.setup_data()

    def test_rdb_saverestore(self):
        """
        Test RDB saving
        """
        client = self.server.get_new_client()
        assert True == client.execute_command('save')
        client.execute_command('FLUSHDB')
        assert b'OK' == client.execute_command('DEBUG', 'RELOAD', 'NOSAVE')
