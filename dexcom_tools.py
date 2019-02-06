#!/usr/bin/env python

import datetime
import logging
import os
import re
import requests
import time
import urllib

DEXCOM_ACCOUNT_NAME = "xxx"
DEXCOM_PASSWORD = "yyy"
AUTH_RETRY_DELAY_BASE = 2
FETCH_RETRY_DELAY_BASE = 2
MAX_AUTHFAILS = 3
MAX_FETCHFAILS = 3

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
    "NO_DIR": 0,
    "DOUBLE_UP": 1,
    "SINGLE_UP": 2,
    "45_UP": 3,
    "FLAT": 4,
    "45_DOWN": 5,
    "SINGLE_DOWN": 6,
    "DOUBLE_DOWN": 7,
    "NOT_COMPUTABLE": 8,
    "RATE_OUT_OF_RANGE": 9,
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


def parse_dexcom_response(ops, res):
    try:
        last_reading_time = int(
            re.search('\d+', res.json()[0]['ST']).group())/1000
        trend = res.json()[0]['Trend']
        mgdl = res.json()[0]['Value']
        trend_english = DIRECTIONS.keys()[DIRECTIONS.values().index(trend)]
        return {
                "bg": mgdl,
                "trend": trend,
                "trend_english": trend_english,
                "last_reading_time": last_reading_time
                }
    except IndexError:
        return None


def get_sessionID(opts):
    authfails = 0
    while True:
        try:
            res = authorize(opts)
            if res and res.status_code == 200:
                opts.sessionID = res.text.strip('"')
                return 0
            else:
                if authfails > MAX_AUTHFAILS:
                    return -1
                else:
                    time.sleep(AUTH_RETRY_DELAY_BASE**authfails)
                    authfails += 1
        except:
            return -2


def monitor_dexcom():
    fetchfails = 0
    while True:
        try:
            res = fetch(opts)
            if res and res.status_code < 400:
                reading = parse_dexcom_response(opts, res)
                return reading
            else:
                if fetchfails > MAX_FETCHFAILS:
                    opts.sessionID = None
                    return -1
                else:
                    time.sleep(FETCH_RETRY_DELAY_BASE**fetchfails)
                    fetchfails += 1
        except:
            opts.sessionID = None
            return -2

opts = Defaults
opts.accountName = os.getenv("DEXCOM_ACCOUNT_NAME", DEXCOM_ACCOUNT_NAME)
opts.password = os.getenv("DEXCOM_PASSWORD", DEXCOM_PASSWORD)

get_sessionID(opts)

reading = monitor_dexcom()
print(reading)
print(time.localtime(reading["last_reading_time"]))
time.sleep(30)
reading = monitor_dexcom()
print(reading)
print(time.localtime(reading["last_reading_time"]))
