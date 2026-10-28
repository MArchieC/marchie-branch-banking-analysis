# Python -> PostgreSQL database container

import psycopg2 #PostgreSQL adapter for Python translating Python calls into PostgreSQL wire-protocol messages and
                #translates responses back

CONNECTION_SETTINGS = {
    "host": "localhost",
    "port": 5432,
    "dbname": "bank_health",
    "user": "capstone",
    "password": "capstone",
}

def get_connection():
    """Return fresh psycopg2 connection to capstone database."""
    return psycopg2.connect(**CONNECTION_SETTINGS)