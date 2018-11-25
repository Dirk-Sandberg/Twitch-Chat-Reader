#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""

@author: Erik Sandberg

https://github.com/317070/python-twitch-stream/blob/master/examples/basic_chat.py
https://www.elifulkerson.com/projects/commandline-text-to-speech.php # Voice.exe for windows TTS

Adapted from code with the following license:
    
Copyright (c) 2015 Jonas Degrave

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.


TWITCH USERNAME: ImABotBoy
TWITCH PW: BotBoyBaby
NICK = "ImABotBoy"
PASS = "oauth:1ruvijtcfg81i6d0b44j5ct76mrhyo"

This file contains the python code used to interface with the Twitch
chat. Twitch chat is IRC-based, so it is basically an IRC-bot, but with
special features for Twitch, such as congestion control built in.
"""
import pyHook #import HookManager, GetKeyState, HookConstants
#from __future__ import print_function
import tkinter as tk
import time
import socket
import re
import sys
try: # Mac user
    import fcntl
except: # Windows user, they'll use socket instead
    pass
import subprocess
import os
import errno
import threading

class TwitchChatStream(object):
    """
    The TwitchChatStream is used for interfacing with the Twitch chat of
    a channel. To use this, an oauth-account (of the user chatting)
    should be created. At the moment of writing, this can be done here:
    https://twitchapps.com/tmi/
    :param username: Twitch username
    :type username: string
    :param oauth: oauth for logging in (see https://twitchapps.com/tmi/)
    :type oauth: string
    :param verbose: show all stream messages on stdout (for debugging)
    :type verbose: boolean
    """

    def __init__(self, username, oauth, verbose=False):
        """Create a new stream object, and try to connect."""
        self.username = username
        self.oauth = oauth
        self.verbose = verbose
        self.current_channel = ""
        self.last_sent_time = time.time()
        self.buffer = []
        self.connected = False
        self.s = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, type, value, traceback):
        self.s.close()

    @staticmethod
    def _logged_in_successful(data):
        """
        Test the login status from the returned communication of the
        server.
        :param data: bytes received from server during login
        :type data: list of bytes
        :return boolean, True when you are logged in.
        """
        '''
        if re.match(r'^:(testserver\.local|tmi\.twitch\.tv)'join(self
                    r' NOTICE \* :'
                    r'(Login unsuccessful|Error logging in)*$',
                    data.strip()):
            return False'''
        if "Login authentication failed" in data or "Improperly formatted auth" in data:
            return False
        else:
            return True

    @staticmethod
    def _check_has_ping(data):
        """
        Check if the data from the server contains a request to ping.
        :param data: the byte string from the server
        :type data: list of bytes
        :return: True when there is a request to ping, False otherwise
        """
        return re.match(
            r'^PING :tmi\.twitch\.tv$', data)

    @staticmethod
    def _check_has_channel(data):
        """
        Check if the data from the server contains a channel switch.
        :param data: the byte string from the server
        :type data: list of bytes
        :return: Name of channel when new channel, False otherwise
        """
        return re.findall(
            r'^:[a-zA-Z0-9_]+\![a-zA-Z0-9_]+@[a-zA-Z0-9_]+'
            r'\.tmi\.twitch\.tv '
            r'JOIN #([a-zA-Z0-9_]+)$', data)

    @staticmethod
    def _check_has_message(data):
        """
        Check if the data from the server contains a message a user
        typed in the chat.
        :param data: the byte string from the server
        :type data: list of bytes
        :return: returns iterator over these messages
        """
        return re.match(r'^:[a-zA-Z0-9_]+\![a-zA-Z0-9_]+@[a-zA-Z0-9_]+'
                        r'\.tmi\.twitch\.tv '
                        r'PRIVMSG #[a-zA-Z0-9_]+ :.+$', data)

    def connect(self):
        """
        Connect to Twitch
        """

        # Do not use non-blocking stream, they are not reliably
        # non-blocking
        # s.setblocking(False)
        # s.settimeout(1.0)

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        connect_host = "irc.twitch.tv"
        connect_port = 6667
        try:
            s.connect((connect_host, connect_port))
        except (Exception, IOError):
            print ("Unable to create a socket to %s:%s" % (connect_host,connect_port))
            raise  # unexpected, because it is a blocking socket

        # Connected to twitch
        # Sending our details to twitch...
        s.send(('PASS %s\r\n' % self.oauth).encode('utf-8'))
        s.send(('NICK %s\r\n' % self.username).encode('utf-8'))
        if self.verbose:
            print ('PASS %s\r\n' % self.oauth)
            print ('NICK %s\r\n' % self.username)

        received = s.recv(1024).decode()
        if self.verbose:
            print (received)
        if not TwitchChatStream._logged_in_successful(received):
            # ... and they didn't accept our details
            self.connected=False
            return #raise IOError("Twitch did not accept the username-oauth combination")
        
        else:
            self.connected=True
            # ... and they accepted our details
            # Connected to twitch.tv!
            # now make this socket non-blocking on the OS-level
            try: # Mac user
                fcntl.fcntl(s,fcntl.F_SETFL,os.O_NONBLOCK)
            except: # Windows user
                s.setblocking(0)
            self.s = s


    def _push_from_buffer(self):
        """
        Push a message on the stack to the IRC stream.
        This is necessary to avoid Twitch overflow control.
        """
        if len(self.buffer) > 0:
            if time.time() - self.last_sent_time > 5:
                try:
                    message = self.buffer.pop(0)
                    self.s.send(message.encode('utf-8'))
                    if self.verbose:
                        print (message)
                finally:
                    self.last_sent_time = time.time()

    def _send(self, message):
        """
        Send a message to the IRC stream
        :param message: the message to be sent.
        :type message: string
        """
        if len(message) > 0:
            self.buffer.append(message + "\n")

    def _send_pong(self):
        """
        Send a pong message, usually in reply to a received ping message
        """
        self._send("PONG")

    def join_channel(self, channel):
        """
        Join a different chat channel on Twitch.
        Note, this function returns immediately, but the switch might
        take a moment
        :param channel: name of the channel (without #)
        """
        self.s.send(('JOIN #%s\r\n' % channel).encode('utf-8'))
        if self.verbose:
            print ('JOIN #%s\r\n' % channel)

    def send_chat_message(self, toChannel, message):
        """
        Send a chat message to the server.
        :param message: String to send (don't use \\n)
        :param toChannel: lowercase string of channel name to send message to
        """
        self._send("PRIVMSG #{0} :{1}".format(toChannel, message))

    def _parse_message(self, data):
        """
        Parse the bytes received from the socket.
        :param data: the bytes received from the socket
        :return:
        """
        if TwitchChatStream._check_has_ping(data):
            self._send_pong()
        if TwitchChatStream._check_has_channel(data):
            self.current_channel = \
                TwitchChatStream._check_has_channel(data)[0]

        if TwitchChatStream._check_has_message(data):
            return {
                'channel': re.findall(r'^:.+![a-zA-Z0-9_]+'
                                      r'@[a-zA-Z0-9_]+'
                                      r'.+ '
                                      r'PRIVMSG (.*?) :',
                                      data)[0],
                'username': re.findall(r'^:([a-zA-Z0-9_]+)!', data)[0],
                'message': re.findall(r'PRIVMSG #[a-zA-Z0-9_]+ :(.+)',
                                      data)[0]#.decode('utf8')
            }
        else:
            return None

    def twitch_receive_messages(self):
        """
        Call this function to process everything received by the socket
        This needs to be called frequently enough (~10s) Twitch logs off
        users not replying to ping commands.
        :return: list of chat messages received. Each message is a dict
            with the keys ['channel', 'username', 'message']
        """
        self._push_from_buffer()
        result = []
        while True:
            # process the complete buffer, until no data is left no more
            try:
                msg = self.s.recv(4096).decode()     # NON-BLOCKING RECEIVE!
            except socket.error as e:
                err = e.args[0]
                if err == errno.EAGAIN or err == errno.EWOULDBLOCK:
                    # There is no more data available to read
                    return result
                else:
                    # a "real" error occurred
                    # import traceback
                    # import sys
                    # print(traceback.format_exc())
                    # print("Trying to recover...")
                    self.connect()
                    return result
            else:
                if self.verbose:
                    print (msg)
                rec = [self._parse_message(line)
                       for line in filter(None, msg.split('\r\n'))]
                rec = [r for r in rec if r]     # remove Nones
                result.extend(rec)


class Interface(tk.Tk):
    def __init__(self):
        tk.Tk.__init__(self)
        self.credentialsFrame = tk.LabelFrame(self,text="Login Credentials",padx=3)
        self.channelFrame = tk.LabelFrame(self,text="Channel")
        self.optionsFrame = tk.LabelFrame(self,text="Spam Options",pady=6)
        self.settingsFrame = tk.LabelFrame(self,text="Settings")
        self.iconbitmap(self.resourcePath("TwitchChatBotIcon.ico"))
        self.menubar = tk.Menu(self,tearoff=0)
        self.menubar.add_command(label="Help",command = self.showHelp)
        self.menubar.add_command(label="Hotkeys", command=self.showHotkeys)
        self.config(menu=self.menubar)
        
        self.isInChannel = False
        self.wantsToReceive = False
        self.receiving = False
        self.STOP = False
        self.silencedUsers = ['nightbot']
        self.lastMessageTime = time.time()
        self.title("Twitch Chat Text-To-Speech")
        self.attributes('-topmost',1)
        self.lift()
        self.focus_force()
        OS = os.name
        if OS == 'nt': # Windows
            self.isWindows = True
        else:
            self.isWindows = False
            
        self.PASS = ""
        self.NICK = ""
        
        # Credentials Frame
        self.NICKLabel = tk.Label(self.credentialsFrame,text="Username")
        self.NICKLabel.grid(row=0,column=0,columnspan=2)
        self.NICKEntry = tk.Entry(self.credentialsFrame,width=30)
        self.NICKEntry.grid(row=1,column=0,columnspan=2,padx=10,pady=5)

        self.PASSLabel = tk.Label(self.credentialsFrame,text="OAuth Code")
        self.PASSLabel.grid(row=0,column=2)
        self.PASSEntry = tk.Entry(self.credentialsFrame,width=30)
        self.PASSEntry.grid(row=1,column=2,padx=5,pady=5)
                
        self.NICKEntry.insert(0,"UserNameHere")
        self.PASSEntry.insert(0,"oauth:exampleabcdefg12345677")
        #self.NICKEntry.insert(0,"ImABotBoy")
        #self.PASSEntry.insert(0,"oauth:1ruvijtcfg81i6d0b44j5ct76mrhyo")
        
        self.connectButton = tk.Button(self.credentialsFrame,text="Connect to Twitch", command=self.connect,padx=38)
        self.connectButton.grid(row=2,column=2,padx=7,pady=5)

        # Channel Frame        
        self.JOINLabel = tk.Label(self.channelFrame,text="Channel Name")
        self.JOINLabel.grid(row=0,column=0,columnspan=2,padx=5,pady=5)
        self.JOINEntry = tk.Entry(self.channelFrame)
        self.JOINEntry.grid(row=1,column=0,columnspan=2,padx=5,pady=5)
        self.JOINEntry.insert(0,"tsm_dyrus")
        
        self.joinButton = tk.Button(self.channelFrame,text="Join Channel",command = self.join,padx=55)
        self.joinButton.grid(row=2,column=0,columnspan=2,pady=5,padx=5)
        self.joinButton.config(state='disabled')

        
        self.receiveMessagesButton = tk.Button(self.channelFrame,text="Read Chat!",command=self.receiveMessages,padx=60)
        self.receiveMessagesButton.grid(row=3,column=0,columnspan=2,pady=5,padx=5)
        self.attributes('-topmost',0)
        
        self.stopButton = tk.Button(self.channelFrame,text="Stop Reading", command = self.stop,padx=54)
        self.stopButton.grid(row=4,column=0,columnspan=2,padx=5,pady=5)
        
        self.filterAt = tk.IntVar()
        self.filterAtButton = tk.Checkbutton(self.settingsFrame,text="Filter Messages by @",variable = self.filterAt)
        self.filterAtButton.grid(row=20,column=0,columnspan=2,padx=5,pady=0)
        

        self.chatterLabel = tk.Label(self.optionsFrame,text="Mute User")
        self.chatterLabel.grid(row=0,column=0,padx=5,pady=5)
        self.chatterEntry = tk.Entry(self.optionsFrame)
        self.chatterEntry.grid(row=1,column=0,columnspan=2,padx=5,pady=5)
        
        self.checkBannedButton = tk.Button(self.optionsFrame,text="Bad Boys",command=self.checkBannedUsers,padx=18)
        self.checkBannedButton.grid(row=0,column=1,padx=5)#,pady=5)
        
        self.silenceChatterButton = tk.Button(self.optionsFrame,text="Mute",command = self.silenceUser,padx=23)
        self.silenceChatterButton.grid(row=2,column=0,padx=5,pady=5)
        self.unsilenceChatterButton = tk.Button(self.optionsFrame,text="Un-Mute", command=self.unsilenceUser,padx=18)
        self.unsilenceChatterButton.grid(row=2,column=1,padx=5,pady=5)
    
        self.maxLengthLabel = tk.Label(self.optionsFrame,text="Message Character Limit")
        self.maxLengthLabel.grid(row=3,column=0,columnspan=2,padx=5,pady=5)
        self.maxLengthEntry = tk.Entry(self.optionsFrame)
        self.maxLengthEntry.grid(row=4,column=0,columnspan=2,padx=5,pady=5)
        self.maxLengthEntry.insert(0,"100")

        self.autoMessageLabel = tk.Label(self.settingsFrame,text="Auto Message Interval")
        self.autoMessageLabel.grid(row=0,column=0,columnspan=2,padx=5,pady=5)
        self.autoMessageEntry = tk.Entry(self.settingsFrame,width=10)
        self.autoMessageEntry.insert(0,'100000')
        self.autoMessageEntry.grid(row=1,column=0,sticky='e',padx=5,pady=5)
        self.autoMessageUnitsLabel = tk.Label(self.settingsFrame,text="seconds")
        self.autoMessageUnitsLabel.grid(row=0,column=1,padx=5,pady=5)
        self.autoMessageEntryLabel = tk.Label(self,text="Auto Message").grid(row=0,column=2)
        self.autoMessageVar = tk.IntVar()
        self.autoMessageToggle = tk.Checkbutton(self,text="On",variable=self.autoMessageVar)
        self.autoMessageToggle.grid(row=0,column=3,sticky='sw')
        self.autoMessageEntryText = tk.Text(self,width=20,height=5,pady=5)
        self.autoMessageEntryText.insert(tk.END, "Chat in this channel is being aloud by a Text-To-Speech program 'TwitchChatBot'!")
        self.autoMessageEntryText.grid(row=1,column=2,columnspan=2,padx=5,sticky='s',pady=10)
        
        self.scaleLabel = tk.Label(self.settingsFrame, text="Speech Volume")
        self.scaleLabel.grid(row=2,column=0,columnspan=2,padx=5,pady=5)
        self.volumeScale = tk.Scale(self.settingsFrame,from_=0,to=100,orient='horizontal',length=150)
        self.volumeScale.grid(row=3,column=0,columnspan=2,padx=5,pady=4)
        self.volumeScale.set(50)
        
        # Grid Frames        
        self.credentialsFrame.grid(row=1,column=0,columnspan=2,padx=5,pady=5)
        self.channelFrame.grid(row=3,column=0,padx=5,pady=5,rowspan=2)
        self.optionsFrame.grid(row=3,column=1,padx=5,pady=5)
        self.settingsFrame.grid(row=3,column=2,columnspan=2,padx=5,pady=5)
        self.closeButton = tk.Button(self,text="Close Program",command = self.totalDestroy)
        self.closeButton.grid(row=6,column=3,sticky='e',pady=5,padx=5)
        self.addButtons()
        self.disableButtons()

    def addButtons(self):
        self.allButtons = []
        self.allButtons.append(self.receiveMessagesButton)   
        self.allButtons.append(self.stopButton)
        self.allButtons.append(self.filterAtButton)
        self.allButtons.append(self.checkBannedButton)
        self.allButtons.append(self.silenceChatterButton)
        self.allButtons.append(self.unsilenceChatterButton)
        
    def showHelp(self):
        top = tk.Toplevel(self)
        helpMessage  = "1. Obtain an 'OAuth' code from https://twitchapps.com/tmi/ to use along with your Twitch username.\n\n"
        helpMessage += "2. Connect to a channel once logged into Twitch and interact with messages via the buttons in the 'Channel' section.\n\n"
        helpMessage += "3. Muting users will make it so their messages are ignored. A list of muted users can be seen with the 'Bad Boys' button.\n\n"
        helpMessage += "3. Turning on the '@ filter' will make it so that only messages which contain the phrase '@ChannelNameHere' are read.\n\n"
        helpMessage += "5. The bot will periodically send messages to the channel containing information on how the chat user's can interact with it.\n\n"
        helpMessage += "6. Streamers can start/stop reading messages while in a game by using the associated hotkeys (see the hotkeys tab).\n\n"
        topLabel = tk.Label(top,text=helpMessage)
        topLabel.pack()
        
    def showHotkeys(self):
        top = tk.Toplevel(self)
        topLabel = tk.Label(top,text="CTRL-SHIFT-R to read messages.\nCTRL-SHIFT-S to stop reading.\nCTRL-SHIFT-F to toggle the @Filter.\nCTRL-SHIFT-E to raise volume by 10.\nCTRL-SHIFT-D to lower volume by 10.")
        topLabel.pack()
        top.geometry('{}x{}'.format(320,100))
        
    def checkBannedUsers(self):      
        top = tk.Toplevel(self)
        listBox = tk.Listbox(top)
        label = tk.Label(top,text="Use mouse wheel to scroll")
        label.pack()
        for user in self.silencedUsers:
            listBox.insert('end',user)
        listBox.pack()
            
    def silenceUser(self):
        user = self.chatterEntry.get()
        if user not in self.silencedUsers:
            self.silencedUsers.append(user)
        self.chatterEntry.delete(0,'end')
        
    def unsilenceUser(self):
        user = self.chatterEntry.get().lower()
        if user in self.silencedUsers:
            self.silencedUsers.remove(user)
        self.chatterEntry.delete(0,'end')
        
    def connect(self):
        self.NICK = self.NICKEntry.get()
        self.PASS = self.PASSEntry.get()
        if not self.PASS.startswith('oauth:'):
            self.PASS = 'oauth:'+self.PASS
        self.main = TwitchChatStream(self.NICK,self.PASS,verbose=False)
        #self.main = TwitchChatStream(self.NICK,self.PASS,verbose=True)
        self.main.connect()
        if self.main.connected:
            self.connectButton.config(bg="green")
            self.joinButton.config(state='normal')
            self.checkIfWantsToReceive()
            print("Connected")
        else:
            self.connectButton.config(bg="red")
            print("Connection failed")
            
    def join(self):
        self.joinButton.configure(bg="red")
        channel = self.JOINEntry.get().lower()
        self.main.join_channel(channel)
        #self.main.twitch_receive_messages()
        self.old_channel = self.main.current_channel
        time.sleep(1)
        self.main.twitch_receive_messages()
        print("-----------------")
        print("I was in: " + self.old_channel)
        print("I'm in channel: " + self.main.current_channel)
        print("-----------------")      
        if self.old_channel == self.main.current_channel:
            # Didn't actually join channel
            self.joinButton.configure(bg="red")
            self.disableButtons()
            print("I'm in channel: " + self.main.current_channel)
            
        else:
            # Successfully joined channel
            self.joinButton.configure(bg="green")
            self.enableButtons()
            self.isInChannel = True
        print("I'm in channel: " + self.main.current_channel)

                
    def resourcePath(self,filename):
        try:
            # PyInstaller creates a temp folder and stores path in _MEIPASS
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, filename)

    def TTS(self,message):
        if self.isWindows and not self.STOP:
            voice = self.resourcePath("voice.exe")
            subprocess.call(voice + " -v " + str(int(self.volumeScale.get())) + " " + message,shell=True)
        if not self.isWindows and not self.STOP:
            os.system("say " + message)
            
    def receiveMessages(self):
        print("Receiving: ", self.receiving)
        self.STOP = False
        if not self.receiving and self.isInChannel:
            self.recThread = threading.Thread(target=self.receive)
            self.recThread.start()
            self.receiveMessagesButton.config(bg="green")
            print("After started thread and color changed to green")
        
    def stop(self):
        if self.isInChannel:
            try:            
                print("Wanted to receive before stopping? --> ", self.wantsToReceive)
                self.STOP = True    
                self.receiving = False
                self.wantsToReceive = False
                del(self.recThread) 
                self.receiveMessagesButton.config(bg="red")
            except Exception as e:
                print("GOT AN ERROR IN STOP: ", e)
                pass
        
    def totalDestroy(self):
        self.stop()
        self.destroy()        
        try:
            self.main.s.close()
        except:
            pass
        
    def autoSend(self):
        try:
            autoMessageInterval = float(self.autoMessageEntry.get()) # float
        except:
            autoMessageInterval = 120.
        if autoMessageInterval < 60.:
            self.autoMessageEntry.delete(0,'end')
            self.autoMessageEntry.insert(0,'60')
            autoMessageInterval = 60.
        self.autoMessage = self.autoMessageEntryText.get('1.0',tk.END)#"BOOGA"#Include @" + self.main.current_channel + " to have your message read aloud to " + self.main.current_channel + "!"
        currentTime = time.time()
        timePassed = currentTime - self.lastMessageTime
        autoMessageOn = self.autoMessageVar.get()
        if timePassed > autoMessageInterval and autoMessageOn:
            print("I'm sending a message")
            self.main.send_chat_message(self.main.current_channel,self.autoMessage)
            time.sleep(1)
            self.lastMessageTime = currentTime
            self.main.twitch_receive_messages()
            
    def checkIfWantsToReceive(self):
        if self.wantsToReceive and not self.receiving:
            print("USER HOTKEYED RECEIVED")
            self.receiveMessages()
        self.after(1000,self.checkIfWantsToReceive) # Call this function repeatedly every 1000 milliseconds
            
    def OnKeyboardEvent(self,event):
        pressedShift = pyHook.GetKeyState(pyHook.HookConstants.VKeyToID('VK_LSHIFT')) or  pyHook.GetKeyState(pyHook.HookConstants.VKeyToID('VK_RSHIFT'))
        pressedCtrl = pyHook.GetKeyState(pyHook.HookConstants.VKeyToID('VK_CONTROL'))
        print(pyHook.HookConstants.IDToName(event.KeyID))
        if pressedShift and pressedCtrl:
            pressedKey = pyHook.HookConstants.IDToName(event.KeyID) # Letter that user pressed
            if pressedKey == 'R':
                time.sleep(.2)
                print("Receive")
                self.wantsToReceive = True
            elif pressedKey == 'S':
                print("Stop")
                self.stop()
            elif pressedKey == 'F':
                print("Toggle filter")
                self.filterAt.set(abs(1 - self.filterAt.get())) # Swaps 0 with 1, 1 with 0
            elif pressedKey == 'D':
                loweredVolume = self.volumeScale.get() - 10
                if loweredVolume < 0:
                    loweredVolume = 0
                self.volumeScale.set(loweredVolume)
            elif pressedKey == 'E':
                raisedVolume = self.volumeScale.get() + 10
                if raisedVolume > 100:
                    raisedVolume = 100
                self.volumeScale.set(raisedVolume)

        return True
        


    def receive(self):
        print("IN RECEIVE FUNC")
        self.receiving = True
        
        if self.STOP:
            print ("self.stop is True")
            return
        
        
        
        
        while not self.STOP:
            self.autoSend()
            self.maxLength = int(self.maxLengthEntry.get())
            #print(self.filterAt.get())
            rec = self.main.twitch_receive_messages()        
            if rec and not self.STOP:
                for message_info in rec:
                    if message_info['channel'] == "#"+self.main.current_channel:
                        if self.STOP:
                            return  
                        user = message_info['username'].lower()
                        message = message_info['message']
                        fullMessage = user + " said: " + message
                        if (self.filterAt.get() == 1 and ("@"+self.main.current_channel in message.lower()) ) or self.filterAt.get() == 0:                            
                            if user not in self.silencedUsers and len(message) < self.maxLength:
                                fullMessage.replace("@","")
                                self.TTS(fullMessage)
                                print(user + " length: " + str(len(message)))
        
            time.sleep(.2)      

        self.STOP = False
                
    def enableButtons(self):
        for button in self.allButtons:
            button.config(state='normal')
    def disableButtons(self):
        for button in self.allButtons:
            button.config(state='disabled')
   
# ---------------------------------- #
# ---------- Run Program ----------- #


gui = Interface()

hm = pyHook.HookManager()    
hm.KeyDown = gui.OnKeyboardEvent
hm.HookKeyboard()
# set the hook
gui.mainloop()

