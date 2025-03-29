import valkey
import pytest
import os
import logging
import shutil
import time
from valkeytests.valkey_test_case import ValkeyTestCase, ValkeyServerHandle
from valkey import ResponseError
from error_handlers import ErrorStringTester


class SimpleTestCase(ValkeyTestCase):
    '''
    Simple test case, single server without loading JSON module.
    '''
    @pytest.fixture(autouse=True)
    def setup_test(self, setup):
        server_path = f"{os.path.dirname(os.path.realpath(__file__))}/.build/binaries/{os.environ['SERVER_VERSION']}/valkey-server"
        self.server, self.client = self.create_server(testdir = self.testdir,  server_path=server_path)

    def teardown(self):
        if self.is_connected():
            self.client.execute_command("FLUSHALL SYNC")
            logging.info("executed FLUSHALL at teardown")
        super(SimpleTestCase, self).teardown()

    def is_connected(self):
        try:
            self.client.ping()
            return True
        except:
            return False


class JsonTestCase(SimpleTestCase):
    '''
    Base class for JSON test, single server with JSON module loaded.
    '''

    def verify_error_response(self, client, cmd, expected_err_reply):
        try:
            client.execute_command(cmd)
            assert False
        except ResponseError as e:
            assert_error_msg = f"Actual error message: '{str(e)}' is different from expected error message '{expected_err_reply}'"
            assert str(e) == expected_err_reply, assert_error_msg

    @pytest.fixture(autouse=True)
    def setup_test(self, setup):
        server_path = f"{os.path.dirname(os.path.realpath(__file__))}/.build/binaries/{os.environ['SERVER_VERSION']}/valkey-server"
        args = {'loadmodule': os.getenv('MODULE_PATH'), "enable-debug-command": "local", 'enable-protected-configs': 'yes'}
        self.server, self.client = self.create_server(testdir = self.testdir,  server_path=server_path, args=args)

        self.error_class = ErrorStringTester

    def teardown(self):
        super(JsonTestCase, self).teardown()
