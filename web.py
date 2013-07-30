import urllib.request, urllib.error, urllib.parse
import http.cookiejar
from html.parser import HTMLParser as html_parser
import zlib
from config import HEADERS


def pickup_url(text):
    """Return a vaild URL from a string"""

    PROTOCOLS = ["http:", "https:"]
    for protocol in PROTOCOLS:
        index = text.find(protocol)
        if index != -1:
            return text[index:]
    return None


def web_res_info(word):
    webInfo = {
        "type": "",
        "title": None,
        "size": ""
    }

    def openConnection(word):
        cookieJar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPRedirectHandler,
                                             urllib.request.HTTPCookieProcessor(cookieJar))
        opener.addheaders = HEADERS
        h = opener.open(word)

        if h.code not in [200, 206]:
            raise urllib.error.HTTPError(code=h.code)
        return h

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

    def readContents(h):
        """Read a little part of the contents"""
        contents = b""
        counter = 1
        MAX = 5
        MAX_LENGTH = 16384

        while len(contents) < MAX_LENGTH and counter < MAX:
            following_contents = h.read(16384)

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

    def decompressContents(contents):
        """Decompress gzipped contents, ignore the error"""
        try:
            gunzip = zlib.decompressobj(16 + zlib.MAX_WBITS)
            contents = gunzip.decompress(contents)
        except Exception as e:
            pass
        return contents

    h = openConnection(word)

    if h.info()["Content-Type"].split(";")[0] == "text/html" or (not "Content-Type" in h.info()):
        webInfo["type"] = "text/html"
        contents = readContents(h)

        if h.info().get("Content-Encoding") == "gzip":  # Fix buggy www.bilibili.tv
            contents = decompressContents(contents)

        contents = htmlDecode(contents)
        if contents.find("<title>") != -1:
            encodedTitle = contents.split("<title>")[1].split("</title>")[0]
            webInfo['title'] = encodedTitle
        else:
            webInfo['title'] = ""
    else:
        webInfo["type"] = h.info()["Content-Type"]
        if "Content-Range" in h.info():
            webInfo["size"] = h.info()["Content-Range"].split("/")[1]
        elif "Content-Length" in h.info():
            webInfo["size"] = h.info()["Content-Length"]

    return webInfo
