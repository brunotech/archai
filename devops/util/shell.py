# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.
import subprocess
from threading import Thread, Lock


class Shell:
    def __init__(self):
        self.output = ''
        self.lock = Lock()
        self.verbose = False

    def run(self, cwd, command, print_output=True):
        self.output = ''
        self.verbose = print_output
        with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0,
                                  universal_newlines=True, cwd=cwd, shell=True) as proc:

            stdout_thread = Thread(target=self.logstream, args=(proc.stdout,))
            stderr_thread = Thread(target=self.logstream, args=(proc.stderr,))

            stdout_thread.start()
            stderr_thread.start()

            while stdout_thread.isAlive() or stderr_thread.isAlive():
                pass

            proc.wait()

            if proc.returncode:
                words = command.split(' ')
                print(f"### command {words[0]} failed with error code {proc.returncode}")
                raise Exception(self.output)
            return self.output

    def logstream(self, stream):
        try:
            while True:
                if out := stream.readline():
                    self.log(out)
                else:
                    break
        except Exception as ex:
            msg = f"### Exception: {ex}"
            self.log(msg)

    def log(self, msg):
        self.lock.acquire()
        try:
            msg = msg.rstrip('\r\n')
            self.output += msg + '\r\n'
            if self.verbose:
                print(msg)
        finally:
            self.lock.release()
