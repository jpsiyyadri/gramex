from __future__ import unicode_literals
import os
import json
import requests
import lxml.html
import pandas as pd
import sqlalchemy as sa
from nose.plugins.skip import SkipTest
from six.moves.http_client import OK, UNAUTHORIZED
import gramex.config
from . import TestGramex
from . import server


class TestSession(TestGramex):
    @classmethod
    def setupClass(cls):
        cls.session1 = requests.Session()
        cls.session2 = requests.Session()
        cls.url = server.base_url + '/auth/session'

    def test_session(self):
        r1 = self.session1.get(self.url + '?var=x')
        self.assertIn('sid', r1.cookies)
        self.data1 = json.loads(r1.text)
        self.assertIn('id', self.data1)
        self.assertEqual(self.data1['var'], 'x')

        r2 = self.session2.get(self.url)
        self.assertIn('sid', r2.cookies)
        self.data2 = json.loads(r2.text)
        self.assertIn('id', self.data2)
        self.assertNotIn('var', self.data2)

        self.assertNotEqual(r1.cookies['sid'], r2.cookies['sid'])
        self.assertNotEqual(self.data1['id'], self.data2['id'])

        # Test persistence under graceful shutdown
        server.stop_gramex()
        server.start_gramex()
        r1 = self.session1.get(self.url)
        self.assertEqual(self.data1, json.loads(r1.text))
        self.assertEqual(self.data1['var'], 'x')
        r2 = self.session2.get(self.url)
        self.assertEqual(self.data2, json.loads(r2.text))


class TestDBAuth(TestGramex):

    @classmethod
    def setUpClass(cls):
        folder = os.path.dirname(os.path.abspath(__file__))
        cls.data = pd.read_csv(os.path.join(folder, 'userdata.csv'), encoding='cp1252')
        cls.dburl = 'mysql+pymysql://root@%s/' % gramex.config.variables.MYSQL_SERVER
        # sqlalchemy needs encoding to be a `str` in both Python 2.x and 3.x
        encoding = str('utf-8')
        cls.engine = sa.create_engine(cls.dburl, encoding=encoding)
        try:
            cls.engine.execute('DROP DATABASE IF EXISTS test_auth')
            cls.engine.execute('CREATE DATABASE test_auth')
            cls.engine.dispose()
            cls.engine = sa.create_engine(cls.dburl + 'test_auth', encoding=encoding)
            cls.data.to_sql('users', con=cls.engine, index=False)
        except sa.exc.OperationalError:
            raise SkipTest('Unable to connect to %s' % cls.dburl)

        cls.session = requests.Session()
        cls.url = server.base_url + '/auth/db'

    def post(self, user, password, query_next=None, header_next=None):
        # Get the login page
        params, headers = {}, {}
        if query_next is not None:
            params['next'] = query_next
        if header_next is not None:
            headers['NEXT'] = header_next
        r = self.session.get(self.url, params=params, headers=headers)
        tree = lxml.html.fromstring(r.text)
        self.assertEqual(tree.xpath('.//h1')[0].text, 'DBAuth')

        # Create form submission data
        data = {'user': user, 'password': password}
        data['xsrf'] = tree.xpath('.//input[@name="_xsrf"]')[0].get('value')

        # Submitting the correct password redirects
        return self.session.post(self.url, timeout=10, data=data, headers=headers)

    def ok(self, *args, **kwargs):
        check_next = kwargs.pop('check_next')
        r = self.post(*args, **kwargs)
        self.assertEqual(r.status_code, OK)
        self.assertNotRegexpMatches(r.text, 'error code')
        self.assertEqual(r.url, server.base_url + check_next)

    def unauthorized(self, *args, **kwargs):
        r = self.post(*args, **kwargs)
        self.assertEqual(r.status_code, UNAUTHORIZED)
        self.assertRegexpMatches(r.text, 'error code')
        self.assertEqual(r.url, self.url)

    def test_login(self):
        self.ok('alpha', 'alpha', check_next='/dir/index/')
        self.ok('beta', 'beta', check_next='/dir/index/')

    def test_login_wrong_password(self):
        self.unauthorized('alpha', 'beta')

    def test_login_nonexistent_user(self):
        self.unauthorized('nonexistent', 'beta')

    def test_redirect(self):
        self.ok('alpha', 'alpha', query_next='/func/args', check_next='/func/args')
        self.ok('alpha', 'alpha', header_next='/func/args', check_next='/func/args')