import sys
import os
import datetime
import subprocess
import urllib.request
import yaml
import pronto


class EmptyObject:
    """Helper class that creates objects with attributes supplied by keyword arguments"""
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


def open_file_read(filename: str):
    """Function opening a (potentially gzipped) text file for read access"""
    if not filename:
        # Read from stdin
        f = sys.stdin
    else:
        # Check if file exists
        filepath = os.path.abspath(filename)
        if not os.path.exists(filepath):
            raise FileNotFoundError("File '" + filepath + "' does not exist.")
        # Open file for reading
        if filename.endswith(".gz"):
            subprocess.check_call("gunzip -t " + filename, shell=True, stderr=subprocess.DEVNULL)
            f = os.popen("gunzip -c " + filename, "r")
        else:
            f = open(filename, "r")
    return f


def open_file_write(filename: str):
    """Function opening a (potentially gzipped) text file for write access"""
    if not filename:
        # Write to stdout
        f = sys.stdout
    else:
        # Check if path exists
        filepath = os.path.abspath(os.path.dirname(filename))
        if not os.path.exists(filepath):
            raise FileNotFoundError("Directory '" + filepath + "' does not exist.")
        # Open file for writing
        if filename.endswith(".gz"):
            f = os.popen("gzip -9 -c > " + filename, "w")
        else:
            f = open(filename, "w")
    return f


def close(file):
    """Function closing a text file"""
    if file not in [sys.stdout, sys.stderr]:
        file.close()


def read_text(filename: str) -> str:
    """Function reading text from a file"""
    file = open_file_read(filename)
    content = file.read()
    close(file)
    return content


def write_text(filename: str, content: str) -> None:
    """Function writing text to a file"""
    file = open_file_write(filename)
    file.write(content)
    close(file)


def parse_yaml(filename: str) -> dict:
    """Function parsing a YAML file"""
    stream = open_file_read(filename)
    data = dict(yaml.load(stream))
    for key, value in data.items():
        if value is not None:
            data[key] = str(value).strip()
    close(stream)
    return data


def dump_yaml(filename: str, data: dict) -> None:
    """Function dumping data into a YAML file"""
    stream = open_file_write(filename)
    yaml.dump(data, stream)
    close(stream)


def parse_obo(filename: str) -> pronto.Ontology:
    """Function parsing an OBO file"""
    print("Parsing OBO file ...")
    return pronto.Ontology(filename)


def list_to_string(the_list: list, delimiter: str) -> str:
    """Function concatenating all elements of a list"""
    the_string = []
    for element in the_list:
        if isinstance(element, bool) and element:
            the_string.append('t')
        elif isinstance(element, bool) and not element:
            the_string.append('f')
        elif isinstance(element, str):
            the_string.append(element)
        elif element is None:
            the_string.append("")
        else:
            the_string.append(str(element))
    return delimiter.join(the_string)


def current_date() -> str:
    """Function returning the current date in format 'YYYYMMDD"""
    return datetime.date.today().strftime('%Y%m%d')


def download_file(url: str) -> str:
    """Downloads a file from the internet"""
    print("Downloading file from URL " + url + " ...")
    file, headers = urllib.request.urlretrieve(url)
    return file
