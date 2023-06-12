import unittest
import uuid
from fixtures.db import DBMock
import datetime
from freezegun import freeze_time
from pony import orm

class TestDBInit(unittest.TestCase):
    def setUp(self):
        self.db = DBMock()

    def tearDown(self):
        self.db.reset_db()

    def testDBInit(self):
        """Test DB Init"""
        assert self.db.getAccessLog() == []
        assert (
                self.db.getLatestSuccessfulPassword(uuid.UUID("61877565-5fe5-4175-9f2b-d24704df0b74"))
                is None
        )

    @freeze_time("2022-01-14")
    def testInsertMachine(self):
        """Test DB GetAccessLog"""
        uid = uuid.UUID("61877565-5fe5-4175-9f2b-d24704df0b74")
        assert self.db.createMachine(uid, "test", "testitest") is True
        assert self.db.updateMachineInfo(uid, "test2", "testitest2") is True
        assert self.db.getMachineList() == [
            {
                "mid": uuid.UUID("61877565-5fe5-4175-9f2b-d24704df0b74"),
                "hostname": "testitest2",
                "serialnumber": "test2",
                "enroll_time": datetime.datetime(2022, 1, 14, 0, 0),
                "enroll_success" : True,
                "disabled" : False,
                "password_status": 'Unknown'
            }
        ]

    @freeze_time("2022-01-14")
    def testInsertCheckin(self):
        """Test DB GetAccessLog"""
        # setup
        uid = uuid.UUID("61877565-5fe5-4175-9f2b-d24704df0b74")
        assert self.db.createMachine(uid, "test", "testitest") is True

        assert self.db.createCheckin(uid) is True

    @freeze_time("2022-01-14")
    def testInsertPassword(self):
        """Test DB GetAccessLog"""
        # setup
        uid = uuid.UUID("61877565-5fe5-4175-9f2b-d24704df0b74")
        assert self.db.createMachine(uid, "test", "testitest") is True
        pw = "mysafepassword1234"
        assert self.db.createPassword(uid, pw) is True
        #assert self.db.updatePasswordStatus(True, uid) is True
        with orm.db_session:
            expected_pw = DBMock.Password(id=uuid.uuid4(),
                                          machine_id=self.db.readMachine(uid),
                                          password=pw,
                                          password_set=True,
                                          status='Unseen',
                                          password_received=datetime.datetime(2022, 1, 14, 0, 0),
                                          password_expiry=datetime.datetime(2022, 1, 14, 0, 0, 1))
            returned_pw = self.db.getLatestSuccessfulPassword(uid)
        assert returned_pw.machine_id.id == expected_pw.machine_id.id
        assert returned_pw.password == expected_pw.password
        assert returned_pw.password_received == expected_pw.password_received
        assert returned_pw.password_set == expected_pw.password_set
        assert returned_pw.password_expiry == expected_pw.password_expiry

    @freeze_time("2022-01-14")
    def testInsertAccessLog(self):
        """Test DB GetAccessLog"""
        # setup
        uid = uuid.UUID("61877565-5fe5-4175-9f2b-d24704df0b74")
        assert self.db.createMachine(uid, "test", "testitest") is True
        assert self.db.createPassword(uid, "mysafepassword123") is True
        with orm.db_session:
            expected_machine = self.db.readMachine(uid)
            # expected_machine = DBMock.Machine(id=uid,
            #                                   hostname="test",
            #                                   serialnumber="testitest",
            #                                   enroll_time=datetime.datetime(2022, 1, 14, 0, 0),
            #                                   passwords=(),
            #                                   access_log=(),
            #                                   check_in=())
            expected_pw = DBMock.Password(id=uuid.uuid4(),
                                          machine_id=expected_machine,
                                          password="mysafepassword123",
                                          password_set=False,
                                          password_received=datetime.datetime(2022, 1, 14, 0, 0),
                                          password_expiry=datetime.datetime(2022, 1, 14, 0, 0, 1))
            assert self.db.createAccessEntry("admin", expected_machine, expected_pw) is True
            returned_log: dict = self.db.getAccessLog()
            del returned_log[0]['aid']
            assert returned_log == [
                {
                    "admin_kurzel" : "admin",
                    "getTime" : datetime.datetime(2022, 1, 14, 0, 0),
                    "machine_id" : expected_machine.id,
                    "password_id" : expected_pw.id,
                    "machine_hostname" : "testitest",
                    "machine_serialnumber" : "test"
                }
            ]




if __name__ == "__main__":
    unittest.main()
