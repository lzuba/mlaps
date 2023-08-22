import datetime
import logging
import uuid

from flask_table import Table, Col, DatetimeCol, LinkCol
from flask import url_for
import dbClient


class TableBuilder():
    # sorts the passed items according to the passed sort column with the given reverse order
    def get_sorted_by(self, items, sort, reverse: bool = False):
        return sorted(items, key=lambda x: getattr(x, sort), reverse=reverse)
    """
    Needs a database connection to pull the data to populate the tables
    """
    def __init__(self, mysql_conx: dbClient.dbClient):
        self.mysql = mysql_conx

    """
    Renders a html table filled with all enrolled machines in the given order and sorting
    """
    def getAccessTable(self, sort_by='aid',sort_reverse=False):
        # gets all recorded password access from the database
        data = self.mysql.getAccessLog()
        # creates compatible row objects from the table object
        items = list()
        for entry in data:
            items.append(AccessEntry(**entry))
        logging.getLogger('mlaps').debug(sort_by)
        # renders the table with all parameters given and the generated rows
        return AccessTable(self.get_sorted_by(items, sort=sort_by, reverse=(sort_reverse == 'desc')), classes=['table table-striped table-dark'], sort_by=sort_by, sort_reverse=(sort_reverse == 'desc'))
    """
    Renders a html table filled with all recorded password decryptinos in the given order and sorting
    """
    def getMachineTable(self, sort_by='mid',sort_reverse=False):
        # greps all known machines from the database
        data = self.mysql.getMachineList()
        # creates compatible row objects from the table object
        items = list()
        for entry in data: items.append(MachineEntry(**entry))
        logging.getLogger('mlaps').debug(sort_by)
        # renders the table with all parameters given and the generated rows
        return MachineTable(self.get_sorted_by(items, sort=sort_by, reverse=(sort_reverse == 'desc')), classes=['table table-striped table-dark'], sort_by=sort_by, sort_reverse=(sort_reverse == 'desc'))

    def getShortPasswordTable(self, mid: uuid.UUID):
        pws = self.mysql.getMachinesPasswords(mid)
        shortPasswordList = list()
        for pw in pws:
            self.mysql.checkPasswordStatus(pw)
            shortPasswordList.append(ShortPasswordEntry(pwid=pw.id, isSet=pw.password_set, status=pw.status, receivedTime=pw.password_received, expiredTime=pw.password_expiry))
        return ShortPasswordTable(shortPasswordList, classes=['table table-striped table-dark'])

    def getCheckinTable(self, mid: uuid.UUID):
        checkins = self.mysql.getMachinesCheckins(mid)
        checkinList = list()
        for checkin in checkins:
            checkinList.append(CheckinListEntry(ckid=checkin.id, cktime=checkin.checkin_time))
        return CheckinTable(checkinList, classes=['table table-striped table-dark'])

    def getPosDuplicatesTable(self, mid: uuid.UUID):
        posDuplicates = self.mysql.getMachinesPosDuplicates(mid)
        posDuplicatesList = list()
        for posDuplicate in posDuplicates:
            posDuplicatesList.append(PosDuplicateEntry(posDuplicate.id, posDuplicate.hostname, posDuplicate.serialnumber))
        return PosDuplicateTable(posDuplicatesList, classes=['table table-striped table-dark'])

    def getGeneralInfoTable(self, data: dict[str: str]):
        infolist = list()
        for key, value in data.items():
            infolist.append(GeneralInfoEntry(infotype=key, info=value))
        return GeneralInfoTable(infolist, classes=['table table-striped table-dark'])


class PasswordCol(Col):
    """Class that will just output whatever it is given and will not
    escape it.
    """
    def td_format(self, content: int):
        return f"""
        <div class="btn-group" role="group">
            <button class="btn btn-primary btn-sm" hx-get="{url_for('.handleShowPassword', mid=content)}" hx-target="#response-div" hx-trigger="click" _="on htmx:afterOnLoad wait 10ms then add .show to #modal then add .show to #response-div" >Show Password</button>
            <button class="btn btn-primary btn-sm" hx-get="{url_for('.handleCreateShareLinkPassword', mid=content)}" hx-target="#response-div" hx-trigger="click" _="on htmx:afterOnLoad wait 10ms then add .show to #modal then add .show to #response-div" >Share Link</button>
            <button class="btn btn-secondary btn-sm" hx-get="{url_for('.handleExpireNow', mid=content)}" hx-target="#toast-div" hx-swap="beforeend" >Expire Password Now</button>
            <button class="btn btn-danger btn-sm" hx-get="{url_for('.handleDisableMachine', mid=content)}" hx-target="#toast-div" hx-swap="beforeend" hx-confirm="Are you sure you wish to disable the machine?" >Disable Machine</button>
        </div>
        """

class ExpiryCol(Col):
    """Class that will just output whatever it is given and will not
    escape it.
    """
    def td_format(self, content: int):
        return f"""
        <button class="btn btn-danger btn-sm" hx-get="{url_for('.handleDisableMachine', mid=content)}" hx-target="#toast-div" hx-swap="beforeend" hx-confirm="Are you sure you wish to disable the machine?" >Disable Machine</button>
        """

class MachineTable(Table):
    # structure/columns of the machine table
    mid = LinkCol('ID of Machine', 'handleDetailedMachine', url_kwargs=dict(mid='mid'), attr='mid')
    hostname = Col('Hostname')
    serialnumber = Col('Serialnumber')
    enroll_time = DatetimeCol('Enrollment Timestamp', datetime_format="medium")
    enroll_success = Col('Enrollment Successful')
    password_status = Col('Password Status')
    password = PasswordCol('Password')
    allow_sort = True

    def sort_url(self, col_key, reverse=False):
        if reverse:
            direction = 'desc'
        else:
            direction = 'asc'
        return url_for('home', sort=col_key, direction=direction)

class MachineEntry():
    def __init__(self, mid, hostname, serialnumber, enroll_time,enroll_success, disabled, password_status='Unknown'):
        # here all fields defined in the table must be filled, also need to be in sync with the table
        self.mid = mid
        self.hostname = hostname
        self.serialnumber = serialnumber
        self.password = mid
        self.enroll_time = enroll_time
        self.enroll_success = enroll_success
        self.password_status = password_status


class AccessTable(Table):
    # structure/columns of the machine table
    aid = Col('ID')
    admin_kurzel = Col("Admin's Name")
    getTime = DatetimeCol('Timestamp', datetime_format="medium")
    mid = Col('Machine ID')
    msn = Col('Machine Serialnumber')
    mhn = Col('Machine Hostname')
    pwid = Col('Password ID')
    allow_sort = True

    def sort_url(self, col_key, reverse=False):
        if reverse:
            direction = 'desc'
        else:
            direction = 'asc'
        return url_for('handle_access_log', sort=col_key, direction=direction)

class AccessEntry():
    def __init__(self, aid, admin_kurzel, getTime, machine_id, machine_serialnumber, machine_hostname, password_id):
        # here all fields defined in the table must be filled, also need to be in sync with the table
        self.aid = aid
        self.admin_kurzel = admin_kurzel
        self.getTime = getTime
        self.mid = machine_id
        self.msn = machine_serialnumber
        self.mhn = machine_hostname
        self.pwid = password_id

class ShortPasswordCol(Col):
    """Class that will just output whatever it is given and will not
    escape it.
    """
    def td_format(self, content: int):
        return f"""
        <div class="btn-group" role="group">
            <button class="btn btn-primary btn-sm" hx-get="{url_for('.handleShowPassword', pwid=content)}" hx-target="#response-div" hx-trigger="click" _="on htmx:afterOnLoad wait 10ms then add .show to #modal then add .show to #response-div" >Show Password</button>
            <button class="btn btn-secondary btn-sm" hx-get="{url_for('.handleExpireNow', pwid=content)}" hx-target="#toast-div" hx-swap="beforeend" >Expire Password Now</button>
        </div>
        """

class ShortPasswordTable(Table):
    #structure of password table
    pwid = Col('ID')
    isSet = Col('Set')
    status = Col('Status')
    receivedTime = DatetimeCol('Received', datetime_format="medium")
    expiredTime = DatetimeCol('Expired', datetime_format="medium")
    pw = ShortPasswordCol('Options')

class ShortPasswordEntry():
    def __init__(self, pwid: uuid.UUID, isSet: bool, status: str, receivedTime: datetime.datetime, expiredTime: datetime.datetime):
        self.pwid = pwid
        self.isSet = isSet
        self.status = status
        self.receivedTime = receivedTime
        self.expiredTime = expiredTime
        self.pw = pwid

class CheckinTable(Table):
    ckid = Col('Checkin-ID')
    cktime = DatetimeCol('Timestamp', datetime_format="medium")

class CheckinListEntry():
    def __init__(self, ckid: uuid.UUID, cktime: datetime.datetime):
        self.ckid = ckid
        self.cktime = cktime

class PosDuplicateTable(Table):
    mid = LinkCol('ID of Machine', 'handleDetailedMachine', url_kwargs=dict(mid='mid'), attr='mid')
    hostname = Col('Hostname')
    serialnumber = Col('Serialnumber')
    expireButton = ExpiryCol('Expire Button')

class PosDuplicateEntry():
    def __init__(self, mid, hostname, serialnumber):
        self.mid = mid
        self.hostname = hostname
        self.serialnumber = serialnumber
        self.expireButton = mid

class GeneralInfoTable(Table):
    infotype = Col("type")
    info = Col("info")

    def thead(self):
        return ''

class GeneralInfoEntry():
    def __init__(self, infotype: str, info: str):
        self.infotype = infotype
        self.info = info
