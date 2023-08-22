from typing import Union

import hvac, base64, logging
from os import environ as env

class HSMClient():
    # tracks the uses of the current hsm token, to know when to renew it
    uses = 0
    # keeps track of the current status to the vault without using a token usage everything checking
    isAuthenticated = False

    def checkConnection(self) -> Union[bool, str]:
        if not self.isAuthenticated: return "Not initialized/Failed to initialize hsmclient"
        self.uses += 2
        sealStatus = bool(self.__hsmClient.seal_status['sealed'])
        authenticationStatus = self.__hsmClient.is_authenticated()
        logging.getLogger('mlaps').debug(f"Connection to Vault is authenticated: {authenticationStatus}, Vault is sealed: {sealStatus}")
        self.isAuthenticated = authenticationStatus
        return True

    def __init__(self, host, role_id, secret_id):
        try:
            # try to initialize the hsm connection with the given credentials
            self.isAuthenticated = self.__hsmlogin(host, role_id, secret_id)
        except Exception as e:
            logging.getLogger('mlaps').error(str(e))

    def __hsmlogin(self,url,role,secret):
        # calls the hsm library to login
        self.__hsmClient = hvac.Client(url="http://{}:8200/".format(url))
        # pass the credentials to the approle login endpoint
        self.__hsmClient.auth.approle.login(
                role_id=role,
                secret_id=secret,
                )
        # check if the credentials worked
        if self.__hsmClient.is_authenticated():
            logging.getLogger('mlaps').debug("Successfully authenticated to Vault")
            return True
        else:
            raise Exception('error, could not authenticate')

    """
    Sends the given password to the hsm for encryption and returns the entire response
    parameters:
        plaintext: plain plaintext password as utf-8 string, not base64 encoded
    """
    def hsm_enc(self, plaintext: str):
        try:
            # base64 encode the given password, hsm expects the text to be encoded
            encod_pw = str(base64.b64encode(bytes(plaintext,"utf-8")),"utf-8")
            logging.getLogger('mlaps').debug(encod_pw)
            # increment the hsm token usage, even if it fails it counts as a request
            self.uses += 1
            # actually send the request to encrypt to the hsm
            cipher = self.__hsmClient.secrets.transit.encrypt_data(
                name = 'client-passwords',
                plaintext = encod_pw,
            )
            logging.getLogger('mlaps').debug(cipher)
            # return the entire response
            return cipher
        except Exception as e:
            logging.getLogger('mlaps').error(str(e))
        return False

    """
    Sends the given password to the hsm for decryption and returns the entire response
    parameters:
        cipher: encrypted password as utf-8 string in hsm format, not base64 encoded
    """
    def hsm_dec(self, cipher):
        try:
            # increment the hsm token usage, even if it fails it counts as a request
            self.uses += 1
            # actually send the request to decrypt to the hsm
            plain = self.__hsmClient.secrets.transit.decrypt_data(
                name = 'client-passwords',
                ciphertext = cipher,
            )
            logging.getLogger('mlaps').debug(plain)
            # return the entire response
            return plain
        except Exception as e:
            logging.getLogger('mlaps').error(str(e))
        return False
    """
    Sends the given csr to the hsm for signing with the given common_name to be set as the cn
    """
    def hsm_sign_csr(self,csr, common_name):
        try:
            # increment the hsm token usage, even if it fails it counts as a request
            self.uses += 1
            # send the actual request to the hsm with the common_name set
            signed_cert = self.__hsmClient.secrets.pki.sign_certificate(
                name='mlaps',
                csr=csr,
                common_name=common_name
            )
            logging.getLogger('mlaps').debug(signed_cert)
            # return the entire response
            return signed_cert
        except Exception as e:
            logging.getLogger('mlaps').error(str(e))
        return False

    """
    Sends a request for a new secret id to the hsm and returns the entire response
    """
    def hsm_get_new_secret(self):
        try:
            # increment the hsm token usage, even if it fails it counts as a request
            self.uses += 1
            # send the actual request to the hsm
            resp = self.__hsmClient.auth.approle.generate_secret_id(
                role_name='client-passwords',
            )
            logging.getLogger('mlaps').debug(resp)
            # return the entire response
            return resp
        except Exception as e:
            logging.getLogger('mlaps').error(str(e))
        return False


