import requests
import uuid
import socket
import datetime
import pytz
import logging

from .sports import SPORTS


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
        params = {'maxResults': max_results,
                  'fields': 'simple,points'}

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
        results = []

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
            logging.info("fetching {max_results} workouts, all except {before} .. {after}".format(max_results=max_results, before=before, after=after))
            return (self._fetch_in_range(max_results=max_results, before=None, after=after) +
                    self._fetch_in_range(max_results=max_results, before=before, after=None))
        else:
            logging.info("fetching {max_results} workouts from {before} .. {after}".format(max_results=max_results, before=before, after=after))
            return self._fetch_in_range(max_results=max_results, before=before, after=after)

    def get_workouts(self, max_results=None, before=None, after=None):
        '''
        if `before` is earlier than `after` all workouts except that in range will be fetched
        '''
        raw = self.get_workouts_raw(max_results, before, after)
        return list(map(Workout, raw))

    fetch = get_workouts


class Workout:
    def __init__(self, properties):
        self.id = properties['id']
        self.start_time = _to_python_time(properties['start_time'])
        self.duration = datetime.timedelta(seconds=properties['duration'])

        self.calories = properties.get('calories', None)

        try:
            self.distance = int(properties['distance'] * 1000)
        except KeyError:
            self.distance = None

        sport = int(properties['sport'])
        self.sport = SPORTS.get(sport, "Other")
        self.sport_number = sport

        try:
            self.points = list(self._parse_points(properties['points']))
        except Exception as e:
            logging.error("skipping points because {}, data: {}".format(e, properties))
            self.points = []

    def __repr__(self):
        return ("#{}, "
                "started: {}, "
                "duration: {}, "
                "sport: {}, "
                "sport_number: {}, "
                "distance: {}m").format(self.id,
                                        self.start_time,
                                        self.duration,
                                        self.sport,
                                        self.sport_number,
                                        self.distance)

    def _parse_points(self, json):

        def _float(dictionary, key):
            if key in dictionary.keys():
                return float(dictionary[key])
            else:
                return None

        def _int(dictionary, key):
            if key in dictionary.keys():
                return int(dictionary[key])
            else:
                return None

        def parse_point(data):
            try:
                return {'time': _to_python_time(data['time']),
                        'lat': float(data['lat']),
                        'lon': float(data['lng']),
                        'alt': _float(data, 'alt'),
                        'cad': _int(data, 'cad'),
                        'hr': _int(data, 'hr')}
            except KeyError as e:
                logging.error("{}, data: {}".format(e, data))
                raise e

        return map(parse_point, json)
