import pkg_resources
import subprocess
import psycopg2
import urllib.request, urllib.error
from pychado import utils


def generate_uri(connectionDetails: dict) -> str:
    """Creates a connection URI"""
    uriAsList = ["postgresql://"]
    if "user" in connectionDetails and connectionDetails["user"] is not None:
        uriAsList.append(connectionDetails["user"])
        if "password" in connectionDetails and connectionDetails["password"] is not None:
            uriAsList.append(":" + connectionDetails["password"])
        uriAsList.append("@")
    if "host" in connectionDetails and connectionDetails["host"] is not None:
        uriAsList.append(connectionDetails["host"])
    if "port" in connectionDetails and connectionDetails["port"] is not None:
        uriAsList.append(":" + connectionDetails["port"])
    if "database" in connectionDetails and connectionDetails["database"] is not None:
        uriAsList.append("/" + connectionDetails["database"])
    return "".join(uriAsList)


def generate_dsn(connectionDetails: dict) -> str:
    """Creates a connection DSN"""
    dsnAsList = []
    if "database" in connectionDetails and connectionDetails["database"] is not None:
        dsnAsList.append("dbname=" + connectionDetails["database"] + " ")
    if "user" in connectionDetails and connectionDetails["user"] is not None:
        dsnAsList.append("user=" + connectionDetails["user"] + " ")
    if "password" in connectionDetails and connectionDetails["password"] is not None:
        dsnAsList.append("password=" + connectionDetails["password"] + " ")
    if "host" in connectionDetails and connectionDetails["host"] is not None:
        dsnAsList.append("host=" + connectionDetails["host"] + " ")
    if "port" in connectionDetails and connectionDetails["port"] is not None:
        dsnAsList.append("port=" + connectionDetails["port"] + " ")
    return "".join(dsnAsList).strip()


def getSchemaUrl() -> str:
    """Obtains the URL for a database schema from parsing a YAML file"""
    yamlFile = pkg_resources.resource_filename("pychado", "data/gmodSchema.yml")
    defaultSchema = utils.parse_yaml(yamlFile)
    return defaultSchema["url"].replace("<VERSION>", defaultSchema["version"])


def connect(configurationFile: str, dbname: str) -> None:
    """Connects to a PostgreSQL database and brings back a command line prompt"""

    # Create a URI based on connection parameters from a configuration file
    if not configurationFile:
        configurationFile = pkg_resources.resource_filename("pychado", "data/exampleDB.yml")
    connectionDetails = utils.parse_yaml(configurationFile)
    connectionDetails["database"] = dbname
    connectionURI = generate_uri(connectionDetails)

    # Establish a connection to an SQL server by running a subprocess
    print("Establishing connection to database...")
    command = ["psql", connectionURI]
    subprocess.run(command)
    print("Connection to database closed.")


def create(configurationFile: str, schemaFile: str, dbname: str) -> None:
    """Creates a new PostgreSQL database"""

    # Create a DSN based on connection parameters from a configuration file
    if not configurationFile:
        configurationFile = pkg_resources.resource_filename("pychado", "data/exampleDB.yml")
    connectionDetails = utils.parse_yaml(configurationFile)
    dsn = generate_dsn(connectionDetails)

    # Create a new database
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("CREATE DATABASE " + dbname)
    cur.close()
    conn.close()
    print("Database has been created.")

    # Download schema if not saved locally
    if not schemaFile:
        print("Downloading database schema...")
        url = getSchemaUrl()
        try:
            schemaFile, headers = urllib.request.urlretrieve(url)
        except urllib.error.HTTPError:
            raise Exception("HTTP Error 404: The address '" + url + "' does not exist.")

    # Set up the database with the provided schema
    connectionDetails["database"] = dbname
    connectionURI = generate_uri(connectionDetails)
    command = ["psql", "-q", "-f", schemaFile, connectionURI]
    subprocess.run(command)
    print("Database schema has been set up.")


def dump(configurationFile: str, dbname: str, archive: str) -> None:
    """Dumps a PostgreSQL database into an archive file"""

    # Create a URI based on connection parameters from a configuration file
    if not configurationFile:
        configurationFile = pkg_resources.resource_filename("pychado", "data/exampleDB.yml")
    connectionDetails = utils.parse_yaml(configurationFile)
    connectionDetails["database"] = dbname
    connectionURI = generate_uri(connectionDetails)

    # Dump the database by running a subprocess
    command = ["pg_dump", "-f", archive, "--format=custom", connectionURI]
    subprocess.run(command)
    print("Database has been dumped.")


def restore(configurationFile: str, archive: str) -> None:
    """Restores a PostgreSQL database from an archive file"""

    # Create a URI based on connection parameters from a configuration file
    if not configurationFile:
        configurationFile = pkg_resources.resource_filename("pychado", "data/exampleDB.yml")
    connectionDetails = utils.parse_yaml(configurationFile)
    connectionURI = generate_uri(connectionDetails)

    # Restore the database by running a subprocess
    command = ["pg_restore", "--create", "--clean", "--format=custom", "-d", connectionURI, archive]
    subprocess.run(command)
    print("Database has been restored.")