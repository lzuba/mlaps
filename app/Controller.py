import datetime
import sys, base64, configparser, dbClient, hsmclient, logger, atexit, uuid, time, flask, tableBuilder, secrets, random, \
    hashlib
from apscheduler.schedulers.background import BackgroundScheduler
from pony import orm
from flask_wtf.csrf import generate_csrf
from flask import Response


class Controller():
    # number of allowed usages of the HSM Token configured in the HSM
    hsmTokenMaxUses = 10

    def __init__(self):
        # Setup the config and secret parser, considering if the script is called in development mode
        self.__config = configparser.ConfigParser()
        self.__secrets = configparser.ConfigParser()
        self.devmode = '-dev' in list(sys.argv)
        if self.devmode:
            self.__config.read('app/config-dev.ini')
            self.__secrets.read('app/secrets-dev.ini')
        else:
            self.__config.read('app/config.ini')
            self.__secrets.read('app/secrets.ini')
        # Starts the logger with a custom format
        self.__logger = logger.Logger(self.__config['LOGGING']['LEVEL'])
        # Setup the mysql connection with the pony ORM
        self.__mysqlConx = dbClient.dbClient(self.__logger, self.__config['MYSQL']['username'],
                                             self.__secrets['MYSQL']['password'],
                                             self.__config['MYSQL']['host'], self.__config['MYSQL']['database'],
                                             self.devmode)

        # Setup the tablebuilder with the db connection for server-side html table building
        self.__tableBuilder = tableBuilder.TableBuilder(self.__mysqlConx)
        # Setup runtime tables to store temporary valid sharelinks and valid updatesessionids
        self.__updateSessions = {}
        self.__shareLinks = {}

        """
        Trys to read the HSM login credentials from the auth-secret table, if no rows are present read the table again in 5 sec indefinitely until a line was successfully read
        """
        while True:
            with orm.db_session:
                hsmData = self.__mysqlConx.readHSMSecret()
            if hsmData:
                break
            else:
                time.sleep(5)

        # Login to the HSM and obtain a token
        self.__hsmClient = hsmclient.HSMClient(self.__logger, self.getHSMHost(), hsmData['role_id'],
                                               hsmData['secret_id'])

        #After the hsm authenticated, renew secrets immediately in order to ensure correct timing between renewals
        #self.renewHsmSecret()

        """ Setup the interval scheduler to automatically renew the HSM token and login credentials """
        # 10800 is 3 hours in seconds
        # 7200 is 2 hours
        self.__scheduler = BackgroundScheduler()
        self.__scheduler.add_job(func=self.renewHsmSecret, trigger="interval", seconds=9000)
        self.__scheduler.add_job(func=self.reLoginHsm, trigger="interval", seconds=3500)
        self.__scheduler.start()
        # Shut down the scheduler when exiting the app
        atexit.register(lambda: self.__scheduler.shutdown())

    def getCompanyName(self) -> str:
	return self.__config["GENERAL"]["company-name"]

    def getKeycloakReam(self) -> str:
        return self.__config["KEYCLOAK"]["realm"]

    def getHSMHost(self) -> str:
        return self.__config["HSM"]["host"]

    """
    Checks if the given UUID from a request is known in the database
    Returns a boolean according
    """
    def checkUUID(self, uid: uuid.UUID) -> bool:
        with orm.db_session:
            if self.__mysqlConx.readMachine(uid):
                return True
            else:
                return False

    """
    Combines the index html template with the rendered machine html table
    Appends a csrf token to the response and returns it
    """
    def handleIndex(self, sort_col: str, directionReverse) -> Response:
        resp: Response = flask.make_response(flask.render_template("index.html",
                                                         table=self.__tableBuilder.getMachineTable(sort_by=sort_col,
                                                                                                   sort_reverse=directionReverse)))
        resp.set_cookie('X-CSRFToken', generate_csrf(), secure=True, httponly=True)
        return resp

    """
    Combines the accesslog html template with the rendered audit html table
    """
    def handleAccessLog(self, sort_col: str, directionReverse) -> str:
        return flask.render_template("accesslog.html",
                                     table=self.__tableBuilder.getAccessTable(sort_by=sort_col, sort_reverse=directionReverse))

    """
    Adds an checkin entry in the database with the given UUID,
    Checks if the password of given machine is expired
        if it is not, return a list with just boolean true
        if it is, return a list with boolean false and a new updatesessionid with is also saved in a dict
    """
    def handleCheckin(self, uid: uuid.UUID, hn: str, sn: str) -> list:
        with orm.db_session:
            self.__mysqlConx.createCheckin(uid)
            if not self.__mysqlConx.updateMachineInfo(uid, sn, hn):
                return [False, "Failed to update machine with hostname and serialnumber"]
            if self.__mysqlConx.checkPasswordValidityString(uid):
                return [True]
            else:
                #usid is updateSessionID
                usid: str = self.get_random_string()
                self.__updateSessions.update({uid: usid})
                return [False, {'updateSessionID': usid}]

    """
    Trys to save the given password with the provided uuid and updateSessionID
    Returns an error message if any off the steps fail or a simple "ok" in a list if everything succeeded
    """
    def handleUpdatePassword(self, password: str, uid: str, updateSessionID: str) -> list:
        self.__logger.debug(updateSessionID)
        self.__logger.debug(self.__updateSessions)

        # Check if a password is needed and if the given updatesessionid is currently registered to the provided UUID
        if not uid in self.__updateSessions:
            self.__logger.warn(f"Rejecting updatePassword payload of {uid} because the latest password is not expired")
            return [False, "Password not expired"]
        elif not updateSessionID == self.__updateSessions.get(uid):
            self.__logger.warn(f"Rejecting updatePassword payload of {uid} because the client sent an invalid updateSessionID")
            return [False, "Wrong UpdateSessionID was sent"]

        with orm.db_session:
            # Gets and checks if the given uuid is known as a machine
            machine: dbClient.dbClient.Machine = self.__mysqlConx.readMachine(uid)
            if machine:
                # Check if the hsm token is still valid for the next vault request
                self.checkHSMTokenValidity()
                self.__logger.debug(f"Trying to encrypt Password: '{password}'")
                # Sends the cleartext to the hsm and trys to read the response
                password_encrpy: dict = self.__hsmClient.hsm_enc(password)
                try:
                    password_encrpy: str = password_encrpy['data']['ciphertext']
                except KeyError:
                    self.__logger.warn(
                        f"Rejecting updatePassword payload of {uid} because HSM failed to encrypt the password")
                    return [False, "Failed to encrypt the password in the HSM"]
                # Save the encrypted password to the database
                res = self.__mysqlConx.createPassword(machine.id, password_encrpy)
                # If everything worked, the updatesessionid is removed and a successful response is returned
                if res:
                    return [True, "ok"]
                else:
                    self.__logger.warn(
                        f"Rejecting updatePassword payload of {uid} because the db wasn't able to save the new password")
                    return [False, "Failed to set new Password"]
            else:
                self.__logger.warn(
                    f"Rejecting updatePassword payload of {uid} because the supplied uid (from the cert) was not found")
                return [False, "Machine not found"]

    """
    Handles the second part of the update password workflow
    Check if the submitted request is valid based on the given updateSessionID and UID
    If the request is valid, the supplied password is saved in the DB, the updateSession is completed and Ok is returned
    If the request isn't valid, an appropriated error is returned
    """
    def handleUpdatePasswordConfirmation(self, res,  uid: str, updateSessionID: str):
        self.__logger.debug(updateSessionID)
        self.__logger.debug(self.__updateSessions)

        # Check if a password is needed and if the given updatesessionid is currently registered to the provided UUID
        if not uid in self.__updateSessions:
            self.__logger.warn(f"Rejecting updatePasswordConfirmation payload of {uid} because the latest password is not expired")
            return [False, "Password not expired"]
        elif not updateSessionID == self.__updateSessions.get(uid):
            self.__logger.warn(f"Rejecting updatePasswordConfirmation payload of {uid} because the client sent an invalid updateSessionID")
            return [False, "Wrong UpdateSessionID was sent"]

        if self.__mysqlConx.updatePasswordSecStage(res, uuid.UUID(uid)):
            self.__logger.debug(f"Successfully set new status for newest password for machine {uid}")
            self.__updateSessions.pop(uid)
            return [True, "Ok"]
        else:
            self.__logger.warn(f"Rejecting updatePasswordConfirmation payload of {uid} because the db waa unable "
                               f"to get unconfirmed password or set to new status on the password")
            return [False, "Failed to get unconfirmed password or set to new status on the password"]

    """
    Trys to issue an new certificate for the machine with the given csr, hostname and serialnummber (not of which must be unique)
    Returns a pem format certificate or an string with an error message what step failed
    """
    def handleEnrollClient(self, csr, hostname, serialnumber):
        # Generate a new UUID which will be the id for the machine
        uid = uuid.uuid4()
        with orm.db_session:
            # Create a new entry in the database
            dbResp = self.__mysqlConx.createMachine(uid, serialnumber, hostname)
            if dbResp:
                # if the machine was successfully created,
                # send the csr to the hsm signing endpoint to get a new certicate with the cn set to the previously created uuid
                self.checkHSMTokenValidity()
                hsmResp = self.__hsmClient.hsm_sign_csr(csr, str(uid))
                # if the hsm returned a valid response, return the included certifcate
                if hsmResp != False:
                    # successfully enrolled
                    return hsmResp["data"]["certificate"]
                else:
                    # error occurred
                    self.__logger.warn(f"Failed to sign the CSR in vault")
                    self.__mysqlConx.removeMachine(uid)
                    return "Failed to sign the CSR in vault"
            else:
                # error occurred
                self.__logger.error(f"Failed to create new machine in the DB")
            return "Failed to create new machine in the DB"

    """
    Relogin to HSM vault since the generated token upon login expires
    """
    def reLoginHsm(self):
        with orm.db_session:
            hsmData = self.__mysqlConx.readHSMSecret()
        # recreate the hsmclient with the same login credentials
        self.__hsmClient = hsmclient.HSMClient(self.__logger, self.getHSMHost(), hsmData['role_id'],
                                               hsmData['secret_id'])
        return self.__hsmClient.isAuthenticated

    """
    Generate new hsm secret id since it expires
    """
    def renewHsmSecret(self):
        with orm.db_session:
            # get the current last line for the role id
            lastHsmLine = self.__mysqlConx.readHSMSecret()
            self.checkHSMTokenValidity()
            # grep a new secret id from the hsm with still valid login credentials
            newHsmSecret = self.__hsmClient.hsm_get_new_secret()
            try:
                # assembly a new auth-secret entry to be saved
                newHsmEntry = [lastHsmLine['role_id'], newHsmSecret["data"]["secret_id"]]
                self.__logger.debug(newHsmEntry)
            except KeyError:
                self.__logger.warn("Failed to get a new secret id from the hsm")
                return self.__hsmClient.isAuthenticated
            # save the new credentials to the database
            res = self.__mysqlConx.updateHsmSecret(newHsmEntry)
        self.__logger.info(f"Tried renewing HSM secret with result: {res}")
        # recreate the hsmclient with these login credentials
        self.__hsmClient = hsmclient.HSMClient(self.__logger, self.getHSMHost(), newHsmEntry[0], newHsmEntry[1])
        return self.__hsmClient.isAuthenticated

    """
    Get the requested password for a machine based on the mid from the database, decrypt it in the hsm and returns it in plaintext
    Also records the decryption in the audit log using the given name (logged in admin)
    """
    def handleGetPassword(self, admin_name: str, mid="", pwid=""):
        with orm.db_session:
            # get the password the database using the given machine uuid
            if mid != "":
                latestPassword = self.__mysqlConx.getLatestSuccessfulPassword(uuid.UUID(mid))
                returntext = f"Machine {mid}"
                self.__logger.debug("Searching for password by machine id")
            if pwid != "":
                latestPassword = self.__mysqlConx.readPassword(uuid.UUID(pwid))
                returntext = f"Password {pwid}"
                self.__logger.debug("Searching for password by password id")
            if latestPassword:
                # if a password was found,
                # log the attempt to decrypt the password in the audit log
                self.__mysqlConx.createAccessEntry(admin_name, mid if mid != "" else latestPassword.machine_id.id, latestPassword.id)
                #decrypt the password and return it
                return self._decryptPassword(password=latestPassword)
            else:
                if pwid == "" and mid == "": return "Not uuid was supplied"
                return f"Password not found using {returntext}"

    """
    Handle the decryption of the password
    Takes a password object directly from the db
    Returns the decrypted password as a string or an error 
    """
    def _decryptPassword(self, password : dbClient.dbClient.Password) -> str:
        #check if a hsm request can be made
        try:
            self.checkHSMTokenValidity()
        except ValueError as err:
            self.__logger.warn(str(err))
            return "Decryption failed, HSM Token invalid"
        # try to decrypt the password in the hsm
        jsonResponse = self.__hsmClient.hsm_dec(password.password)
        self.__logger.debug(jsonResponse)
        # try to read the password from the hsm response
        try:
            clearText = jsonResponse['data']['plaintext']
            self.__mysqlConx.updatePasswordStatus(password)
            self.__mysqlConx.expirePasswordDelayed(password, hours=1)
            return base64.b64decode(clearText).decode('UTF-8')
        except KeyError:
            return "Decryption failed in HSM"

    """
    Trys to set the expiration data of the latest password from the given machine to the current time, therefore expiring it immediately
    Returns a string describing what step failed or a success message
    """
    def handleExpireNowButton(self, mid="", pwid="") -> str:
        with orm.db_session:
            if mid != "":
                pw = self.__mysqlConx.getLatestSuccessfulPassword(uuid.UUID(mid))
                returntext = f"for Machine {mid}"
                self.__logger.debug("Expiring Password by Machine id")
            if pwid != "":
                pw = self.__mysqlConx.readPassword(uuid.UUID(pwid))
                returntext = pwid
                self.__logger.debug("Expiring Password by Password id")
            if pw:
                res = self.__mysqlConx.expirePassword(pw)
                if res:
                    return f"Success: Password {returntext} is now marked as expired"
                else:
                    return f"Error: Failed to mark Password {returntext} in db"
            else:
                if pwid == "" and mid == "": return "Not uuid was supplied"
                return f"Error: Password {returntext} was not found"

    """
    Trys to disable machine with the given mid
    Returns a string describing what step failed or a success message
    """
    def handleDisableMachine(self, mid) -> str:
        with orm.db_session:
            res = self.__mysqlConx.disableMachine(mid)
            if res:
                return f"Machine {mid} was successfully disabled"
            else:
                return f"Failed to disable machine {mid}"

    """
    Returns the rendered machine table with the passed sorting column and direction, populated with all rows from the database
    """
    def handleGetMachineTable(self, sort_col='mid', direction=False):
        return self.__tableBuilder.getMachineTable(sort_by=sort_col, sort_reverse=direction)

    """
    Returns the rendered machine table with the passed sorting column and direction, populated with all rows from the database
    """
    def handleGetAccessLogTable(self, sort_col='aid', direction=False):
        return self.__tableBuilder.getAccessTable(sort_by=sort_col, sort_reverse=direction)

    """
    Needs to be called before or after making a request to the HSM, since one token can only be used ten times.
    Returns None if the token is still valid or the token has been successfully renewed.
    Raises an Exception if the token renewal failed
    """
    def checkHSMTokenValidity(self):
        # keep one use reserved for +-1 mistake and renewal
        if self.__hsmClient.uses >= self.hsmTokenMaxUses - 1:
            res = self.reLoginHsm()
            if res:
                self.__logger.debug("HSM Token has been renewed with the last permitted request")
                return
            else:
                raise ValueError("HSM Token is over its permitted uses and failed to renew")
        else:
            self.__logger.debug(f"HSM Token is still valid, current uses: {self.__hsmClient.uses}")
            return

    # https://www.hacksplaining.com/prevention/weak-session
    """
    Returns a securely generated random string.
    The default length of 12 with the a-z, A-Z, 0-9 character set returns
    a 71-bit value. log_2((26+26+10)^12) =~ 71 bits
    """
    def get_random_string(self, length=12,
                          allowed_chars='abcdefghijklmnopqrstuvwxyz'
                                        'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789') -> str:
        # This is ugly, and a hack, but it makes things better than
        # the alternative of predictability. This re-seeds the PRNG
        # using a value that is hard for an attacker to predict, every
        # time a random string is required. This may change the
        # properties of the chosen random sequence slightly, but this
        # is better than absolute predictability.
        random.seed(
            hashlib.sha256(
                ("%s%s%s" % (
                    random.getstate(),
                    time.time(),
                    self.__secrets['MYSQL']['password'])).encode('utf-8')
            ).digest())
        return ''.join(secrets.choice(allowed_chars) for i in range(length))

    """
    Associate a pw from a machine to a random string and also save at which time this association was requested
    Return the random string
    """
    def handleCreateShareLink(self, mid, pw, admin_name) -> str:
        tempStr: str = self.get_random_string(32)
        curTime: datetime.datetime = datetime.datetime.utcnow()

        #create access log entry
        self.__mysqlConx.createAccessEntry(admin_name, mid, self.__mysqlConx.getLatestSuccessfulPassword(uuid.UUID(mid)).id)
        #create entry for valid share link
        self.__shareLinks.update({tempStr: {'creationTime': curTime, 'mid': mid, 'pw': pw}})
        return tempStr

    """
    Check if an entry with key=randomStr exists in the shareLinks dict, if not it returns False
    Then it returns True if the creationTime of the entry difference is under 15 minutes compared to current time otherwise it returns False
    """
    def checkSharePasswordStr(self, randomStr) -> bool:
        self.__logger.debug(self.__shareLinks)
        self.__logger.debug(randomStr)
        if randomStr in self.__shareLinks:
            entry: dict = self.__shareLinks[randomStr]
            curTime: datetime.datetime = datetime.datetime.utcnow()
            if (entry['creationTime'] + datetime.timedelta(minutes=15)) > curTime:
                self.__logger.info("Found valid share link")
                return True
            self.__logger.warn("Found expired share link")
            return False
        else:
            self.__logger.warn("No valid share link found")
            return False

    """
    Checks if the provided password is correct (how ever thats gonna work) 
    and if correct returns password associated to the rid from the shareLinks/Database
    otherwise an error is returned
    """
    def handleSharePassword(self, rid: str, pw: str) -> str:
        entry: dict = self.__shareLinks[rid]
        if pw != entry['pw']:
            self.__logger.info("Wrong password was send for share password request" + rid)
            return "Wrong Password"
        with orm.db_session:
            password: dbClient.dbClient.Password = self.__mysqlConx.getLatestSuccessfulPassword(uuid.UUID(entry['mid']))
            return self._decryptPassword(password=password)

    """
    Get all non disabled non enrolled machines from the db and disable them
    Returns a string describing who many machines have been disabled
    """
    def handleDisableUnenrolledMachines(self) -> str:
        with orm.db_session:
            machines = self.__mysqlConx.getNonDisabledNonEnrolledMachines()
            c = machines.count()
            self.__logger.debug(f"Found {c} non disabled non enrolled machines, going to disable")
            for machine in machines:
                machine.disabled = True
            orm.commit()
            return f"{c} machines have been successfully disabled"

    """
    
    """
    def handleDetailedMachine(self, mid: str):
        uMid = uuid.UUID(mid)
        with orm.db_session:
            pwTable = self.__tableBuilder.getShortPasswordTable(uMid)
            dupTable = self.__tableBuilder.getPosDuplicatesTable(uMid)
            checkTable = self.__tableBuilder.getCheckinTable(uMid)
            machine = self.__mysqlConx.readMachine(uMid)
            infoTable = self.__tableBuilder.getGeneralInfoTable({'UUID:': machine.id, 'Serialnumber:': machine.serialnumber,
                                                                 'Enrollment Timestamp': machine.enroll_time,
                                                                 'Enrollment Success': machine.enroll_success,
                                                                 'Is Disabled': machine.disabled})

        return flask.render_template("machine.html", generalInfo=infoTable, hostName=machine.hostname,
                                    posDuplicates=dupTable, passwords=pwTable, checkins=checkTable)
