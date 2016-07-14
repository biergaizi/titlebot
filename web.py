import re
import base64
import urllib.request
import urllib.error
import urllib.parse
import http.cookiejar
from html.parser import HTMLParser as html_parser
import zlib
import io
from config import HEADERS
import time
import sys
import bs4
import copy


def pickup_url(text):
    """Return a vaild URL from a string"""

    PROTOCOLS = ["http:", "https:", "magnet:"]
    for protocol in PROTOCOLS:
        index = text.find(protocol)
        if index != -1:
            return text[index:]
    return None


def openConnection(word, encoding=True):
    cookieJar = http.cookiejar.CookieJar()

    if re.match("http:/*([^/]+)\\.i2p(/|$)", word):
        from config import I2P_USER, I2P_PASSWORD
        timeout = 60
        authinfo = urllib.request.HTTPBasicAuthHandler()
        authinfo.add_password(realm=None, uri=word, user=I2P_USER, passwd=I2P_PASSWORD)
        proxy_support = urllib.request.ProxyHandler({"http" : "http://127.0.0.1:4444"})
        opener = urllib.request.build_opener(urllib.request.HTTPRedirectHandler,
                                             urllib.request.HTTPCookieProcessor(cookieJar),
                                             proxy_support, authinfo)
        headers = copy.deepcopy(HEADERS)
        remove = -1

        for idx, item in enumerate(headers):
            if item[0] == "X-Forwarded-For":
                remove = idx
        if remove > 0:
            del headers[remove]
        opener.addheaders = headers
    else:
        timeout = 10
        opener = urllib.request.build_opener(urllib.request.HTTPRedirectHandler,
                                             urllib.request.HTTPCookieProcessor(cookieJar))
        opener.addheaders = HEADERS
    if encoding:
        word = urllib.parse.quote(word, safe=":/=?%#")
    h = opener.open(word, timeout=timeout)

    if h.code not in [200, 206]:
        raise urllib.error.HTTPError(code=h.code)
    return h


def readContents(h, timeout=3):
    """Read a little part of the contents"""
    contents = b""
    counter = 1
    MAX = 8192
    MAX_LENGTH = 16384

    start_time = time.time()

    while len(contents) < MAX_LENGTH and counter < MAX:
        if time.time() - start_time > timeout:
            raise RuntimeError("Request timeout.")

        following_contents = h.read(16)

        # Hack: read more when we saw a script
        if b"<script" in following_contents:
            MAX += 1
            MAX_LENGTH += 16384

        if following_contents:
            contents += following_contents
        else:
            break
        counter += 1
    return contents


def decompressContents(compressed_contents, block_size=128, max_length=1024000):
    """Decompress gzipped contents, ignore the error"""

    gzipped_stream = io.BytesIO(compressed_contents)

    decompressed_contents = b""
    decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)

    while len(decompressed_contents) < max_length:
        block = gzipped_stream.read(block_size)
        if not block:
            break
        seek = decompressor.unconsumed_tail + block
        decompressed_block = decompressor.decompress(seek)
        decompressed_contents += decompressed_block
    else:
        raise RuntimeError("Too large gzipped content.")

    gzipped_stream.close()

    return decompressed_contents


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

    raw_info = readContents(openConnection("https://torrentproject.se/?s=%s&out=json" % querystring, encoding=False))
    info = json.loads(raw_info.decode("UTF-8"))

    if info["total_found"] != "0":
        title = info["1"]["title"]
        cat = info["1"]["category"]
        size = info["1"]["torrent_size"]
        return title, cat, size

    # oh, gonna try plan b
    raw_info = readContents(openConnection("https://torrentz.eu/%s" % querystring, encoding=False))
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
                decodedText = encodedText.decode(encoding)
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

    if "Content-Type" not in h.info() or h.info()["Content-Type"].split(";")[0] == "text/html":
        webInfo["type"] = "text/html"
        contents = readContents(h)

        if h.info().get("Content-Encoding") == "gzip":  # Fix buggy www.bilibili.tv
            contents = decompressContents(contents)

        # Other parsers are really naive,
        # they can't even distinguish between comments and code.
        soup = bs4.BeautifulSoup(contents, "html5lib")
        if soup.title:
            webInfo["title"] = soup.title.string
    else:
        webInfo["type"] = h.info()["Content-Type"]
        if "Content-Range" in h.info():
            webInfo["size"] = h.info()["Content-Range"].split("/")[1]
        elif "Content-Length" in h.info():
            webInfo["size"] = h.info()["Content-Length"]

    return webInfo
