from subprocess import Popen, PIPE
from threading import Thread
from blessings import Terminal
from time import time
import argparse
import termios
import sys
import tty
import re
import json


with open('config.json') as config:
    DEFAULT_ARGS = json.loads(config.read())


class TF2Daemon():
    '''Wrapper for the TF2 Linux Server.  Allows a user to interact with a
    running server instance (via stdin/stdio pipes) from Python.'''
    def __init__(self, run_time=5400, **kwargs):
        '''Sets up a Daemon to run for run_time seconds.  Set time to -1 to
        run indefinitely.'''
        self.args = ['/usr/games/tf2_server/srcds_run']
        for key, value in DEFAULT_ARGS.items():
            if key in kwargs:
                value = kwargs[key]
            if value:
                self.args.extend((key, value))
            else:
                self.args.append(key)
        self.run_time = run_time
        self.starttime = None
        self.server = None

    def set_run_time(self, time):
        self.run_time = time

    def run(self):
        '''Runs the TF2 daemon in it's own subprocess.'''
        self.server = Popen(self.args, shell=True, stdin=PIPE, stdout=PIPE)
        self.starttime = time()

    def communicate(self, command=""):
        '''Sends data to the process via stdin and retrieves via stdio.'''
        running = self.server.poll()
        if running:
            if self.run_time > 0 and time() - self.starttime < self.run_time:
                if msg:
                    self.server.stdin.write(command)
                output = self.server.stdout.readlines()
            else:
                self.server.terminate()
                running = False
                output = "Server Terminated - Timeout"
                self.server = None
        else:
            output = "Server Quit Unexpectedly!"
            self.server = None
        return (running, output)


class KeyHandler():
    '''A class to grab/handle user input via keyboard.  Allows for :vim-style
    and command-character (e.g. ctrl+[char], [spacebar]) commands.'''
    def __init__(self):
        '''Sets initial state for this instance.'''
        self.NORMAL_MODE = 0
        self.INPUT_MODE = 1
        self.COMMAND_MODE = 2

        self.COMMAND_CHARS = ""

        self.mode = self.NORMAL_MODE
        self.buf = ""
        self.command_queue = []

        self.running = False

    def getch(self):
        '''Captures a single character from stdin via termios, with no echo
        to stdout.  NOTE: do not run this directly.  It will block the app,
        waiting on user input.'''
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(sys.stdin.fileno())
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        return ch

    def read(self):
        return self.buf

    def flush(self):
        temp = self.buf
        self.buf = ""
        return temp

    def append(self, ch):
        self.buf = ''.join([self.buf, ch])

    def queue_command(self):
        self.command_queue.append(self.flush())

    def read_command(self):
        if len(self.command_queue):
            return self.command_queue.pop(0)
        else:
            return None

    def get_input_stub(self):
        '''Wrapper for read(), useful for previewing user-entered commands.'''
        if self.mode == self.INPUT_MODE:
            return self.read()
        else:
            return ""

    def update(self):
        '''Handles characters typed by the user, making relevant state
        changes if necessary, and appending well-formed commands to the
        command queue.'''
        ch = self.getch()
        self.append(ch)
        if ch is not None:
            if self.mode == self.NORMAL_MODE:
                if ch == ':':
                    self.flush()
                    self.mode == self.INPUT_MODE
                elif ch in self.COMMAND_CHARS:
                    self.mode = self.COMMAND_MODE
            elif self.mode == self.INPUT_MODE:
                if ch == "\r":
                    self.queue_command()
                    self.mode == self.NORMAL_MODE
                elif ch == "\x1b":
                    self.flush()
                    self.mode == self.NORMAL_MODE
            elif self.mode == self.COMMAND_MODE:
                command = self.command_complete(ch)
                if command:
                    self.queue_command()
                    self.mode == self.NORMAL_MODE
            else:
                raise ValueError("Not a valid input mode!")

    def command_complete(self, ch):
        self.append(ch)
        if self.read():
            return self.flush()
        else:
            return ""

    def run(self):
        '''Runs update functionality in its own thread, until stop()
        is called.'''
        self.running = True

        def update_loop(self):
            while self.running is True:
                self.update()

        t = Thread(target=update_loop, args=(self,))
        t.start()

    def stop(self):
        '''Stops the running keyhandler thread.'''
        self.running = False


class Formatter():
    '''Text formatter for steaming output displayed in a Blessings
    terminal.  Custom formatting can be added via regex-based rules, and
    verbosity levels from 1 (priority/unclassified messages only) to 5
    (most verbose) are supported.'''
    def __init__(self, terminal):
        self.messages = []
        self.t = terminal
        self.rules = {}
        self.verbosity = 3

    def set_verbosity(self, verbosity):
        self.verbosity = verbosity

    def add_rule(self, alias, regex, formats, priority=5):
        if isinstance(formats, string):
            formats = (formats,)
        self.rules[alias] = {'regex': re.compile(regex),
                                'format': ''.join(["self.t.%s" % rule
                                    for rule in formats]),
                                'priority': priority}

    def append(self, text):
        message = text.split(' ')
        rule = self.classify_message()
        if not rule or self.rules[rule]['priority'] <= self.verbosity:
            self.messages.append({'text': message,
                                    'rule': rule})
            while self.total_lines > self.t.height - 3:
                self.messages.pop(0)

    def classify_message(self, message):
        text = ' '.join(message)
        current_priority = 100
        matched_rule = None
        for alias, rule in self.rules.items():
            if rule['priority'] < current_priority:
                #Only replace a rule if a higher priority rule exists.
                match = rule['regex'].search(text)
                if match:
                    matched_rule = alias
                    current_priority = rule['prority']
        return matched_rule

    def format_message(self, message):
        lines = self.message_to_lines(message['text'], return_lines=True)
        try:
            lines = [''.join([self.get_format(message), line, self.t.normal])
                    for line in lines]
        finally:
			return lines

    def get_format(self, message):
        rule = self.rules[message['rule']]
        return rule['format']

    def message_to_lines(self, message, return_lines=False):
        lines = []
        current_line = ""
        cursor = [1, 1]
        for word in message:
            cursor[0] += len(word) + 1
            if cursor[0] < self.t.width:
                if return_lines:
                    current_line = ' '.join([current_line, word])
            else:
                if return_lines:
                    lines.append(current_line)
                    current_line = word
                cursor = [len(word) + 1, cursor[1] + 1]
        return (cursor[1], lines)

    def total_lines(self):
        messages = [message['text'] for message in self.messages]
        return sum([numlines for numlines, unused in
                    map(self.message_to_lines, messages)])

    def __repr__(self):
        output = []
        for message in self.messages:
            output.extend(self.format_message(message))
        return output


class Sandvich():
    '''Full terminal application for controlling the TF2 server console.'''
    def __init__(self):
        self.term = Terminal()
        self.kh = KeyHandler()
        self.tf2d = TF2Daemon()
        self.output = Formatter(self.term)
        self.command_stub = ""
        self.flags = []

        self.COMMAND_PROMPT = ":^) --> "
        self.REDRAW_OUPUT = 0
        self.REDRAW_CMDLINE = 1

    def run(self):
        '''Launches the threads which handle server I/O and terminal
        interaction.'''
        self.tf2d.run()
        self.kh.run()
        running = True
        self.term.enter_fullscreen()
        while running is True:
            running = self.update()
        self.teardown()

    def update(self):
        '''Triggers user interaction with server, and screen redraw.'''
        command = self.kh.read_command()
        running, output = self.tf2d.communicate(command)
        self.update_output(output)
        self.update_cmdline()
        self.redraw()
        return running

    def update_output(self, output):
        '''Updates console output and triggers a console redraw, if
        necessary.'''
        if output:
            self.output.append(output)
            self.flags.append(self.REDRAW_OUTPUT)

    def update_cmdline(self):
        '''Updates command box output and triggers a console redraw, if
        necessary.'''
        new_stub = self.kh.get_command_stub()
        if new_stub != self.command_stub:
            self.command_stub = new_stub
            self.flags.append(self.REDRAW_CMDLINE)

    def redraw(self):
        '''Performs per-flag redraws of visual elements.'''
        while len(self.flags):
            flag = self.flags.pop(0)
            if flag == self.REDRAW_OUTPUT:
                with self.term.location():
                    for line in self.output:
                        print line + self.term.move_down
            elif flag == self.REDRAW_CMDLINE:
                with term.location(0, term.height - 1):
                    print ' '.join([self.COMMAND_PROMPT, self.command_stub])

    def teardown(self):
        self.kh.stop()
        self.term.exit_fullscreen()

    def set_verbosity(self, verbosity):
        self.output.set_verbosity(int(verbosity))


if __name__ == '__main__':
    s = Sandvich()
    s.run()
