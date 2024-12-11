#!/PATH/TO/YOUR/PYTHON3
import functools
import os, logging, Controller, sys, base64, customSessionInterface, distinguishedname
from flask_oidc import OpenIDConnect
from flask import Flask, request, jsonify, make_response, send_from_directory, render_template, Response, session
import flask_wtf.csrf
from cheroot.wsgi import Server as WSGIServer, PathInfoDispatcher
from markupsafe import Markup

if __name__ == "__main__":
    devmode = '-dev' in list(sys.argv)
    contr = Controller.Controller()
    app = Flask(__name__)
    companyName = contr.getCompanyName()
    #use customsessioninterface to not send cookies on api calls
    app.session_interface = customSessionInterface.CustomSessionInterface()

    app.config.update(
        {
            "SECRET_KEY": os.urandom(24),
            "OIDC_COOKIE_SECURE": True,
            "OIDC_CLIENT_SECRETS": "app/secrets.json",
            "OIDC_ID_TOKEN_COOKIE_SECURE": True,
            "OIDC_CLOCK_SKEW": 3600,
            "OVERWRITE_REDIRECT_URI": f"https://mlaps.{companyName}.com/oidc_callback",
            "OIDC_RESOURCE_SERVER_VALIDATION_MODE": "online",
            "OIDC_USER_INFO_ENABLED": True,
            "OIDC_OPENID_REALM": contr.getKeycloakReam(),
            "OIDC_SCOPES": ["openid", "email", "profile", "roles"],
            "OIDC_INTROSPECTION_AUTH_METHOD": "client_secret_post",
        }
    )

    if '-dev' in list(sys.argv):
        app.config.update({"OIDC_CLIENT_SECRETS": "app/secrets-dev.json"})

    # initialise flask extensions
    oidc = OpenIDConnect(app)
    csrf = flask_wtf.CSRFProtect(app)


    def get_oidc_user_info() -> dict:
        if oidc.user_loggedin:
            username = session['oidc_auth_profile']["preferred_username"]
            email = session['oidc_auth_profile']["email"]
            groups = session['oidc_auth_profile']["groups"]
            return {"username": username, "email": email, "groups": groups}
        else:
            return None

    """
    Wrapper for checking if the logged-in user has the correct role assigned (webaccess-mlaps)
    If the user has the correct role, the called function gets executed
    If the user is doesn't have the role, the wrapper returns Not Authorized and the called function doesn't get executed
    """
    def checkPermission(func):
        @functools.wraps(func)
        def inner(*args, **kwargs):
            user = get_oidc_user_info()
            logging.getLogger('mlaps').debug(user)
            if user["groups"] is None: return "Not Authorized"
            if 'webaccess_mlaps' in user['groups']: return func(*args, **kwargs)
            return "Not Authorized"
        return inner

    #Returns the favicon in the app/static folder called LAPS.ico
    @app.route('/favicon.ico')
    def favicon():
        return send_from_directory(os.path.join(app.root_path, 'static'),
                                   'LAPS.ico', mimetype='image/vnd.microsoft.icon')

    #Returns the svg favicon in the app/static folder called MLAPS.svg
    @app.route('/favicon.svg')
    def faviconSVG():
        return send_from_directory(os.path.join(app.root_path, 'static'),
                                   'MLAPS.svg', mimetype='image/svg+xml')

    #Returns the legal notice page
    @app.route("/legal_notice", methods=['GET'])  # decorator
    def legal_notice():
        return make_response(render_template("legal-notice.html"))

    #simple healthcheck
    @app.route("/ping", methods=['GET'])  # decorator
    def healthCheck():
        return "pong"

    """
    Handles the index call of the website
    Requires a valid client SSL certificate and the correct oidc role
    Returns a table of all machines and information to them
    """
    @app.route("/", methods=['GET'])  # decorator
    @oidc.require_login
    @checkPermission
    def home():
        # returning a response
        return contr.handleIndex(sort_col=request.args.get('sort', default='mid', type=str),
                                            directionReverse=request.args.get('direction', default='asc', type=str))

    """
    Handles the access log call
    Requires a valid client SSL certificate and the correct oidc role
    Returns a table of all recorded decryptions of passwords by authorized users
    """
    @app.route("/access_log", methods=['GET'])  # decorator
    @oidc.require_login
    @checkPermission
    def handle_access_log():
        # returning a response
        return contr.handleAccessLog(sort_col=request.args.get('sort', default='aid', type=str),
                                             directionReverse=request.args.get('direction', default='asc', type=str))

    """
    Handles the api call to enroll a machine
    Doesnt require any authentication or authorization
    Is also exempted from csrf protection, since this is a "public" endpoint
    Expects json input, {"csr":csr(encoded in base64, utf-8), "hn":hostname, "sn":serialnumber}
    Returns ether a new machine certificate or an error with information why the enrollment failed in a simple http response
    """
    @csrf.exempt
    @app.route('/api/enroll', methods=['POST'])
    def handle_enroll():
        json_data = request.json
        csr_bencoded = json_data["csr"]
        csr = base64.b64decode(csr_bencoded).decode('UTF-8')
        serialnumber = json_data["sn"]
        hostname = json_data["hn"]
        res = contr.handleEnrollClient(csr,hostname,serialnumber)
        if not res.startswith("Failed"):
            resp = make_response(jsonify({"response": res}), 200)
            resp.headers['Content-Type'] = 'application/json'
        else:
            resp = make_response(jsonify({"response": res}), 400)
            resp.headers['Content-Type'] = 'application/json'

        return resp

    """
    Handle the api call to checkin from a machine
    Doesnt require to be logged in via oidc
    Expects a valid SSL certificate
    Returns a json with format {"response": data} where data is ether ok, update, UUID not found and an appropriate http code
    If the response is update, an additional updatesessionid is also sent, to ensure no password gets lost in update process 
    """
    @csrf.exempt
    @app.route('/api/checkin', methods=['POST'])
    def handle_checkin():
        #Parse incoming data
        json_data = request.json
        serialnumber = json_data["sn"]
        hostname = json_data["hn"]
        parsedDN = distinguishedname.string_to_dn(request.headers.get("ssl-client", "dnNotFound"))
        logging.getLogger('mlaps').info(parsedDN)
        if not parsedDN: return "Failed to read certificate correctly", 410
        uid: str = next((dnPart[2:] for dnPart in sum(parsedDN, []) if dnPart.startswith("CN=")), ("uidNotFound"))
        if uid == "uidNotFound": return "Failed to read uid from certificate", 411
        logging.getLogger('mlaps').info(f"handling checkin for uuid:{uid}")
        res: list = contr.handleCheckin(uid, hostname, serialnumber)
        logging.getLogger('mlaps').debug(res)
        if res[0] == True:
            resp = make_response(jsonify({"response": "ok"}), 200)
            resp.headers['Content-Type'] = 'application/json'
        elif isinstance(res[1], dict):
            resp = make_response(jsonify(({"response": "update", **res[1]})), 200)
            resp.headers['Content-Type'] = 'application/json'
        else:
            resp = make_response(jsonify(({"response": res[1]})), 400)
            resp.headers['Content-Type'] = 'application/json'

        return resp


    """
    Handle the api call to send a new password
    Doesnt require to be logged in via oidc
    Expect a valid SSL certificate and json data in the format {"Password":pw(cleartext), "updateSessionID":usid(str)}
    Returns a json response in the format {response} where response can be ether ok or an error message why it failed
    """
    @csrf.exempt
    @app.route('/api/password', methods=['POST'])
    def handle_update_password() -> Response:
        # check if password is expired and uuid matches
        json_data: dict = request.json
        uid: str = request.headers["Ssl-Client"].split(",")[0].split("=")[1]
        password: str = json_data["Password"]
        updateSessionID: str = json_data["updateSessionID"]

        res: list = contr.handleUpdatePassword(password,uid,updateSessionID)
        if res[0] == True:
            resp: Response = make_response(jsonify({"response": res[1]}), 200)
            resp.headers['Content-Type'] = 'application/json'
        else:
            resp: Response = make_response(jsonify({"response": res[1]}), 400)
            resp.headers['Content-Type'] = 'application/json'
        return resp

    """
    Doesnt require to be logged in via oidc
    Expect a valid SSL certificate and json data in the format {"res":error-message or success, "updateSessionID":usid(str)}
    Returns ok as an acknowledgement
    """
    @csrf.exempt
    @app.route('/api/password-confirm', methods=['POST'])
    def handle_update_password_confirm() -> Response:
        # check if password is expired and uuid matches
        json_data: dict = request.json
        uid: str = request.headers["Ssl-Client"].split(",")[0].split("=")[1]
        result: str = json_data["res"]
        updateSessionID: str = json_data["updateSessionID"]
        res: list = contr.handleUpdatePasswordConfirmation(result,uid,updateSessionID)
        if res[0] == True:
            resp: Response = make_response(jsonify({"response": res[1]}), 200)
            resp.headers['Content-Type'] = 'application/json'
        else:
            resp: Response = make_response(jsonify({"response": res[1]}), 400)
            resp.headers['Content-Type'] = 'application/json'

        return resp

    """
    Handle the api call to show a password for a given machine
    Requires a valid client SSL certificate and the correct oidc role
    Requires also a json input in the format {"mid":uuid} or {"pwid":uuid}
    Returns a bootstrap modal in plain html with the decrypted password
    """
    @oidc.require_login
    @checkPermission
    @app.route('/api/getPassword', methods=['GET'])
    def handleShowPassword() -> str:
        pw: str = contr.handleGetPassword(admin_name=get_oidc_user_info()['username'], mid=request.args.get('mid', default=""),
                                          pwid=request.args.get('pwid', default=""))
        resp: str = render_template("modal.html", title="Latest valid password: " if request.args.get('mid', default=False) else "Password: ", body=pw)
        return resp

    """
    Handle the api call to expire a password for a given machine
    Requires a valid client SSL certificate and the correct oidc role
    Requires also a json input in the format {"mid":uuid} or {"pwid":uuid}
    Returns a bootstrap toast in plain html with the confirmation or error message why it failed
    """
    @oidc.require_login
    @checkPermission
    @app.route('/api/expirePassword', methods=['GET'])
    def handleExpireNow() -> str:
        msg: str = contr.handleExpireNowButton(mid=request.args.get('mid', default=""),
                                               pwid=request.args.get('pwid', default=""))
        resp: str = render_template("toast.html", body=msg)
        return resp

    """
    Handle the api call to 
    Requires a valid client SSL certificate and the correct oidc role
    Requires 
    Returns a bootstrap toast in plain html with 
    """
    @oidc.require_login
    @checkPermission
    @app.route('/api/disableMachine', methods=['GET'])
    def handleDisableMachine() -> str:
        msg: str = contr.handleDisableMachine(request.args.get('mid'))
        resp: str = render_template("toast.html", body=msg)
        return resp

    """
    Handle the api call to generate a modal with a password field
    Requires a valid client ssl certificate and correct oidc role
    Returns a modal with a input field
    """
    @oidc.require_login
    @checkPermission
    @app.route('/api/createSharelinkPassword', methods=['GET'])
    def handleCreateShareLinkPassword() -> str:
        html: Markup = Markup('<form hx-post="/api/createSharelink" hx-swap="innerHTML"  hx-target="#response-div">'\
               f"<input type='hidden' id='mid' name='mid' value='{request.args.get('mid')}'>"\
               '<input id="password" name="password" type="password" placeholder="Enter password" required class="form-control">'\
               '</form>')

        return render_template("modal.html", title="Enter a password to protect the sharing link", raw_body=html)

    """
    Handle the api call to generate a temporary link to share a password
    Requires a valid client ssl certificate and correct oidc role
    Returns a modal with the generated link
    """
    @oidc.require_login
    @checkPermission
    @csrf.exempt
    @app.route('/api/createSharelink', methods=['POST'])
    def handleCreateShareLink() -> Response:
        link = contr.handleCreateShareLink(request.form['mid'], request.form['password'],get_oidc_user_info()['username'])
        resp = make_response(render_template("modal.html", title="Sharable link", body=f"{request.host_url}share_password?rid={link}"))
        resp.headers['HX-Trigger'] = 'closeModal'
        return resp

    """
    Handle the get request of a share password link
    Requires no authentication
    Return a page with a prompt to authenticate the request
    """
    @app.route('/share_password', methods=['GET'])
    def handleSharePasswordPage():
        if contr.checkSharePasswordStr(request.args.get('rid')):
            return make_response(render_template("share_password.html", title="MLAPS Share PW", rid=request.args.get('rid')))
        else:
            #return custom error page
            return make_response(render_template("bad_request.html", title="Bad Request"))

    """
    Handle the api call to authenticate a share password page by an admin
    Requires no authentication
    Returns a modal with the password linked to the submitted rid if the authentication was successful,
    otherwise an error is displayed in the modal
    """
    @csrf.exempt
    @app.route('/api/share_password', methods=['POST'])
    def handleSharePasswordAPI():
        rid: str = request.form['rid']
        pw: str = request.form['password']
        if contr.checkSharePasswordStr(rid):
            machinePassword = contr.handleSharePassword(rid, pw)
            resp = render_template("modal.html", title="Password: ", body=machinePassword)
            return resp

    """
    Handle the api call to disable all not successfully enrolled machines
    Requires a valid client ssl certificate and correct oidc role
    Returns a bootstrap toast with raw html
    """
    @oidc.require_login
    @checkPermission
    @app.route('/api/disableUnenrolledMachines', methods=['GET'])
    def handleDisableUnenrolledMachines():
        msg = contr.handleDisableUnenrolledMachines()
        resp = render_template("toast.html", body=msg)
        return resp

    """
    
    """
    @oidc.require_login
    @checkPermission
    @app.route('/detailedMachine', methods=['GET'])
    def handleDetailedMachine():
        args = request.args.to_dict()
        if "mid" not in args:
           return make_response(render_template("bad_request.html", title="Bad Request", reason="Mid not supplied"))
        mid: str = args["mid"]
        res = contr.handleDetailedMachine(mid)
        return make_response(res)


    """

    """
    @oidc.require_login
    @checkPermission
    @app.route('/admin', methods=['GET'])
    def handleAdminPage():
        db, vault, log = contr.handleAdmin()
        return make_response(render_template("admin.html", dbconnection=db, vaultconnection=vault, log=log))


    logging.getLogger('mlaps').info("Server initialized")

    if devmode:
        app.run(host="0.0.0.0", debug=True, port=8080)  # to allow for debugging and auto-reload
    else:
        d = PathInfoDispatcher({'/': app})
        server = WSGIServer(('0.0.0.0', 8080), d)
        try:
            server.start()
        except KeyboardInterrupt:
            server.stop()
    #app.run(host="localhost", debug=True, port=8050,ssl_context=('web.crt', 'web.key'))  # to allow for debugging and auto-reload

