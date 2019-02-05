#!/usr/bin/env python

import datetime
import logging
import os
import re
import requests
import time
import urllib

DEXCOM_ACCOUNT_NAME = "dclovesdc"
DEXCOM_PASSWORD = "wowrls21"
AUTH_RETRY_DELAY_BASE = 2
FAIL_RETRY_DELAY_BASE = 2
MAX_AUTHFAILS = 1
MAX_FETCHFAILS = 10
LAST_READING_MAX_LAG = 60 * 15

class Defaults:
    applicationId = "d89443d2-327c-4a6f-89e5-496bbb0317db"
    agent = "Dexcom Share/3.0.2.11 CFNetwork/711.2.23 Darwin/14.0.0"
    login_url = "https://share1.dexcom.com/ShareWebServices/Services/" +\
        "General/LoginPublisherAccountByName"
    accept = 'application/json'
    content_type = 'application/json'
    LatestGlucose_url = "https://share1.dexcom.com/ShareWebServices/" +\
        "Services/Publisher/ReadPublisherLatestGlucoseValues"
    sessionID = None
    MIN_PASSPHRASE_LENGTH = 12
    last_seen = 0


# Mapping friendly names to trend IDs from dexcom
DIRECTIONS = {
    "nodir": 0,
    "DoubleUp": 1,
    "SingleUp": 2,
    "FortyFiveUp": 3,
    "Flat": 4,
    "FortyFiveDown": 5,
    "SingleDown": 6,
    "DoubleDown": 7,
    "NOT COMPUTABLE": 8,
    "RATE OUT OF RANGE": 9,
}
keys = DIRECTIONS.keys()


def login_payload(opts):
    """ Build payload for the auth api query """
    body = {
        "password": opts.password,
        "applicationId": opts.applicationId,
        "accountName": opts.accountName
        }
    return body


def authorize(opts):
    """ Login to dexcom share and get a session token """

    url = Defaults.login_url
    body = login_payload(opts)
    headers = {
            'User-Agent': Defaults.agent,
            'Content-Type': Defaults.content_type,
            'Accept': Defaults.accept
            }

    return requests.post(url, json=body, headers=headers)


def fetch_query(opts):
    """ Build the api query for the data fetch
    """
    q = {
        "sessionID": opts.sessionID,
        "minutes":  1440,
        "maxCount": 1
        }
    url = Defaults.LatestGlucose_url + '?' + urllib.urlencode(q)
    return url


def fetch(opts):
    """ Fetch latest reading from dexcom share
    """
    url = fetch_query(opts)
    body = {
            'applicationId': 'd89443d2-327c-4a6f-89e5-496bbb0317db'
            }

    headers = {
            'User-Agent': Defaults.agent,
            'Content-Type': Defaults.content_type,
            'Content-Length': "0",
            'Accept': Defaults.accept
            }

    return requests.post(url, json=body, headers=headers)


class Error(Exception):
    """Base class for exceptions in this module."""
    pass


class AuthError(Error):
    """Exception raised for errors when trying to Auth to Dexcome share
    """

    def __init__(self, status_code, message):
        self.expression = status_code
        self.message = message
        print(message.__dict__)


class FetchError(Error):
    """Exception raised for errors in the date fetch.
    """

    def __init__(self, status_code, message):
        self.expression = status_code
        self.message = message
        print(message.__dict__)


def parse_dexcom_response(ops, res):
    epochtime = int((
                datetime.datetime.utcnow() -
                datetime.datetime(1970, 1, 1)).total_seconds())
    try:
        last_reading_time = int(
            re.search('\d+', res.json()[0]['ST']).group())/1000
        reading_lag = epochtime - last_reading_time
        trend = res.json()[0]['Trend']
        mgdl = res.json()[0]['Value']
        trend_english = DIRECTIONS.keys()[DIRECTIONS.values().index(trend)]
        print(
                "Last bg: {}  trending: {}  last reading at: {} seconds ago".format(mgdl, trend_english, reading_lag))
        if reading_lag > LAST_READING_MAX_LAG:
            print(
                "***WARN It has been {} minutes since DEXCOM got a" +
                "new measurement".format(int(reading_lag/60)))
        return {
                "bg": mgdl,
                "trend": trend,
                "trend_english": trend_english,
                "reading_lag": reading_lag,
                "last_reading_time": last_reading_time
                }
    except IndexError:
        print(
                "Caught IndexError: return code:{} ... response output" +
                " below".format(res.status_code))
        print(res.__dict__)
        return None


def get_sessionID(opts):
    authfails = 0
    while not opts.sessionID:
        res = authorize(opts)
        if res.status_code == 200:
            opts.sessionID = res.text.strip('"')
            print("Got auth token {}".format(opts.sessionID))
        else:
            if authfails > MAX_AUTHFAILS:
                raise AuthError(res.status_code, res)
            else:
                print("Auth failed with: {}".format(res.status_code))
                time.sleep(AUTH_RETRY_DELAY_BASE**authfails)
                authfails += 1
    return opts.sessionID


def monitor_dexcom():
    """ Main loop """

    opts = Defaults
    opts.accountName = os.getenv("DEXCOM_ACCOUNT_NAME", DEXCOM_ACCOUNT_NAME)
    opts.password = os.getenv("DEXCOM_PASSWORD", DEXCOM_PASSWORD)

    runs = 0
    fetchfails = 0
    failures = 0
    runs += 1
    if not opts.sessionID:
        authfails = 0
        opts.sessionID = get_sessionID(opts)
    try:
        res = fetch(opts)
        if res and res.status_code < 400:
            fetchfails = 0
            reading = parse_dexcom_response(opts, res)
            if reading:
                return reading
            else:
                opts.sessionID = None
                log.error(
                    "parse_dexcom_response returned None." +
                    "investigate above logs")
                if run_once:
                    return None
        else:
            failures += 1
            if run_once or fetchfails > MAX_FETCHFAILS:
                opts.sessionID = None
                print("Saw an error from the dexcom api, code: {}.  details to follow".format(res.status_code))
                raise FetchError(res.status_code, res)
            else:
                print("Fetch failed on: {}".format(res.status_code))
                if fetchfails > (MAX_FETCHFAILS/2):
                    print("Trying to re-auth...")
                    opts.sessionID = None
                else:
                    print("Trying again...")
                time.sleep(
                    (FAIL_RETRY_DELAY_BASE**authfails))
                    #opts.interval)
                fetchfails += 1
    except ConnectionError:
        opts.sessionID = None
        if run_once:
            raise
        print(
            "Cnnection Error.. sleeping for {} seconds and".format(RETRY_DELAY) +
            " trying again")
        time.sleep(RETRY_DELAY)


if __name__ == '__main__':
    reading = monitor_dexcom()
    print(reading)
