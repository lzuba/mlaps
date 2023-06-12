import datetime, uuid
import logging
import pprint

from pony import orm
from pony.orm import desc


class dbClient:
    dbClient = orm.Database()

    def __init__(self, logger, username, password, host, database, isdev):
        self.devmode = isdev
        self.logger = logger
        self.dbClient.bind(
            provider="mysql", host=host, user=username, passwd=password, db=database
        )
        orm.set_sql_debug(True)
        self.dbClient.generate_mapping(create_tables=True)

    class Machine(dbClient.Entity):
        id = orm.PrimaryKey(uuid.UUID)
        hostname = orm.Required(str)
        serialnumber = orm.Required(str)
        enroll_time = orm.Required(datetime.datetime, precision=6)
        enroll_success = orm.Required(bool, default=False)
        disabled = orm.Required(bool, default=False)
        passwords = orm.Set("Password")
        access_log = orm.Set("AccessLog")
        check_in = orm.Set("Checkin")

    class Password(dbClient.Entity):
        id = orm.PrimaryKey(uuid.UUID)
        machine_id = orm.Required("Machine")
        password = orm.Required(str)
        status = orm.Required(str, default='Unseen')
        password_set = orm.Required(bool, default=False)
        password_received = orm.Required(datetime.datetime, precision=6)
        password_expiry = orm.Required(datetime.datetime, precision=6)
        access_log = orm.Set("AccessLog")

    class AccessLog(dbClient.Entity):
        id = orm.PrimaryKey(int, auto=True, size=64)
        admin_kurzel = orm.Required(str)
        getTime = orm.Required(datetime.datetime, precision=6)
        machine_id = orm.Required("Machine")
        password_id = orm.Required("Password")

    class Auth_secret(dbClient.Entity):
        id = orm.PrimaryKey(int, auto=True, size=64)
        role_id = orm.Required(str)
        secret_id = orm.Required(str)

    class Checkin(dbClient.Entity):
        id = orm.PrimaryKey(int, auto=True, size=64)
        uuid = orm.Required(uuid.UUID)
        mid = orm.Required("Machine")
        checkin_time = orm.Required(datetime.datetime, precision=6)

    ##### Vault Methods #####

    @orm.db_session
    def readHSMSecret(self):
        try:
            return self.__convertQueryToDict(
                self.Auth_secret.select().order_by(lambda c: orm.desc(c.id)).limit(1)
            )[0]
        except Exception as e:
            self.logger.error(e)
            return None

    @orm.db_session
    def updateHsmSecret(self, entry):
        try:
            newSecret = self.Auth_secret(role_id=entry[0], secret_id=entry[1])
            return True
        except Exception as e:
            self.logger.error(e)
            return False

    ##### Read Methods #####

    @orm.db_session
    def readMachine(self, uid):
        try:
            return self.Machine.get(id=uid)
        except Exception as e:
            self.logger.error(e)
            return False

    @orm.db_session
    def readPassword(self, uid: uuid.UUID) -> Password:
        try:
            return self.Password.get(id=uid)
        except Exception as e:
            self.logger.error(e)
            return False

    @orm.db_session
    def getLatestSuccessfulPassword(self, mid: uuid.UUID):
        try:
            pw = self.Password.select(lambda c: c.machine_id.id == mid and c.password_set == True
                                                and c.machine_id.disabled == False).order_by(
                lambda c: orm.desc(c.password_received)
            )
            if pw:
                return pw.limit(1)[0]
            else:
                return None
        except Exception as e:
            self.logger.error(e)
            return None

    @orm.db_session
    def getMachineList(self):
        try:
            allMachines = self.Machine.select().where(lambda m: m.disabled == False)
            return self.__convertQueryToDict(allMachines)
        except Exception as e:
            self.logger.error(e)
            return False

    """
    Returns a list of dict, ig
    """
    @orm.db_session
    def getAccessLog(self):
        try:
            allAccess = self.AccessLog.select()
            return self.__convertQueryToDict(allAccess)
        except Exception as e:
            self.logger.error(e)
            return False

 """
    """
    @orm.db_session
    def getMachinesPasswords(self, mid: uuid.UUID):
        try:
            return self.Password.select(lambda c: c.machine_id.id == mid).order_by(lambda d: orm.desc(d.password_received))
        except Exception as e:
            self.logger.error(e)
            return False

    """
    """
    @orm.db_session
    def getMachinesCheckins(self, mid: uuid.UUID):
        try:
            return self.Checkin.select(lambda c: c.mid.id == mid).order_by(lambda d: orm.desc(d.checkin_time))
        except Exception as e:
            self.logger.error(e)
            return False

    """
    """
    @orm.db_session
    def getMachinesByHostname(self, hostname: str):
        try:
            return self.Machine.select(lambda c: c.hostname == hostname)
        except Exception as e:
            self.logger.error(e)
            return False

    """
    """
    @orm.db_session
    def getMachinesBySerialnumber(self, serialnumber: str):
        try:
            return self.Machine.select(lambda c: c.serialnumber == serialnumber)
        except Exception as e:
            self.logger.error(e)
            return False

    """
    """
    @orm.db_session
    def getMachinesPosDuplicates(self, mid: uuid.UUID):
        try:
            self.logger.debug(mid)
            machine = self.readMachine(mid)
            posDuplList = list()
            posDuplList.extend(self.getMachinesByHostname(machine.hostname)[:])
            posDuplList.extend(self.getMachinesBySerialnumber(machine.serialnumber)[:])
            self.logger.debug(posDuplList)
            #exclude own machine from result, since it had to be in both queries
            #also exclude already disabled machines
            return set([posDupl for posDupl in posDuplList if not posDupl.id == machine.id and not posDupl.disabled])
        except Exception as e:
            self.logger.error(e)
            return False

    """
    Returns all non disabled machine with unsuccessful enrollment status
    """
    @orm.db_session
    def getNonDisabledNonEnrolledMachines(self):
        try:
            return self.Machine.select().where(lambda m: m.disabled is False and m.enroll_success is False)
        except Exception as e:
            self.logger.error(e)
            return False

    @orm.db_session
    def checkPasswordValidityString(self, uid):
        """
        Parameter
            uid - str: id of the machine
        Check if the latest password for given machine id(uid) is expired
        Return True if the password is not expired and therefore still valid
        Return False if the password is expired and needs to be updated
        """
        password = self.getLatestSuccessfulPassword(uuid.UUID(uid))
        if password:
            return self.checkPasswordValidity(password)
        else:
            self.logger.warn(f"Unable to find password for given UUID {uid}")
        return False

    @orm.db_session
    def checkPasswordValidity(self, pw):
        """
        Parameter
            pw - Password: Password Object from oom
        Check if the given password is expired
        Return True if the password is not expired and therefore still valid
        Return False if the password is expired and needs to be updated
        """
        timeNow = datetime.datetime.utcnow()
        timePasswordExpiry = pw.password_expiry
        # timePasswordExpiry = datetime.datetime.strptime(timePasswordExpiry,"%Y-%m-$d %H:$M:$S.$f")

        if timePasswordExpiry > timeNow:
            return True
        else:
            return False

    ##### Update Methods #####

    @orm.db_session
    def updateMachineInfo(self, uid, serialnumber, hostname):
        machine = self.readMachine(uid)
        try:
            if not machine.enroll_success: machine.enroll_success = True
            machine.serialnumber = serialnumber
            machine.hostname = hostname
            orm.commit()
            return True
        except Exception as e:
            self.logger.error(e)
            return False

    @orm.db_session
    def disableMachine(self, uid):
        machine = self.readMachine(uid)
        try:
            machine.disabled = True
            orm.commit()
            return True
        except Exception as e:
            self.logger.error(e)
            return False

    @orm.db_session
    def checkPasswordStatus(self, pw):
        if pw.status == 'Expired': return
        try:
            if not self.checkPasswordValidity(pw):
                pw.status = 'Expired'
                orm.commit()
        except Exception as e:
            self.logger.error(e)

    @orm.db_session
    def updatePasswordStatus(self, pw):
        try:
            pw.status = 'Seen'
            orm.commit()
        except Exception as e:
            self.logger.error(e)

    @orm.db_session
    def updatePasswordSecStage(self, res : str, mid):
        pw = self.Password.select(lambda c: c.machine_id.id == mid and c.password_set == False).order_by(
            lambda c: orm.desc(c.password_received)
        )
        if pw:
            pw = pw.limit(1)[0]
            if not res: self.logger.warn(f"Machine {mid} has reported failed password change with result {res}")
            try:
                pw.password_set = True if not res.startswith("Failed to") else False
                orm.commit()
                self.maintainLastFiveSuccessfulPasswords(mid)
                return True
            except Exception as e:
                self.logger.error(e)
            self.maintainLastFiveSuccessfulPasswords(mid)
            return False
        else:
            self.maintainLastFiveSuccessfulPasswords(mid)
            return False


    @orm.db_session
    def expirePassword(self, password):
        return self.expirePasswordDelayed(password)

    @orm.db_session
    def expirePasswordDelayed(self, password, minutes=0, hours=0, days=0):
        try:
            password.password_expiry = datetime.datetime.utcnow() + datetime.timedelta(minutes=minutes, hours=hours, days=days)
            # commit is automatically executed upon leaving the db_session scope
            orm.commit()
            return True
        except Exception as e:
            self.logger.error(e)
            return False

    ##### Create Methods #####

    @orm.db_session
    def createCheckin(self, uid):
        machine = self.readMachine(uid)
        if not machine: return 5
        mid = machine.id
        cTime = datetime.datetime.utcnow()
        try:
            newCheckin = self.Checkin(uuid=uid, mid=mid, checkin_time=cTime)
            return True
        except Exception as e:
            self.logger.error(e)
            return False

    @orm.db_session
    def createPassword(self, machine_id, password):
        timeNow = datetime.datetime.utcnow()
        if self.devmode:
            timeExpiry = timeNow + datetime.timedelta(seconds=1)
        else:
            #set validity to 7 days minus five minute to avoid
            #   a checkin with a set password that has a few seconds/minutes validity left
            timeExpiry = timeNow + datetime.timedelta(days=7) - datetime.timedelta(minutes=5)

        try:
            newPassword = self.Password(
                id=uuid.uuid4(),
                machine_id=machine_id,
                password=password,
                status='Unseen',
                password_set=False,
                password_received=timeNow,
                password_expiry=timeExpiry,
            )
            return True
        except Exception as e:
            self.logger.error(e)
            return False

    @orm.db_session
    def createMachine(self, uid, serial, hostname):
        try:
            newMachine = self.Machine(
                id=uid,
                hostname=hostname,
                serialnumber=serial,
                enroll_time=datetime.datetime.utcnow(),
                enroll_success=False,
                disabled=False,
            )
            return True
        except Exception as e:
            self.logger.error(e)
            return False


    @orm.db_session
    def createAccessEntry(self, admin_name, mid, pwid):
        try:
            newAccessLog = self.AccessLog(
                admin_kurzel=admin_name,
                getTime=datetime.datetime.utcnow(),
                machine_id=mid,
                password_id=pwid,
            )
            return True
        except Exception as e:
            self.logger.error(e)
            return False


    #### Delete Methods ####

    @orm.db_session
    def removeMachine(self, uid):
        try:
            machine = self.readMachine(uuid.UUID(uid))
            if machine:
                machine.delete()
                orm.commit()
                return True
            else:
                self.logger.warn(f"Failed to delete machine with id {uid}")
                return False
        except Exception as e:
            self.logger.error(e)
            return False


    #### Helper Methods ####
    def __convertQueryToDict(self, query):
        allDict = list()
        for entry in query:
            if isinstance(entry, self.AccessLog):
                newEntry = entry.to_dict()
                with orm.db_session:
                    machine: dbClient.Machine = self.readMachine(newEntry['machine_id'])
                    newEntry.update({'machine_serialnumber': machine.serialnumber,
                                     'machine_hostname': machine.hostname})
                repl = {"id": "aid"}
                allDict.append({repl.get(k, k): newEntry[k] for k in newEntry})
            elif isinstance(entry, self.Machine):
                # pw cam be ether a string that contains 'Unknown' or a password object
                if list(entry.passwords):
                    pw = entry.passwords.order_by(desc(self.Password.password_expiry)).first()
                else:
                    pw = 'Unknown'

                newEntry = entry.to_dict()
                repl = {"id": "mid"}
                res = {
                    repl.get(key, key): newEntry[key]
                    for key in newEntry if key not in ["passwords", "access_log", "check_in"]
                }

                if list(entry.passwords):
                    self.checkPasswordStatus(pw)
                    res.update({'password_status': pw.status})
                else:
                    res.update({'password_status': pw})

                allDict.append(res)
            else:
                allDict.append(entry.to_dict())
        return allDict

    @orm.db_session
    def maintainLastFiveSuccessfulPasswords(self, mid):
        n = 5
        try:
            pws = self.Password.select(lambda c: c.machine_id.id == mid).order_by(
                lambda c: orm.desc(c.password_received)
            )
            if len(pws) <= n:
                self.logger.info(f"Machine {mid} has less or equal to {n} passwords saved, returning all")
                return pws
            vcount = 0
            wantedPws = []
            for pw in pws:
                if pw.password_set:
                    wantedPws.append(pw)
                    vcount += 1
                if vcount == n: break
            rmcount = 0
            for pw in pws:
                if pw in wantedPws:
                    wantedPws.remove(pw)
                    continue
                if len(wantedPws) == 0:
                    pw.delete()
                    rmcount += 1
            self.logger.debug(f"Removed {rmcount} password from machine {mid}")
        except Exception as e:
            self.logger.error(e)
            return None
