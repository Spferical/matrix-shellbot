#!/usr/bin/env python3
import click
import subprocess
from subprocess import PIPE
import sys
import threading


def print_stdout(stdout):
    while True:
        sys.stdout.write(stdout.read(1))
        sys.stdout.flush()


@click.command()
@click.option('--shell', default='sh', help='Shell to run')
def shell(shell):
    shell_proc = subprocess.Popen(['script', '-c', shell, '-q', '/dev/null'],
                                  stdin=PIPE, stdout=PIPE,
                                  universal_newlines=True)
    stdout_printer = threading.Thread(target=print_stdout,
                                      args=[shell_proc.stdout])
    stdout_printer.start()
    while True:
        cmdline = sys.stdin.readline()
        shell_proc.stdin.write(cmdline)
        shell_proc.stdin.flush()


if __name__ == "__main__":
    shell()
