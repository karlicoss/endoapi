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

    def call(self, url, params={}):
        params.update({'authToken': self.auth_token,
                       'language': 'EN'})

        r = self._simple_call(url, params)

        return r.json()['data']


def _to_endomondo_time(time):
    return time.astimezone(pytz.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _to_python_time(endomondo_time):
    return datetime.datetime.strptime(endomondo_time, "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=pytz.utc)


class Endomondo:
    def __init__(self, email=None, password=None, token=None):
        self.protocol = Protocol(email, password, token)

        # for compatibility
        self.auth_token = self.protocol.auth_token
        self.token = self.protocol.auth_token

    def _get_workouts_chunk(self, max_results=40, before=None, after=None):
        params = {'maxResults': max_results,
                  'fields': 'simple,points'}

        if after is not None:
            params.update({'after': _to_endomondo_time(after)})

        if before is not None:
            params.update({'before': _to_endomondo_time(before)})

        json = self.protocol.call('api/workout/list', params)

        return list(map(Workout, json))

    def get_workouts(self, max_results=None, after=None):
        chunk_size = 40

        result = []
        before = None
        for part in range(500):
            chunk = self._get_workouts_chunk(max_results=chunk_size, after=after, before=before)
            result.extend(chunk)

            logging.debug("chunk #{} {} -> {}".format(part, chunk[0].start_time, chunk[-1].start_time))

            if len(chunk) < chunk_size or (max_results is not None and max_results < len(result)):
                break
            else:
                before = chunk[-1].start_time

        return result


class Workout:
    def __init__(self, properties):
        self.properties = properties
        self.id = properties['id']
        self.start_time = _to_python_time(properties['start_time'])
        self.duration = datetime.timedelta(seconds=properties['duration'])

        try:
            self.distance = int(properties['distance'] * 1000)
        except KeyError:
            self.distance = None

        sport = int(properties['sport'])
        self.sport = SPORTS.get(sport, "Other")

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
                "distance: {}m").format(self.id,
                                        self.start_time,
                                        self.duration,
                                        self.sport,
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
                        'hr': _int(data, 'hr')}
            except KeyError as e:
                logging.error("{}, data: {}".format(e, data))
                raise e

        return map(parse_point, json)
