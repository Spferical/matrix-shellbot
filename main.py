#!/usr/bin/env python3
import click
import sys
import threading
import select
import pty
import os
from matrix_client.client import MatrixClient


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
    alive = True

    def on_event(event):
        if event['type'] == 'm.room.message' and (
                event['sender'] in allowed_users and
                'msgtype' in event['content'] and
                event['content']['msgtype'] == 'm.text'):
            message = str(event['content']['body'])
            if message == '!ctrlc':
                print('sending ctrl+c')
                pin.write('\x03')
                pin.flush()
            else:
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
                buf.append(os.read(master, 1024))
                print('shell stdout: {}'.format(buf[-1]))
                if buf[-1] == '':
                    return
            elif buf and client.rooms:
                text = b''.join(buf).decode('utf8')
                html = '<pre><code>' + text + '</code></pre>'
                for room in client.rooms.values():
                    room.send_html(html, body=text)
                buf.clear()

    client = MatrixClient(homeserver)
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
