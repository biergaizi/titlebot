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


def pickup_url(text):
    """Return a vaild URL from a string"""

    PROTOCOLS = ["http:", "https:", "magnet:"]
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

    def transformSpecialResource(url):
        i2p = re.sub('http:/*([^/]+)\\.i2p(/|$)', 'http://\\1.i2p.xyz\\2', word)
        if (i2p != word):
            return i2p

        bthash_b16 = re.findall(u'(?:\\?|&|&amp;)xt=urn:btih:([0-9A-Fa-f]{40})', word)
        bthash_b32 = re.findall(u'(?:\\?|&|&amp;)xt=urn:btih:([2-7A-Za-z]{32})', word)
        if bthash_b16 and bthash_b32:
            print("Assertion Error, both bthash!")
            print(word)

        if bthash_b16:
            querystring = bthash_b16[0].encode('utf-8', 'replace')
        elif bthash_b32:
            querystring = base64.b16encode(base64.b32decode(bthash_b32[0]))
        else:
            # no bt, do not touch url
            return url

        return 'https://btdigg.org/search?info_hash=%s' % querystring


    def openConnection(word):
        cookieJar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPRedirectHandler,
                                             urllib.request.HTTPCookieProcessor(cookieJar))
        opener.addheaders = HEADERS

        if "i2p.xzy" in word:
            timeout = 60
        else:
            timeout = 10
        h = opener.open(word, timeout=timeout)

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

    word = transformSpecialResource(word)
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
