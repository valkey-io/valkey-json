from utils_json import DEFAULT_MAX_PATH_LIMIT, DEFAULT_STORE_PATH
from json_test_case import JsonTestCase
from valkeytests.conftest import resource_port_tracker
import logging, os, pathlib
import pytest
from error_handlers import ErrorStringTester
from valkey.exceptions import ResponseError

logging.basicConfig(level=logging.DEBUG)


# --- Helpers for crafting raw DUMP/RESTORE payloads (issue #107) ---

_CRC64_POLY = 0xad93d23594c935a9


def _reflect64(value):
    """Reverse the bit order of a 64-bit integer."""
    result = 0
    for i in range(64):
        if (value >> i) & 1:
            result |= 1 << (63 - i)
    return result


def _build_crc64_table():
    poly = _reflect64(_CRC64_POLY)
    table = []
    for n in range(256):
        crc = n
        for _ in range(8):
            crc = (crc >> 1) ^ poly if (crc & 1) else (crc >> 1)
        table.append(crc & 0xFFFFFFFFFFFFFFFF)
    return table


_CRC64_TABLE = _build_crc64_table()


def crc64(data, crc=0):
    """Valkey/Redis CRC-64 (Jones variant) over a byte string."""
    for b in data:
        crc = _CRC64_TABLE[(crc ^ b) & 0xFF] ^ (crc >> 8)
    return crc & 0xFFFFFFFFFFFFFFFF


def rdb_save_len(n):
    """Encode n using Valkey's RDB length encoding."""
    if n < (1 << 6):
        return bytes([n])                                  # 6-bit length
    elif n < (1 << 14):
        return bytes([0x40 | (n >> 8), n & 0xFF])          # 14-bit length
    elif n <= 0xFFFFFFFF:
        return bytes([0x80]) + n.to_bytes(4, 'big')        # RDB_32BITLEN
    else:
        return bytes([0x81]) + n.to_bytes(8, 'big')        # RDB_64BITLEN


# RDB_TYPE_MODULE_2 frames each saved value with a module opcode so it can be parsed
# without the module loaded. ValkeyModule_SaveUnsigned emits: opcode + length.
RDB_MODULE_OPCODE_EOF = 0
RDB_MODULE_OPCODE_UINT = 2

# JSON encver-0 metacodes (see meta_codes in dom.cc), each framed with OPCODE_UINT.
JSON_METACODE_NULL = 0x01
JSON_METACODE_STRING = 0x02
JSON_METACODE_ARRAY = 0x40


RDB_MODULE_OPCODE_STRING = 5


def module_save_unsigned(n):
    """Encode ValkeyModule_SaveUnsigned: opcode + length."""
    return rdb_save_len(RDB_MODULE_OPCODE_UINT) + rdb_save_len(n)


def module_save_string_buffer(data):
    """Encode ValkeyModule_SaveStringBuffer: opcode + len + data."""
    return rdb_save_len(RDB_MODULE_OPCODE_STRING) + rdb_save_len(len(data)) + data


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

    def test_rdb_restore_legacy_array_oom_bounded(self):
        """
        Regression test for issue #107: legacy RDB load passed an untrusted array count
        directly to Reserve() and looped without IO-error checks, enabling OOM via RESTORE.
        The fix caps pre-reservation and breaks on the first error.
        """
        import valkey
        client = self.server.get_new_client()

        # Self-check: CRC-64 matches the known test vector.
        assert crc64(b"123456789") == 0xe9c6d914c4b8d9ca

        # Extract module id and RDB version from a genuine DUMP.
        assert b'OK' == client.execute_command('JSON.SET', 'arr', '.', '[1,2,3]')
        genuine = bytes(client.execute_command('DUMP', 'arr'))

        # Verify our CRC matches the server's footer.
        assert crc64(genuine[:-8]) == int.from_bytes(genuine[-8:], 'little')
        assert genuine[0] == 7, f"unexpected RDB type byte {genuine[0]:#x}"
        assert genuine[1] == 0x81, f"unexpected module-id length encoding {genuine[1]:#x}"
        module_id = int.from_bytes(genuine[2:10], 'big')
        assert (module_id & 0x3FF) == 3, f"expected genuine encver 3, got {module_id & 0x3FF}"
        rdbver_bytes = genuine[-10:-8]

        # Downgrade encver to 0 to route through the legacy loader.
        legacy_id_bytes = bytes([0x81]) + (module_id & ~0x3FF).to_bytes(8, 'big')

        def make_restore_payload(body):
            base = bytes([7]) + legacy_id_bytes + body + rdbver_bytes
            return base + crc64(base).to_bytes(8, 'little')

        # Positive case: a valid legacy array [null, null] must load correctly.
        valid_body = (module_save_unsigned(JSON_METACODE_ARRAY)
                      + module_save_unsigned(2)
                      + module_save_unsigned(JSON_METACODE_NULL)
                      + module_save_unsigned(JSON_METACODE_NULL)
                      + rdb_save_len(RDB_MODULE_OPCODE_EOF))   # module value EOF marker
        assert b'OK' == client.execute_command(
            'RESTORE', 'legacy_ok', 0, make_restore_payload(valid_body))
        assert b'[null,null]' == client.execute_command('JSON.GET', 'legacy_ok')

        # Negative case: ~4 billion declared elements, no data. Pre-fix this OOM'd.
        huge_body = (module_save_unsigned(JSON_METACODE_ARRAY)
                     + module_save_unsigned((1 << 32) - 1))
        evil_payload = make_restore_payload(huge_body)

        # Short timeout as safety net if the bound regresses.
        guarded = valkey.Valkey(host="localhost", port=self.server.port, socket_timeout=15)
        with pytest.raises(ResponseError):
            guarded.execute_command('RESTORE', 'evil', 0, evil_payload)

        # Server must still be alive after rejecting the crafted payload.
        assert client.execute_command('PING')
        assert b'OK' == client.execute_command('JSON.SET', 'after', '.', '[1,2,3]')
        assert b'[1,2,3]' == client.execute_command('JSON.GET', 'after')

    def test_rdb_restore_legacy_array_truncated_element(self):
        """
        Safety-net: server survives a RESTORE with a truncated string element (EOF
        mid-body). Passes on unfixed code too (core's stream-EOF catches it first),
        but guards against regressions in that outer check.
        """
        import valkey
        client = self.server.get_new_client()

        # Get module id and rdbver from a genuine DUMP.
        assert b'OK' == client.execute_command('JSON.SET', '_tmp', '.', '"x"')
        genuine = bytes(client.execute_command('DUMP', '_tmp'))
        client.execute_command('DEL', '_tmp')
        module_id = int.from_bytes(genuine[2:10], 'big')
        rdbver_bytes = genuine[-10:-8]
        legacy_id_bytes = bytes([0x81]) + (module_id & ~0x3FF).to_bytes(8, 'big')

        def make_restore_payload(body):
            base = bytes([7]) + legacy_id_bytes + body + rdbver_bytes
            return base + crc64(base).to_bytes(8, 'little')

        # Array with a truncated string element (declares 10 bytes, provides 3).
        truncated_body = (module_save_unsigned(JSON_METACODE_ARRAY)
                         + module_save_unsigned(2)
                         + module_save_unsigned(JSON_METACODE_STRING)
                         + rdb_save_len(RDB_MODULE_OPCODE_STRING)
                         + rdb_save_len(10)    # declares 10 bytes of string data
                         + b'abc')             # only 3 bytes -- EOF mid-string

        payload = make_restore_payload(truncated_body)
        guarded = valkey.Valkey(host="localhost", port=self.server.port, socket_timeout=15)
        with pytest.raises(ResponseError):
            guarded.execute_command('RESTORE', 'trunc', 0, payload)

        # Server must remain alive.
        assert client.execute_command('PING')
