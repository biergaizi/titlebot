import re
import base64
import requests
from html.parser import HTMLParser as html_parser
from config import HEADERS
import time
import sys
import bs4


def pickup_url(text):
    """Return a vaild URL from a string"""

    PROTOCOLS = ["http:", "https:", "magnet:"]
    for protocol in PROTOCOLS:
        index = text.find(protocol)
        if index != -1:
            return text[index:]
    return None


def openConnection(word):
    s = requests.Session()
    h = {}
    for item in HEADERS:
        h[item[0]] = item[1]

    if re.match("http:/*([^/]+)\\.i2p(/|$)", word):
        from config import I2P_USER, I2P_PASSWORD
        timeout = 60
        h.pop("X-Forwarded-For")
        s.auth = (I2P_USER, I2P_PASSWORD)
        s.proxies = {"http": "http://127.0.0.1:4444"}
    else:
        timeout = 10

    return s.get(word, headers=h, timeout=timeout, stream=True, verify=True)


def readContents(h, timeout=3):
    """Read a little part of the contents"""
    contents = b""
    counter = 1
    MAX = 8192
    MAX_LENGTH = 16384
    r = h.iter_content(decode_unicode=False)

    start_time = time.time()

    while len(contents) < MAX_LENGTH and counter < MAX:
        if time.time() - start_time > timeout:
            raise RuntimeError("Request timeout.")

        following_contents = b""
        try:
            following_contents += next(r)
        except (StopIteration, Exception):
            break

        # Hack: read more when we saw a script
        if b"<script" in following_contents:
            MAX += 1
            MAX_LENGTH += 16384

        if following_contents:
            contents += following_contents
        counter += 1

    h.close()
    return contents


def lookup_magnet(magnet):
    import json
    import bs4

    bthash_b16 = re.findall(u'(?:\\?|&|&amp;)xt=urn:btih:([0-9A-Fa-f]{40})', magnet)
    bthash_b32 = re.findall(u'(?:\\?|&|&amp;)xt=urn:btih:([2-7A-Za-z]{32})', magnet)
    if bthash_b16 and bthash_b32:
        sys.stderr.write("Assertion error, both bthash!", magnet, "\n")

    if bthash_b16:
        querystring = bthash_b16[0]
    elif bthash_b32:
        querystring = base64.b16encode(base64.b32decode(bthash_b32[0]))
    else:
        # no bt, do not touch url
        return

    raw_info = readContents(openConnection("https://torrentproject.se/?s=%s&out=json" % querystring))
    info = json.loads(raw_info.decode("UTF-8"))

    if info["total_found"] != "0":
        title = info["1"]["title"]
        cat = info["1"]["category"]
        size = info["1"]["torrent_size"]
        return title, cat, size

    # oh, gonna try plan b
    raw_info = readContents(openConnection("https://torrentz.eu/%s" % querystring))
    page = bs4.BeautifulSoup(raw_info, "html.parser")

    try:
        div = page.find_all("div", "download", recursive=True)[0]
        firstmatch = div.find_all(rel="e")[0]

        title = firstmatch.find_all("span")[1].text
        cat = firstmatch.text.split(title)[-1].split()[0]
    except:
        raise RuntimeError("404 Torrent Not Found, maybe DMCA?")

    try:
        div = page.find_all("div", "files")[0]
        size = div.div["title"].replace(",", "").replace("b", "")
    except Exception:
        size = ""

    return title, cat, size


def remove_tailing_space(string):
    if "\n" not in string:
        return string

    tmp = string.split("\n")
    for idx, str in enumerate(tmp):
        tmp[idx] = str.strip()
    return " ".join(tmp).strip()


def web_res_info(word):
    webInfo = {
        "type": "",
        "title": None,
        "size": ""
    }

    def htmlDecode(encodedText):
        decodedText = ""
        for encoding in ("utf-8", "gbk", "gb18030", "iso-8859-1"):
            try:
                decodedText = encodedText.decode(encoding, errors='replace')
                break
            except UnicodeDecodeError:
                pass
        if not decodedText:
            decodedText = decodedText

        decodedText = html_parser().unescape(decodedText).replace("\r", "").replace("\n", " ").strip()
        return decodedText

    if word.startswith("magnet:"):
        webInfo["title"], webInfo["type"], webInfo["size"] = lookup_magnet(word)
        return webInfo

    h = openConnection(word)

    if "Content-Type" not in h.headers or h.headers["Content-Type"].split(";")[0] == "text/html":
        webInfo["type"] = "text/html"
        contents = readContents(h)

        # Other parsers are really naive,
        # they can't even distinguish between comments and code.
        soup = bs4.BeautifulSoup(contents, "html5lib")
        if soup.title:
            webInfo["title"] = remove_tailing_space(soup.title.string)
    else:
        webInfo["type"] = h.info()["Content-Type"]
        if "Content-Range" in h.info():
            webInfo["size"] = h.info()["Content-Range"].split("/")[1]
        elif "Content-Length" in h.info():
            webInfo["size"] = h.info()["Content-Length"]

    return webInfo
