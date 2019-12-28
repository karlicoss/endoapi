import datetime
import logging
import socket
import uuid
from typing import Iterator, NamedTuple, Optional, Union, TypeVar

import pytz
import requests

from .sports import SPORTS


T = TypeVar('T')
Res = Union[T, Exception]


logger = logging.getLogger('endoapi')
logger.addHandler(logging.NullHandler())

class Protocol:
    os = "Android"
    os_version = "2.2"
    model = "M"
    user_agent = "Dalvik/1.4.0 (Linux; U; %s %s; %s Build/GRI54)" % (os, os_version, model)
    device_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, socket.gethostname()))

    def __init__(self, email=None, password=None, token=None):
        self.auth_token = token
        self.request = requests.session()
        self.request.headers['User-Agent'] = self.user_agent

        if self.auth_token is None:
            self.auth_token = self._request_auth_token(email, password)

    def _request_auth_token(self, email, password):
        params = {'email':       email,
                  'password':    password,
                  'country':     'US',
                  'deviceId':    self.device_id,
                  'os':          self.os,
                  'appVersion':  "7.1",
                  'appVariant':  "M-Pro",
                  'osVersion':   self.os_version,
                  'model':       self.model,
                  'v':           2.4,
                  'action':      'PAIR'}

        r = self._simple_call('auth', params)

        for line in self._parse_text(r):
            key, value = line.split("=")
            if key == "authToken":
                return value

        return None

    def _parse_text(self, response):
        lines = response.text.split("\n")

        if len(lines) < 1:
            raise ValueError("Error: URL %s: empty response" % response.url)

        if lines[0] != "OK":
            raise ValueError("Error: URL %s: %s" % (response.url, lines[0]))

        return lines[1:]

    def _parse_json(self, response):
        return response.json()['data']

    def _simple_call(self, command, params):
        r = self.request.get('http://api.mobile.endomondo.com/mobile/' + command, params=params)

        # false positive https://github.com/PyCQA/pylint/issues/1411
        # pylint: disable=no-member
        if r.status_code != requests.codes.ok:
            r.raise_for_status()
            return None

        return r

    def _call(self, url, params={}):
        params.update({'authToken': self.auth_token,
                       'language': 'EN'})

        r = self._simple_call(url, params)

        return r.json()['data']

    def get_workouts_chunk(self, max_results=40, before=None, after=None):
        # see https://github.com/kanekotic/endomondo-unofficial-api/blob/master/lib/workout.js
        params = {'maxResults': max_results,
                  'fields': 'device,simple,basic,interval,points'}

        if after is not None:
            params.update({'after': _to_endomondo_time(after)})

        if before is not None:
            params.update({'before': _to_endomondo_time(before)})

        json = self._call('api/workout/list', params)

        return json


def _to_endomondo_time(time):
    return time.astimezone(pytz.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _to_python_time(endomondo_time):
    return datetime.datetime.strptime(endomondo_time, "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=pytz.utc)


def connect(email=None, password=None, token=None):
    '''
    establish endomondo session by email/password or the token
    if already known
    '''
    return Endomondo(email=email, password=password, token=token)


class Endomondo:
    def __init__(self, email=None, password=None, token=None):
        self.protocol = Protocol(email, password, token)

        # for compatibility
        self.auth_token = self.protocol.auth_token
        self.token = self.protocol.auth_token
        self.chunk_size = 10

    def _fetch_in_range(self, max_results=None, before=None, after=None):
        _before = before
        results = [] # type: ignore

        while True:
            chunk = self.protocol.get_workouts_chunk(max_results=self.chunk_size,
                                                     before=_before,
                                                     after=after)

            if chunk:
                results.extend(chunk)
                last_start_time = chunk[-1]['start_time']
                _before = _to_python_time(last_start_time)

            if not chunk or (max_results and len(results) >= max_results):
                break

        return results

    def get_workouts_raw(self, max_results=None, before=None, after=None):
        if before is not None and after is not None and before < after:
            logger.info("fetching {max_results} workouts, all except {before} .. {after}".format(max_results=max_results, before=before, after=after))
            return (self._fetch_in_range(max_results=max_results, before=None, after=after) +
                    self._fetch_in_range(max_results=max_results, before=before, after=None))
        else:
            logger.info("fetching {max_results} workouts from {before} .. {after}".format(max_results=max_results, before=before, after=after))
            return self._fetch_in_range(max_results=max_results, before=before, after=after)

    def get_workouts(self, max_results=None, before=None, after=None):
        '''
        if `before` is earlier than `after` all workouts except that in range will be fetched
        '''
        raw = self.get_workouts_raw(max_results, before, after)
        return list(map(Workout, raw))

    fetch = get_workouts


class Point(NamedTuple):
    time: datetime.datetime
    hr  : Optional[float]
    lat : Optional[float]
    lon : Optional[float]

    @classmethod
    def parse(cls, d) -> Res['Point']:
        time = d.get('time', None)
        if time is None:
            # not sure why is that possible what would that mean?
            return RuntimeError(f'No timestamp: {d}')
        else:
            return cls(
                time=_to_python_time(time),
                hr  =d.get('hr' , None),
                lat =d.get('lat', None),
                lon =d.get('lon', None),
            )
        # TODO what is 'dist'? and 'inst'?
                # return {'time': ),
                #         'alt': _float(data, 'alt'),
                #         'cad': _int(data, 'cad'),


class Workout:
    def __init__(self, properties):
        self.properties = properties
        self.id = properties['id']
        self.start_time = _to_python_time(properties['start_time'])
        self.duration = datetime.timedelta(seconds=properties['duration'])

        dist = properties.get('distance')
        self.distance = None if dist is None else int(dist * 1000)

        # TODO not sure if should distinguish having no points and empty list?
        pointsdicts = properties.get('points', {})
        # TODO could add policy for suppressing errors, if necessary
        self.points = list(map(Point.parse, pointsdicts))

    @property
    def sport(self):
        sport_num = int(self.properties['sport'])
        return SPORTS.get(sport_num, 'Other')

    @property
    def calories(self):
        return self.properties.get('calories', None)

    @property
    def comment(self):
        return self.properties.get('message', None)

    def __repr__(self):
        return ("#{}, "
                "started: {}, "
                "duration: {}, "
                "sport: {}, "
                "distance: {}m").format(self.id,
                                        self.start_time,
                                        self.duration,
                                        self.sport,
                                        self.distance)
