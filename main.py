#!/usr/bin/env python3
import click
import sys
import threading
import select
import pty
import os
import re
import requests
import time
import logging
from matrix_client.client import MatrixClient


logger = logging.getLogger('shellbot')
logging.basicConfig(stream=sys.stdout, level=logging.INFO,
                    format="%(asctime)s:%(name)s:%(levelname)s:%(message)s")
escape_parser = re.compile(r'\x1b\[?([\d;]*)(\w)')


def remove_escape_codes(shell_out):
    start = 0
    escapes = re.finditer(escape_parser, shell_out)
    html = []
    for match in escapes:
        html.append(shell_out[start:match.start()].replace('\r', ''))
        start = match.end()
    html.append(shell_out[start:])
    return ''.join(html)


def on_event(event, pin, allowed_users):
    """
    If event is a text message event by an authorized user, this function
    writes its contents to the shell.

    event: matrix event dict
    pin: file object for pty master
    allowed_users: users authorized to send input to the shell

    A newline is appended to the text contents when written, so a one-line
    message may be interpreted as a command.

    Special cases: !ctrlc sends a sequence as if the user typed ctrl+c.
    """
    if event['type'] == 'm.room.message' and (
            event['sender'] in allowed_users and
            'msgtype' in event['content'] and
            event['content']['msgtype'] == 'm.text'):
        message = str(event['content']['body'])
        if message == '!ctrlc':
            logger.info('sending ctrl+c')
            pin.write('\x03')
            pin.flush()
        else:
            logger.info('shell stdin: {}'.format(message))
            pin.write(message)
            pin.write('\n')
            pin.flush()


def shell_stdout_handler(master, client, stop):
    """
    Reads output from the shell process until there's a 0.1s+ period of no
    output. Then, sends it as a message to all allowed matrix rooms.

    master: master pipe for the pty. gives us read/write with the shell.
    client: matrix client
    stop: threading.Event that activates when the bot shuts down

    This function exits when stop is set.
    """
    buf = []
    while not stop.is_set():
        ready = select.select([master], [], [], 0.1)[0]
        if ready:
            buf.append(os.read(master, 1024))
            if buf[-1] == '':
                return
        elif buf and client.rooms:
            shell_out = b''.join(buf).decode('utf8')
            logger.info('shell stdout: {}'.format(shell_out))
            text = remove_escape_codes(shell_out)
            html = '<pre><code>' + text + '</code></pre>'
            for room in client.rooms.values():
                room.send_html(html, body=text)
            buf.clear()


@click.command()
@click.option('--homeserver', default='https://matrix.org',
              help='matrix homeserver url')
@click.option('--authorize', default=['@matthew:vgd.me'], multiple=True,
              help='authorize user to issue commands '
              '& invite the bot to rooms')
@click.argument('username')
@click.argument('password')
def run_bot(homeserver, authorize, username, password):
    allowed_users = authorize
    shell_env = os.environ.copy()
    shell_env['TERM'] = 'vt100'
    child_pid, master = pty.fork()
    if child_pid == 0:  # we are the child
        os.execlpe('sh', 'sh', shell_env)
    pin = os.fdopen(master, 'w')
    stop = threading.Event()

    client = MatrixClient(homeserver)
    client.login_with_password_no_sync(username, password)
    client.listen_for_events()  # get rid of initial event sync
    client.add_listener(lambda event: on_event(event, pin, allowed_users))

    shell_stdout_handler_thread = threading.Thread(
        target=shell_stdout_handler, args=(master, client, stop))
    shell_stdout_handler_thread.start()

    while True:
        try:
            client.listen_forever()
        except KeyboardInterrupt:
            stop.set()
            sys.exit(0)
        except requests.exceptions.Timeout:
            logger.warn("disconnected. Trying again in 5s...")
            time.sleep(5)
        except requests.exceptions.ConnectionError:
            logger.warn("disconnected. Trying again in 5s...")
            time.sleep(5)


if __name__ == "__main__":
    run_bot(auto_envvar_prefix='SHELLBOT')
