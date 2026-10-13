import base64
import datetime
import hashlib
import hmac

import requests

DEFAULT_TIMEOUT = 30


class Client:
    def __init__(self, baseUrl, apiKey, apiSecret):
        self.baseUrl = baseUrl
        self.apiKey = apiKey
        self.apiSecret = apiSecret

    @classmethod
    def from_env(cls, env):
        """Build a client from the values configured in Settings > Selcom."""
        icp = env["ir.config_parameter"].sudo()
        return cls(
            baseUrl=(icp.get_param("web_selcom_integration.base_url") or "").rstrip("/"),
            apiKey=icp.get_param("web_selcom_integration.api_key") or "",
            apiSecret=icp.get_param("web_selcom_integration.api_secret") or "",
        )

    def computeHeader(self, dictData):
        apiKey_bytes = self.apiKey.encode('ascii')
        base64_bytes = base64.b64encode(apiKey_bytes)
        base64_apiKey = base64_bytes.decode('ascii')
        authToken = 'SELCOM ' + base64_apiKey

        now = datetime.datetime.now().astimezone()
        timestamp = now.strftime("%Y-%m-%dT%H:%M:%S%z")

        signedFields = ""
        data = "timestamp=" + timestamp
        for key in dictData:
            data = data + "&" + key + "=" + str(dictData[key])
            if signedFields == '':
                signedFields = signedFields + key
            else:
                signedFields = signedFields + "," + key

        signature = hmac.new(
            key=bytes(str(self.apiSecret), 'utf-8'),
            msg=bytes(data, 'utf-8'),
            digestmod=hashlib.sha256).digest()
        digestBytes = base64.b64encode(signature)
        digest = digestBytes.decode('utf-8')

        return authToken, timestamp, digest, signedFields

    def _headers(self, dictData):
        authToken, timestamp, digest, signedFields = self.computeHeader(dictData)
        return {
            "Content-type": "application/json",
            "Authorization": authToken,
            "Digest-Method": "HS256",
            "Digest": digest,
            "Timestamp": timestamp,
            "Signed-Fields": signedFields,
        }

    def postFunc(self, path, dictData):
        response = requests.post(
            self.baseUrl + path, json=dictData,
            headers=self._headers(dictData), timeout=DEFAULT_TIMEOUT)
        return response.json()

    def getFunc(self, path, dictData):
        response = requests.get(
            self.baseUrl + path, params=dictData,
            headers=self._headers(dictData), timeout=DEFAULT_TIMEOUT)
        return response.json()

    def deleteFunc(self, path, dictData):
        response = requests.delete(
            self.baseUrl + path, params=dictData,
            headers=self._headers(dictData), timeout=DEFAULT_TIMEOUT)
        return response.json()
