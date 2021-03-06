#!/usr/bin/env python

# Copyright (C) 2018:
#     Sonia Bogos, sonia.bogos@elca.ch
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.
#

import pytest
import logging
import re
import base64

import helpers.requests as req
from helpers.logging import log_request

from bs4 import BeautifulSoup
from requests import Request, Session
from http import HTTPStatus

author = "Sonia Bogos"
maintainer = "Sonia Bogos"
version = "0.0.1"

# Logging
# Default to Debug
##################

logging.basicConfig(
    format='%(asctime)s %(name)s %(levelname)s %(message)s',
    datefmt='%m/%d/%Y %I:%M:%S %p'
)
logger = logging.getLogger('acceptance-tool.tests.business_tests.test_CT_TC_SAML_IDP_CLAIM_AUG')
logger.setLevel(logging.DEBUG)


@pytest.mark.usefixtures('settings', 'import_realm')
class Test_CT_TC_SAML_IDP_CLAIM_AUG():
    """
   Class to test the CT_TC_SAML_IDP_CLAIM_AUG use case:
   As a user I need CloudTrust to add additional information to my access token when I access applications.
   In these tests, IP at the time of authentication and claims from external applications are checked.
    """

    def test_CT_TC_SAML_SSO_FORM_SIMPLE_SP_initiated(self, settings):
        """
        Test the CT_TC_SAML_SSO_FORM_SIMPLE use case with the SP-initiated flow, i.e. the user accesses the application
        , which is a service provider (SP), that redirects him to the keycloak, the identity provider (IDP).
        The user has to login to keycloak which will give him the SAML token. The token will give him access to the
        application. The token contains builtin and external claims.
        :param settings:
        :return:
        """

        s = Session()

        # Service provider settings
        sp = settings["sps_saml"][0]
        sp_ip = sp["ip"]
        sp_port = sp["port"]
        sp_scheme = sp["http_scheme"]
        sp_path = sp["path"]
        sp_message = sp["logged_in_message"]

        # Identity provider settings
        idp_ip = settings["idp"]["ip"]
        idp_port = settings["idp"]["port"]
        idp_scheme = settings["idp"]["http_scheme"]

        idp_username = settings["idp"]["test_realm"]["username"]
        idp_password = settings["idp"]["test_realm"]["password"]
        idp_attr_name = settings["idp"]["test_realm"]["attr_name"]
        idp_attr_name_external = settings["idp"]["test_realm"]["external_attr_name"]
        idp_attr_tag = settings["idp"]["test_realm"]["attr_xml_elem"]

        keycloak_login_form_id = settings["idp"]["login_form_id"]

        # Common header for all the requests
        header = req.get_header()

        (session_cookie, response) = req.access_sp_saml(logger, s, header, sp_ip, sp_port, sp_scheme, sp_path,
                                                                        idp_ip, idp_port)

        assert response.status_code == HTTPStatus.FOUND

        # store the cookie received from keycloak
        keycloak_cookie = response.cookies

        redirect_url = response.headers['Location']

        header_redirect_idp = {
            **header,
            'Host': "{ip}:{port}".format(ip=idp_ip, port=idp_port),
            'Referer': "{ip}:{port}".format(ip=sp_ip, port=sp_port)
        }

        response = req.redirect_to_idp(logger, s, redirect_url, header_redirect_idp, keycloak_cookie)

        soup = BeautifulSoup(response.content, 'html.parser')

        form = soup.find("form", {"id": keycloak_login_form_id})

        assert form is not None

        url_form = form.get('action')
        method_form = form.get('method')

        inputs = form.find_all('input')

        input_name = []
        for input in inputs:
                input_name.append(input.get('name'))

        assert "username" in input_name
        assert "password" in input_name

        # Simulate the login to the identity provider by providing the credentials
        credentials_data = {}
        credentials_data["username"] = idp_username
        credentials_data["password"] = idp_password

        response = req.send_credentials_to_idp(logger, s, header, idp_ip, idp_port, redirect_url, url_form, credentials_data, keycloak_cookie, method_form)

        assert response.status_code == HTTPStatus.OK or response.status_code == HTTPStatus.FOUND #or response.status_code == 303 or response.status_code == 307

        keycloak_cookie_2 = response.cookies

        soup = BeautifulSoup(response.content, 'html.parser')
        form = soup.body.form

        url_form = form.get('action')
        inputs = form.find_all('input')
        method_form = form.get('method')

        # Get the token (SAML response) from the identity provider
        token = {}
        for input in inputs:
            token[input.get('name')] = input.get('value')

        decoded_token = base64.b64decode(token['SAMLResponse']).decode("utf-8")

        val = idp_attr_tag + "=\"{v}\"".format(v=idp_attr_name)
        # assert that the IDP added the location attribute in the token
        assert re.search(val, decoded_token) is not None

        # assert that the external claim is also in the token
        val = idp_attr_tag + "=\"{v}\"".format(v=idp_attr_name_external)
        assert re.search(val, decoded_token) is not None


        (response, sp_cookie) = req.access_sp_with_token(logger, s, header, sp_ip, sp_port, sp_scheme, idp_scheme,
                                                         idp_ip, idp_port, method_form, url_form, token, session_cookie,
                                                         keycloak_cookie_2)

        assert response.status_code == HTTPStatus.OK

        # assert that we are logged in
        assert re.search(sp_message, response.text) is not None

    def test_CT_TC_SAML_SSO_FORM_SIMPLE_IDP_initiated(self, settings):
        """
        Test the CT_TC_SAML_SSO_FORM_SIMPLE use case with the IDP-initiated flow, i.e. the user logs in keycloak,
        the identity provider (IDP), and then accesses the application, which is a service provider (SP).
        The application redirect towards keycloak to obtain the SAML token.
        The token contains builtin and external claims.
        :param settings:
        :return:
        """

        s = Session()

        # Service provider settings
        sp = settings["sps_saml"][0]
        sp_ip = sp["ip"]
        sp_port = sp["port"]
        sp_scheme = sp["http_scheme"]
        sp_path = sp["path"]
        sp_message = sp["logged_in_message"]

        # Identity provider settings
        idp_ip = settings["idp"]["ip"]
        idp_port = settings["idp"]["port"]
        idp_scheme = settings["idp"]["http_scheme"]
        idp_test_realm = settings["idp"]["test_realm"]["name"]
        idp_path = "auth/realms/{realm}/account".format(realm=idp_test_realm)
        idp_message = settings["idp"]["logged_in_message"]

        idp_username = settings["idp"]["test_realm"]["username"]
        idp_password = settings["idp"]["test_realm"]["password"]
        idp_attr_name = settings["idp"]["test_realm"]["attr_name"]
        idp_attr_tag = settings["idp"]["test_realm"]["attr_xml_elem"]
        idp_attr_name_external = settings["idp"]["test_realm"]["external_attr_name"]

        # Common header for all the requests
        header = req.get_header()

        (oath_cookie, keycloak_cookie, keycloak_cookie2, response) = req.login_idp(logger, s, header, idp_ip, idp_port, idp_scheme,
                                                                                idp_path, idp_username, idp_password)

        assert response.status_code == HTTPStatus.OK

        # Assert we are logged in
        assert re.search(idp_message, response.text) is not None

        (session_cookie, response) = req.access_sp_saml(logger, s, header, sp_ip, sp_port, sp_scheme, sp_path, idp_ip, idp_port)

        # store the cookie received from keycloak
        keycloak_cookie3 = response.cookies

        assert response.status_code == HTTPStatus.FOUND

        redirect_url = response.headers['Location']

        header_redirect_idp = {
            **header,
            'Host': "{ip}:{port}".format(ip=idp_ip, port=idp_port),
            'Referer': "{ip}:{port}".format(ip=sp_ip, port=sp_port)
        }

        response = req.redirect_to_idp(logger, s, redirect_url, header_redirect_idp, {**keycloak_cookie3, **keycloak_cookie2})

        assert response.status_code == HTTPStatus.OK

        soup = BeautifulSoup(response.content, 'html.parser')
        form = soup.body.form

        url_form = form.get('action')
        inputs = form.find_all('input')
        method_form = form.get('method')

        # Get the token (SAML response) from the identity provider
        token = {}
        for input in inputs:
            token[input.get('name')] = input.get('value')

        decoded_token = base64.b64decode(token['SAMLResponse']).decode("utf-8")

        val = idp_attr_tag + "=\"{v}\"".format(v=idp_attr_name)
        # assert that the IDP added the location attribute in the token
        assert re.search(val, decoded_token) is not None

        # assert that the external claim is also in the token
        val = idp_attr_tag + "=\"{v}\"".format(v=idp_attr_name_external)
        assert re.search(val, decoded_token) is not None

        (response, sp_cookie) = req.access_sp_with_token(logger, s, header, sp_ip, sp_port, sp_scheme, idp_scheme,
                                                         idp_ip, idp_port, method_form, url_form, token, session_cookie,
                                                         keycloak_cookie2)

        assert response.status_code == HTTPStatus.OK

        assert re.search(sp_message, response.text) is not None

    def test_CT_TC_SAML_SSO_FORM_SIMPLE_IDP_initiated_keycloak_endpoint(self, settings):
        """
        Test the CT_TC_SAML_SSO_FORM_SIMPLE use case with the IDP-initiated flow, where we set up an endpoint
        on Keycloak with IDP Initiated SSO URL Name.
        Thus, the user accesses
        http[s]://host:port/auth/realms/{RealmName}/protocol/saml/clients/{IDP Initiated SSO URL Name}
        to authenticate to Keycloak and obtain the token (SAML response) and gets redirected
        to the SP that he can access.
        :param settings:
        :return:
        """

        s = Session()

        # Service provider settings
        sp = settings["sps_saml"][0]
        sp_ip = sp["ip"]
        sp_port = sp["port"]
        sp_scheme = sp["http_scheme"]
        sp_path = sp["path"]
        sp_message = sp["logged_in_message"]
        sp_sso_url_name = sp["sso_url_name"]

        # Identity provider settings
        idp_ip = settings["idp"]["ip"]
        idp_port = settings["idp"]["port"]
        idp_scheme = settings["idp"]["http_scheme"]
        idp_test_realm = settings["idp"]["test_realm"]["name"]
        idp_login_endpoint = "auth/realms/{realm}/protocol/saml/clients/{name}".format(realm=idp_test_realm, name=sp_sso_url_name)

        idp_username = settings["idp"]["test_realm"]["username"]
        idp_password = settings["idp"]["test_realm"]["password"]
        idp_attr_name = settings["idp"]["test_realm"]["attr_name"]
        idp_attr_tag = settings["idp"]["test_realm"]["attr_xml_elem"]
        idp_attr_name_external = settings["idp"]["test_realm"]["external_attr_name"]

        keycloak_login_form_id = settings["idp"]["login_form_id"]

        # Common header for all the requests
        header = req.get_header()

        # Idp endpoint for client
        url_endpoint= "{scheme}://{ip}:{port}/{path}".format(scheme=idp_scheme, ip=idp_ip, port=idp_port, path=idp_login_endpoint)

        req_access_idp_endpoint = Request(
            method='GET',
            url=url_endpoint,
            headers=header,
        )

        prepared_request = req_access_idp_endpoint.prepare()

        log_request(logger, req_access_idp_endpoint)

        response = s.send(prepared_request, verify=False, allow_redirects=False)

        logger.debug(response.status_code)

        keycloak_cookie = response.cookies

        soup = BeautifulSoup(response.content, 'html.parser')

        form = soup.find("form", {"id": keycloak_login_form_id})

        assert form is not None

        url_form = form.get('action')
        method_form = form.get('method')

        inputs = form.find_all('input')

        input_name = []
        for input in inputs:
            input_name.append(input.get('name'))

        assert "username" in input_name
        assert "password" in input_name

        # Provide the credentials
        credentials_data = {}
        credentials_data["username"] = idp_username
        credentials_data["password"] = idp_password

        response = req.send_credentials_to_idp(logger, s, header, idp_ip, idp_port, url_endpoint, url_form,
                                               credentials_data, keycloak_cookie, method_form)

        assert response.status_code == HTTPStatus.OK or response.status_code == HTTPStatus.FOUND

        keycloak_cookie_2 = response.cookies

        soup = BeautifulSoup(response.content, 'html.parser')
        form = soup.body.form

        url_form = form.get('action')
        inputs = form.find_all('input')
        method_form = form.get('method')

        # Get the token (SAML response) from the identity provider
        token = {}
        for input in inputs:
            token[input.get('name')] = input.get('value')

        decoded_token = base64.b64decode(token['SAMLResponse']).decode("utf-8")

        val = idp_attr_tag + "=\"{v}\"".format(v=idp_attr_name)
        # assert that the IDP added the location attribute in the token
        assert re.search(val, decoded_token) is not None

        # assert that the external claim is also in the token
        val = idp_attr_tag + "=\"{v}\"".format(v=idp_attr_name_external)
        assert re.search(val, decoded_token) is not None

        (response, sp_cookie) = req.access_sp_with_token(logger, s, header, sp_ip, sp_port, sp_scheme, idp_scheme,
                                                         idp_ip, idp_port, method_form, url_form, token,
                                                         keycloak_cookie_2, keycloak_cookie_2)

        assert response.status_code == HTTPStatus.OK

        #  Access the secure page of the SP
        header_sp_page = {
            **header,
            'Host': "{ip}:{port}".format(ip=sp_ip, port=sp_port),
            'Referer': "{ip}:{port}".format(ip=sp_ip, port=sp_port)
        }

        req_get_sp_page = Request(
            method='GET',
            url="{scheme}://{ip}:{port}/{path}".format(
                scheme=sp_scheme,
                port=sp_port,
                ip=sp_ip,
                path=sp_path
            ),
            headers=header_sp_page,
            cookies=sp_cookie
        )

        prepared_request = req_get_sp_page.prepare()

        log_request(logger, req_get_sp_page)

        response = s.send(prepared_request, verify=False)

        logger.debug(response.status_code)

        assert response.status_code == HTTPStatus.OK

        assert re.search(sp_message, response.text) is not None

