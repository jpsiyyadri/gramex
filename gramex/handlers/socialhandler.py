import os
import six
import json
import gramex
import tornado.gen
from oauthlib import oauth1
from orderedattrdict import AttrDict
from tornado.web import HTTPError
from tornado.auth import TwitterMixin, FacebookGraphMixin
from tornado.httputil import url_concat, responses
from .basehandler import BaseHandler
from gramex.http import OK, BAD_REQUEST, CLIENT_TIMEOUT

custom_responses = {
    CLIENT_TIMEOUT: 'Client Timeout'
}
store_cache = {}


class SocialMixin(object):
    @classmethod
    def setup_social(cls, user_info, transform={}, methods=['get', 'post'], **kwargs):
        # Session key that stores the user info
        cls.user_info = user_info

        # Set up methods
        if not isinstance(methods, list):
            methods = [methods]
        methods = set(method.lower().strip() for method in methods)
        for method in ('get', 'post', 'put', 'patch'):
            if method in methods:
                setattr(cls, method, cls.run)

    @tornado.gen.coroutine
    def social_response(self, response):
        # Set response headers
        if response.code in responses:
            self.set_status(response.code)
        else:
            self.set_status(response.code, custom_responses.get(response.code))
        for header, header_value in response.headers.items():
            # We're OK with anything that starts with X-
            # Also set MIME type and last modified date
            if header.startswith('X-') or header in {'Content-Type', 'Last-Modified'}:
                self.set_header(header, header_value)

        # Set user's headers
        for header, header_value in self.conf.kwargs.get('headers', {}).items():
            self.set_header(header, header_value)

        # Transform content
        content = response.body
        if content and response.code == OK:
            content = yield gramex.service.threadpool.submit(self.run_transforms, content=content)
        # Convert to JSON if required
        if not isinstance(content, (six.binary_type, six.text_type)):
            content = json.dumps(content, ensure_ascii=True, separators=(',', ':'))
        raise tornado.gen.Return(content)

    def run_transforms(self, content):
        result = json.loads(content.decode('utf-8'))
        for name, transform in self.transform.items():
            for value in transform['function'](result):
                result = value
            for header, header_value in transform.get('headers', {}).items():
                self.set_header(header, header_value)
        return result

    def write_error(self, status_code, **kwargs):
        '''Write error responses in JSON'''
        self.set_header('Content-Type', 'application/json; charset=UTF-8')
        self.finish(json.dumps({'errors': [{
            'code': status_code,
            'message': self._reason,
        }]}))

    def _get_store_key(self):
        '''
        Allows social mixins to store information in a single global JSONStore.
        Keys are "$YAMLPATH: url-key". Any value may be stored against it.
        '''
        if 'store' not in store_cache:
            store_path = os.path.join(gramex.config.variables['GRAMEXDATA'], 'socialstore.json')
            store_cache['store'] = gramex.handlers.basehandler.JSONStore(store_path, flush=60)
        base_key = '{}: {}'.format(os.getcwd(), self.name)
        return store_cache['store'], base_key

    def read_store(self):
        '''
        Read from this URL handler's social store. Typically returns a dict
        '''
        cache, key = self._get_store_key()
        return cache.load(key, {})

    def write_store(self, value):
        '''
        Write to this URL handler's social store. Typically stores a dict
        '''
        cache, key = self._get_store_key()
        cache.dump(key, value)

    def get_token(self, key, fetch=lambda info, key, val: info.get(key, val)):
        '''
        Returns an access token / key / secret with the following priority:

        1. If YAML config specifies "persist" for the token, get it from the last
           stored value. If none is stored, save and use the current session's
           token
        2. If YAML config specifies a token, use it
        3. If YAML config does NOT specify a token, use current sessions' token

        If after all of this, we don't have a token, raise an exception.
        '''
        info = self.session.get(self.user_info, {})
        token = self.conf.kwargs.get(key, None)         # Get from config
        session_token = fetch(info, key, None)
        if token == 'persist':
            token = self.read_store().get(key, None)    # If persist, use store
            if token is None and session_token:         # Or persist from session
                self.write_store(info)
        if token is None:
            token = session_token                       # Use session token
        if token is None:                               # Ensure token is present
            raise HTTPError(BAD_REQUEST, reason='token %s missing' % key)
        return token


class TwitterRESTHandler(SocialMixin, BaseHandler, TwitterMixin):
    '''
    Proxy for the Twitter 1.1 REST API via these ``kwargs``::

        pattern: /twitter/(.*)
        handler: TwitterRESTHandler
        kwargs:
            key: your-consumer-key
            secret: your-consumer-secret
            access_key: your-access-key         # Optional -- picked up from session
            access_secret: your-access-token    # Optional -- picked up from session
            methods: [get, post]                # HTTP methods to use for the API
            path: /search/tweets.json           # Freeze Twitter API request

    Now ``POST /twitter/search/tweets.json?q=gramener`` returns the same response
    as the Twitter REST API ``/search/tweets.json``.

    If you only want to expose a specific API, specify a ``path:``. It overrides
    the URL path. The query parameters will still work.

    By default, ``methods`` is POST, and GET logs the user in, storing the access
    token in the session for future use. But you can specify the ``access_...``
    values and set ``methods`` to ``[get, post]`` to use both GET and POST
    requests to proxy the API.
    '''
    @staticmethod
    def get_from_token(info, key, val):
        return info.get('access_token', {}).get(key.replace('access_', ''), val)

    @classmethod
    def setup(cls, **kwargs):
        super(TwitterRESTHandler, cls).setup(**kwargs)
        cls.setup_social('user.twitter', **kwargs)

    @tornado.gen.coroutine
    def run(self, path=None):
        path = self.conf.kwargs.get('path', path)
        if not path and self.request.method == 'GET':
            yield self.login()
            raise tornado.gen.Return()

        args = {key: self.get_argument(key) for key in self.request.arguments}
        params = AttrDict(self.conf.kwargs)
        params['access_key'] = self.get_token('access_key', self.get_from_token)
        params['access_secret'] = self.get_token('access_secret', self.get_from_token)

        client = oauth1.Client(
            client_key=params['key'],
            client_secret=params['secret'],
            resource_owner_key=params['access_key'],
            resource_owner_secret=params['access_secret'])
        endpoint = params.get('endpoint', 'https://api.twitter.com/1.1/')
        path = params.get('path', path)
        uri, headers, body = client.sign(url_concat(endpoint + path, args))
        http = self.get_auth_http_client()
        response = yield http.fetch(uri, headers=headers, raise_error=False)
        result = yield self.social_response(response)
        self.set_header('Content-Type', 'application/json; charset=UTF-8')
        self.write(result)

    @tornado.gen.coroutine
    def login(self):
        if self.get_argument('oauth_token', None):
            info = self.session[self.user_info] = yield self.get_authenticated_user()
            if (any(self.conf.kwargs.get(key, None) == 'persist'
                    for key in ('access_key', 'access_secret'))):
                self.write_store(info)
            self.redirect_next()
        else:
            self.save_redirect_page()
            yield self.authorize_redirect(callback_uri=self.request.protocol + "://" +
                                          self.request.host + self.request.uri)

    def _oauth_consumer_token(self):
        return dict(key=self.conf.kwargs['key'],
                    secret=self.conf.kwargs['secret'])


class FacebookGraphHandler(SocialMixin, BaseHandler, FacebookGraphMixin):
    '''
    Proxy for the Facebook Graph API via these ``kwargs``::

        pattern: /facebook/(.*)
        handler: FacebookGraphHandler
        kwargs:
            key: your-consumer-key
            secret: your-consumer-secret
            access_token: your-access-token     # Optional -- picked up from session
            methods: [get, post]                # HTTP methods to use for the API
            scope: user_posts,user_photos       # Permissions requested for the user
            path: /me/feed                      # Freeze Facebook Graph API request

    Now ``POST /facebook/me`` returns the same response as the Facebook Graph API
    ``/me``. To request specific access rights, specify the ``scope`` based on
    `permissions`_ required by the `Graph API`_.

    If you only want to expose a specific API, specify a ``path:``. It overrides
    the URL path. The query parameters will still work.

    By default, ``methods`` is POST, and GET logs the user in, storing the access
    token in the session for future use. But you can specify the ``access_token``
    values and set ``methods`` to ``[get, post]`` to use both GET and POST
    requests to proxy the API.

    .. _permissions: https://developers.facebook.com/docs/facebook-login/permissions
    .. _Graph API: https://developers.facebook.com/docs/graph-api/reference
    '''
    @classmethod
    def setup(cls, **kwargs):
        super(FacebookGraphHandler, cls).setup(**kwargs)
        cls.setup_social('user.facebook', **kwargs)

    @tornado.gen.coroutine
    def run(self, path=None):
        path = self.conf.kwargs.get('path', path)
        if not path and self.request.method == 'GET':
            yield self.login()
            raise tornado.gen.Return()

        args = {key: self.get_argument(key) for key in self.request.arguments}
        args['access_token'] = self.get_token('access_token')
        uri = url_concat(self._FACEBOOK_BASE_URL + '/' + self.conf.kwargs.get('path', path), args)
        http = self.get_auth_http_client()
        response = yield http.fetch(uri, raise_error=False)
        result = yield self.social_response(response)
        self.set_header('Content-Type', 'application/json; charset=UTF-8')
        self.write(result)

    @tornado.gen.coroutine
    def login(self):
        redirect_uri = self.request.protocol + "://" + self.request.host + self.request.uri
        if self.get_argument('code', False):
            info = self.session[self.user_info] = yield self.get_authenticated_user(
                redirect_uri=redirect_uri,
                client_id=self.conf.kwargs['key'],
                client_secret=self.conf.kwargs['secret'],
                code=self.get_argument('code'))
            if self.conf.kwargs.get('access_token', None) == 'persist':
                self.write_store(info)
            self.redirect_next()
        else:
            self.save_redirect_page()
            scope = self.conf.kwargs.get('scope', 'user_posts,read_insights')
            yield self.authorize_redirect(
                redirect_uri=redirect_uri,
                client_id=self.conf.kwargs['key'],
                extra_params={'scope': scope})