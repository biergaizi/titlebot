import socket
socket.setdefaulttimeout(4)

from queue import Queue
import re
import web
from urllib.error import HTTPError
from hack import async, restart_program, Signal
import libirc
from time import sleep
from config import (HOST, PORT, NICK, IDENT,
                    REALNAME, CHANNELS, ADMINS,
                    IGNORED_URLS)


class IRCHandler(object):

    message_recived = Signal()
    error_raised = Signal()

    def __init__(self, irc_connection):
        self.__connection = irc_connection
        self.__running = True
        self.__message_pool = Queue()

    def __mainloop(self):
        while self.__running:
            text = self.__connection.recvline(block=True)
            message = irc.parse(line=text)
            if message and message['msg'] and message['cmd'] == "PRIVMSG":
                self.__last_message = message
                self.message_recived.emit(message)

    def mainloop(self):
        while self.__running:
            try:
                self.__say()
                self.__mainloop()
            except socket.error as e:
                self.quit("Network error")
            except Exception as e:
                self.complain(self.__last_messag['dest'], e)

    def say(self, nick, text):
        self.__message_pool.put([nick, text])

    def _say(self, nick, text):
        self.__connection.say(nick, text)

    @async
    def __say(self):
        while self.__running:
            sleep(0.5)
            nick, text = self.__message_pool.get(block=True)
            self._say(nick, text)

    def complain(self, nick, text):
        nick = str(nick)
        text = str(text)
        try:
            self.say(nick, "哎呀，%s 好像出了点问题: " % (NICK) + text)
        except Exception:
            pass

    def complain_network(self, nick, text):
        nick = str(nick)
        text = str(text)
        try:
            self.say(nick, "哎呀，网络好像出了点问题: " + text)
        except Exception:
            pass

    def quit(self, reason="Exit"):
        self.__running = False
        self.__connection.quit(reason)


class MessageHandler(object):

    def __init__(self, irc_handler):
        self.__handler = irc_handler
        self.__handler.message_recived.connect(self.message_handler)

    @async
    def message_handler(self, msg):
        if msg['dest'] == NICK:
            self.react_command(msg)
        else:
            self.react_message(msg)

    def react_command(self, msg):
        if msg['nick'] in ADMINS or (not ADMINS):
            if msg['msg'] == "Get out of this channel!":
                self.__handler.quit("%s asked to leave" % msg['nick'])
            elif msg['msg'] == "Restart!":
                self.__handler.quit("%s asked to restart" % msg['nick'])
                restart_program()
            else:
                irc.say(msg['nick'], "Unknown Command, 233333...")
        else:
            irc.say(msg['nick'], "Permission Denied")

    def react_message(self, msg):
        for word in msg['msg'].split():
            self.say_title(msg['dest'], word)

    @async
    def say_title(self, channel, text):
        url = web.pickup_url(text)
        if not url:
            return

        for badurl in IGNORED_URLS:
            if re.match(badurl, url):
                return

        errors = 0
        while True:
            try:
                web_info = web.web_res_info(url)
                if web_info['type'] == "text/html":
                    self.say_webpage_title(channel, web_info)
                else:
                    self.say_resource_info(channel, web_info)
                break
            except (RuntimeError, HTTPError) as e:
                if errors < 3:
                    errors += 1
                    continue
                else:
                    self.__handler.complain_network(channel, e)
                    break
            except Exception as e:
                self.__handler.complain(channel, e)
                break

    def say_webpage_title(self, channel, web_info):
        if web_info['title']:
            self.__handler.say(channel, "⇪标题: %s" % web_info['title'])
        elif web_info['title'] is None:
            self.__handler.say(channel, "⇪无标题网页")
        elif not (web_info['title'].strip()):
            self.__handler.say(channel, "⇪标题: (空)")

    def say_resource_info(self, channel, web_info):
        if web_info['title']:
            assert web_info['size']
            assert web_info['type']
            self.__handler.say(channel, "⇪标题: %s, 文件类型: %s, 文件大小: %s 字节\r\n" % (web_info["title"], web_info['type'], web_info['size']))
        elif web_info['size']:
            assert web_info['type']
            self.__handler.say(channel, "⇪文件类型: %s, 文件大小: %s 字节\r\n" % (web_info['type'], web_info['size']))
        elif web_info['type']:
            self.__handler.say(channel, "⇪文件类型: %s\r\n" % (web_info['type']))


irc = libirc.IRCConnection()
irc.connect((HOST, PORT), use_ssl=True)
irc.setnick(NICK)
irc.setuser(IDENT, REALNAME)

for channel in CHANNELS:
    irc.join(channel)

irc_handler = IRCHandler(irc)
message_handler = MessageHandler(irc_handler)

irc_handler.mainloop()
