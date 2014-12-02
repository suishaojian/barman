# Copyright (C) 2013-2014 2ndQuadrant Italia (Devise.IT S.r.L.)
#
# This file is part of Barman.
#
# Barman is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Barman is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Barman.  If not, see <http://www.gnu.org/licenses/>.

import os
from barman.testing_helpers import mock_backup_info

from mock import patch, Mock
import pytest
from barman.infofile import WalFileInfo

from barman.server import Server


class ExceptionTest(Exception):
    """
    Exception for test purposes
    """
    pass


class TestServer(object):
    @staticmethod
    def build_config(tmpdir=None):
        """
        Build a server instance
        """
        # Instantiate a Server object using mocked configuration file
        config = Mock(name='config')
        config.bandwidth_limit = None
        config.tablespace_bandwidth_limit = None
        config.minimum_redundancy = '0'
        config.retention_policy = None
        if tmpdir:
            config.wals_directory = str(tmpdir.ensure('wals', dir=True))
        return config

    def test_init(self):
        """
        Basic initialization test with minimal parameters
        """
        Server(self.build_config())

    @patch('barman.server.os')
    def test_xlogdb_with_exception(self, os_mock, tmpdir):
        """
        Testing the execution of xlog-db operations with an Exception

        :param os_mock: mock for os module
        :param tmpdir: temporary directory unique to the test invocation
        """
        # unpatch os.path
        os_mock.path = os.path
        # Setup temp dir and server
        server = Server(self.build_config(tmpdir))

        # Test the execution of the fsync on xlogdb file forcing an exception
        with pytest.raises(ExceptionTest):
            with server.xlogdb('w') as fxlogdb:
                fxlogdb.write("00000000000000000000")
                raise ExceptionTest()
        # Check call on fsync method. If the call have been issued,
        # the "exit" section of the contextmanager have been executed
        assert os_mock.fsync.called

    @patch('barman.server.os')
    @patch('barman.server.LockFile')
    def test_xlogdb(self, lock_file_mock, os_mock, tmpdir):
        """
        Testing the normal execution of xlog-db operations.

        :param lock_file_mock: mock for LockFile object
        :param os_mock: mock for os module
        :param tmpdir: temporary directory unique to the test invocation
        """
        # unpatch os.path
        os_mock.path = os.path
        # Setup temp dir and server
        server = Server(self.build_config(tmpdir))
        # Test the execution of the fsync on xlogdb file
        with server.xlogdb('w') as fxlogdb:
            fxlogdb.write("00000000000000000000")
        # Check for calls on fsync method. If the call have been issued
        # the "exit" method of the contextmanager have been executed
        assert os_mock.fsync.called
        # Check for enter and exit calls on mocked LockFile
        lock_file_mock.return_value.__enter__.assert_called_once_with()
        lock_file_mock.return_value.__exit__.assert_called_once_with(
            None, None, None)

        os_mock.fsync.reset_mock()
        with server.xlogdb():
            # nothing to do here.
            pass
        # Check for calls on fsync method.
        # If the file is readonly exit method of the context manager must
        # skip calls on fsync method
        assert not os_mock.fsync.called

    def test_get_wal_full_path(self, tmpdir):
        """
        Testing Server.get_wal_full_path() method
        """
        wal_name = '0000000B00000A36000000FF'
        wal_hash = wal_name[:16]
        server = Server(self.build_config(tmpdir))
        full_path = server.get_wal_full_path(wal_name)
        assert full_path == \
            str(tmpdir.join('wals').join(wal_hash).join(wal_name))

    @patch("barman.server.Server.get_next_backup")
    def test_get_wal_until_next_backup(self, get_backup_mock, tmpdir):
        """
        Simple test for the management of .history files
        """
        # build a WalFileInfo object
        wfile_info = WalFileInfo()
        wfile_info.name = '000000010000000000000003'
        wfile_info.size = 42
        wfile_info.time = 43
        wfile_info.compression = None

        # build a WalFileInfo history object
        history_info = WalFileInfo()
        history_info.name = '00000001.history'
        history_info.size = 42
        history_info.time = 43
        history_info.compression = None

        # create a xlog.db and add the 2 entries
        xlog = tmpdir.mkdir("wals").join("xlog.db")
        xlog.write(wfile_info.to_xlogdb_line() + history_info.to_xlogdb_line())
        # facke backup
        backup = mock_backup_info(begin_wal='000000010000000000000001',
                                  end_wal='000000010000000000000004'
                                  )

        # mock a server object and mock a return call to get_next_backup method
        server = Server(self.build_config(tmpdir))
        get_backup_mock.return_value = mock_backup_info(backup_id="1234567899",
                                        begin_wal='000000010000000000000005',
                                        end_wal='000000010000000000000009')

        wals = []
        for wal_file in server.get_wal_until_next_backup(backup,
                                                         include_history=True):
            # get the result of the xlogdb read
            wals.append(wal_file.name)
        # check for the presence of the .history file
        assert history_info.name in wals
