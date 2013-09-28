from subprocess import Popen, PIPE
from threading import Thread
from blessings import Terminal
import argparse
import termios
import sys
import tty
from time import time


DEFAULT_ARGS = {'steam_dir': '/usr/games/steam',
                'steamcmd_script': '/usr/games/steam/runscript_tf2.sh',
                'console': None,
                'game': 'tf',
                'maxplayers': '18',
                'autoupdate': None}


class tf2_daemon():
    '''Wrapper for the TF2 Linux Server.  Allows a user to interact with a
    running server instance (via stdin/stdio pipes) from Python.'''
    def __init__(self, run_time=5400, **kwargs):
        '''Sets up a Daemon to run for run_time seconds.  Set time to -1 to
        run indefinitely.'''
        self.args = ['/usr/games/tf2_server/srcds_run']
        for key, value in DEFAULT_ARGS:
            try:
                value = kwargs[key]
            finally:
                if value:
                    self.args.extend((key, value))
                else:
                    self.args.append(key)
        self.run_time = run_time
        self.starttime = None
        self.server = None

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


class Sandvich():
    def __init__(self):
        self.term = Terminal()
        self.kh = KeyHandler()
        self.tf2d = tf2daemon()
        #TODO write a formatter class to replace this array
        self.output = []
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
        while len(self.flags[]):
            flag = self.flags.pop(0)
            if flag == self.REDRAW_OUTPUT:
                for index in len(self.output):
                    with term.location(0, index):
                        print self.output[index]
            elif flag == self.REDRAW_CMDLINE:
                with term.location(0, term.height - 1):
                    print ' '.join([self.COMMAND_PROMPT, self.command_stub])

    def teardown(self):
        self.kh.stop()
        self.term.exit_fullscreen()


if __name__ == '__main__':
    s = Sandvich()
    s.run()
