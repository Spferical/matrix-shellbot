#!/usr/bin/env python3
import click
import subprocess
import sys
import threading
import select
import pty
import os
import signal
from subprocess import PIPE
from queue import Queue
from matrix_client.client import MatrixClient
from matrix_client.api import MatrixRequestError


@click.command()
@click.option('--url', default='https://matrix.org', help='homeserver url')
@click.argument('username')
@click.argument('password')
def run_bot(url, username, password):
    allowed_room_ids = []
    master, slave = pty.openpty()
    shell_proc = subprocess.Popen(['sh'],
                                  stdin=slave, stdout=slave, stderr=slave,
                                  universal_newlines=True)
    pin = os.fdopen(master, 'w')
    alive = True

    def on_event(event):
        if (event['type'] == 'm.room.message'
            and event['sender'] != client.user_id
            and 'msgtype' in event['content']
            and event['content']['msgtype'] == 'm.text'
            and event['room_id'] in allowed_room_ids):

            message = str(event['content']['body'])
            print('shell stdin: {}'.format(message))
            pin.write(message)
            pin.write('\n')
            pin.flush()

    def shell_stdout_handler():
        """
        Reads output from the shell process until there's a 0.1s+ period of no
        output. Then, sends it as a message to all allowed matrix rooms.
        """
        buf = []
        while alive:
            ready = select.select([master], [], [], 0.1)[0]
            if ready:
                buf.append(os.read(master, 1024).decode('utf8'))
                print('shell stdout: {}'.format(buf[-1]))
                if buf[-1] == '':
                    print('empty output, returning')
                    return
            elif buf and client.rooms:
                text = ''.join(buf)
                for (room_id, room) in client.rooms.items():
                    if room_id in allowed_room_ids:
                        room.send_text(text)
                buf = []

    client = MatrixClient(url)
    client.login_with_password_no_sync(username, password)
    client.listen_for_events()  # get rid of initial event sync
    client.add_listener(on_event)
    shell_stdout_handler_thread = threading.Thread(target=shell_stdout_handler)
    shell_stdout_handler_thread.start()
    try:
        client.listen_forever()
    except KeyboardInterrupt:
        alive = False
        sys.exit(0)

if __name__ == "__main__":
    run_bot(auto_envvar_prefix='SHELLBOT')
