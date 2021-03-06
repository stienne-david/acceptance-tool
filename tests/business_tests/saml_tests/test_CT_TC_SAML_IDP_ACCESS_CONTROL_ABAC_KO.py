#!/usr/bin/env python

# Copyright (C) 2018:
#     Sonia Bogos, sonia.bogos@elca.ch
#
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

import helpers.requests as req
from http import HTTPStatus

from bs4 import BeautifulSoup
from requests import Request, Session

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
logger = logging.getLogger('acceptance-tool.tests.business_tests.test_CT_TC_SAML_IDP_ACCESS_CONTROL_ABAC_KO')
logger.setLevel(logging.DEBUG)


@pytest.mark.usefixtures('settings', 'import_realm')
class Test_test_CT_TC_SAML_IDP_ACCESS_CONTROL_ABAC_KO():
    """
    Class to test the test_CT_TC_SAML_IDP_ACCESS_CONTROL_ABAC_KO use case:
    As a resource owner, I need the solution to prevent end users switching between applications in a timeframe smaller
     than the allowed single sign on time span, to access applications they are not entitled to access.
    """

    def test_CT_TC_SAML_IDP_ACCESS_CONTROL_ABAC_KO_SP_initiated(self, settings):
        """
        Scenario: User logs in to SP1 where he has the appropriate attribute.
        Same user tries to access to SP2, SP that he is not authorized to access. He should receive an
        error message saying he has not the authorization.
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

        # Service provider 2 settings
        sp2 = settings["sps_saml"][3]
        sp2_ip = sp2["ip"]
        sp2_port = sp2["port"]
        sp2_scheme = sp2["http_scheme"]
        sp2_path = sp2["path"]
        sp2_message = settings["idp"]["not_authorized_message"]

        # Identity provider settings
        idp_ip = settings["idp"]["ip"]
        idp_port = settings["idp"]["port"]
        idp_scheme = settings["idp"]["http_scheme"]

        idp_username = settings["idp"]["test_realm"]["username"]
        idp_password = settings["idp"]["test_realm"]["password"]

        keycloak_login_form_id = settings["idp"]["login_form_id"]

        # Common header for all the requests
        header = req.get_header()

        # Perform login to SP1
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

        response = req.send_credentials_to_idp(logger, s, header, idp_ip, idp_port, redirect_url, url_form, credentials_data,
                                               keycloak_cookie, method_form)

        assert response.status_code == HTTPStatus.OK or response.status_code == HTTPStatus.FOUND
        #or response.status_code == 303 or response.status_code == 307

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

        (response, sp_cookie) = req.access_sp_with_token(logger, s, header, sp_ip, sp_port, sp_scheme, idp_scheme, idp_ip,
                                                         idp_port, method_form, url_form, token, session_cookie,
                                                         keycloak_cookie_2, )

        assert response.status_code == HTTPStatus.OK

        # assert that we are logged in
        assert re.search(sp_message, response.text) is not None

        # User is logged in on SP1

        # Attempt to perform login on SP2

        (session_cookie, response) = req.access_sp_saml(logger, s, header, sp2_ip, sp2_port, sp2_scheme, sp2_path, idp_ip,
                                                        idp_port)

        session_cookie2 = response.cookies

        redirect_url = response.headers['Location']

        header_redirect_idp = {
            **header,
            'Host': "{ip}:{port}".format(ip=idp_ip, port=idp_port),
            'Referer': "{ip}:{port}".format(ip=sp2_ip, port=sp2_port)
        }

        response = req.redirect_to_idp(logger, s, redirect_url, header_redirect_idp, {**session_cookie2, **keycloak_cookie_2})

        # Assert that the client is not authorized to access SP2
        assert response.status_code == HTTPStatus.FORBIDDEN

        assert re.search(sp2_message, response.text) is not None


    def test_CT_TC_SAML_IDP_ACCESS_CONTROL_ABAC_KO_IDP_initiated(self, settings):
        """
        Scenario: User logs in to the IDP. He then accesses SP1 where he has the appropriate attribute.
        Same user tries to access SP2, that he is not authorized to access. He should receive an
        error message saying he has not the authorization.
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

        # Service provider 2 settings
        sp2 = settings["sps_saml"][3]
        sp2_ip = sp2["ip"]
        sp2_port = sp2["port"]
        sp2_scheme = sp2["http_scheme"]
        sp2_path = sp2["path"]
        sp2_message = settings["idp"]["not_authorized_message"]

        # Identity provider settings
        idp_ip = settings["idp"]["ip"]
        idp_port = settings["idp"]["port"]
        idp_scheme = settings["idp"]["http_scheme"]
        idp_message = settings["idp"]["logged_in_message"]
        idp_test_realm = settings["idp"]["test_realm"]["name"]
        idp_path = "auth/realms/{realm}/account".format(realm=idp_test_realm)

        idp_username = settings["idp"]["test_realm"]["username"]
        idp_password = settings["idp"]["test_realm"]["password"]

        # Common header for all the requests
        header = req.get_header()

        # Perform login to IDP
        (oath_cookie, keycloak_cookie, keycloak_cookie2, response) = req.login_idp(logger, s, header, idp_ip,
                                                                                   idp_port, idp_scheme,
                                                                                   idp_path, idp_username,
                                                                                   idp_password)

        assert response.status_code == HTTPStatus.OK

        # Assert we are logged in to IDP
        assert re.search(idp_message, response.text) is not None

        # Access SP1
        (session_cookie, response) = req.access_sp_saml(logger, s, header, sp_ip, sp_port, sp_scheme, sp_path,
                                                        idp_ip, idp_port)

        # store the cookie received from keycloak
        keycloak_cookie3 = response.cookies

        assert response.status_code == HTTPStatus.FOUND

        redirect_url = response.headers['Location']

        header_redirect_idp = {
            **header,
            'Host': "{ip}:{port}".format(ip=idp_ip, port=idp_port),
            'Referer': "{ip}:{port}".format(ip=sp_ip, port=sp_port)
        }

        response = req.redirect_to_idp(logger, s, redirect_url, header_redirect_idp,
                                       {**keycloak_cookie3, **keycloak_cookie2})

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

        (response, sp_cookie) = req.access_sp_with_token(logger, s, header, sp_ip, sp_port, sp_scheme, idp_scheme, idp_ip,
                                                         idp_port, method_form, url_form, token, session_cookie,
                                                         keycloak_cookie2)

        assert response.status_code == HTTPStatus.OK

        assert re.search(sp_message, response.text) is not None

        # User can access SP1

        # Attempt to access SP2

        (session_cookie, response) = req.access_sp_saml(logger, s, header, sp2_ip, sp2_port, sp2_scheme, sp2_path,
                                                        idp_ip,
                                                        idp_port)

        session_cookie2 = response.cookies

        redirect_url = response.headers['Location']

        header_redirect_idp = {
            **header,
            'Host': "{ip}:{port}".format(ip=idp_ip, port=idp_port),
            'Referer': "{ip}:{port}".format(ip=sp2_ip, port=sp2_port)
        }

        response = req.redirect_to_idp(logger, s, redirect_url, header_redirect_idp,
                                       {**session_cookie2, **keycloak_cookie2})

        # Assert that the client is not authorized to access SP2
        assert response.status_code == HTTPStatus.FORBIDDEN

        assert re.search(sp2_message, response.text) is not None

