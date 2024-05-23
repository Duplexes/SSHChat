import asyncio
import asyncssh
import sys
from typing import List, cast


class MySSHServer(asyncssh.SSHServer):
    def password_auth_supported(self):
        return True

    def validate_password(self, username, password):
        return username == 'public' and password == 'password'


class ChatClient:
    _clients: List['ChatClient'] = []

    def __init__(self, process: asyncssh.SSHServerProcess):
        self._process = process
        self._name = None

    @classmethod
    async def handle_client(cls, process: asyncssh.SSHServerProcess):
        client = cls(process)
        await client.run()

    async def readline(self) -> str:
        return cast(str, await self._process.stdin.readline())

    def write(self, msg: str) -> None:
        self._process.stdout.write(msg)

    def broadcast(self, msg: str, exclude_self: bool = True) -> None:
        for client in self._clients:
            if not exclude_self or client != self:
                client.send_message_with_prompt_restore(msg)

    async def run(self) -> None:
        self.write('Welcome to chat!\n\n')
        self.write('Enter your name: ')
        self._name = (await self.readline()).rstrip('\n')

        self.write(f'\n{len(self._clients)} other users are connected.\n\n')

        self._clients.append(self)
        self.broadcast(f'*** {self._name} has entered chat ***\n')

        self.write_prompt()

        try:
            async for line in self._process.stdin:
                line = line.rstrip('\n')
                if line.startswith('/'):
                    await self.handle_command(line)
                else:
                    self.broadcast(f'{self._name}: {line}\n')
                    self.write_prompt()  # Show the prompt after broadcasting the message we hope maybe
        except (asyncssh.BreakReceived, asyncio.CancelledError):
            pass
        finally:
            self._clients.remove(self)
            self.broadcast(f'*** {self._name} has left chat ***\n')

    async def handle_command(self, command: str) -> None:
        if command == '/list':
            self.list_users()
        elif command == '/exit':
            await self.exit_chat()
        elif command == '/help':
            self.write('Available commands:\n')
            self.write('  /list - List connected users\n')
            self.write('  /exit - Exit chat\n')
            self.write('  /help - Show this help message\n')
            self.write_prompt()
        else:
            self.write(f'Unknown command: {command}\n')
            self.write_prompt()

    def list_users(self) -> None:
        user_list = ', '.join(client._name for client in self._clients if client._name)
        self.write(f'Connected users: {user_list}\n')
        self.write_prompt()

    async def exit_chat(self) -> None:
        self.write('Goodbye!\n')
        self._process.stdin.write_eof()

    def write_prompt(self) -> None:
        self.write(f'{self._name}: ')

    def send_message_with_prompt_restore(self, msg: str) -> None:
        current_input = self._process.stdin._buffer if hasattr(self._process.stdin, '_buffer') else ''
        self.write(f'\033[2K\r{msg}')
        self.write_prompt()
        self._process.stdout.write(current_input)


async def start_server() -> None:
    print('Starting server on port 8022')
    await asyncssh.create_server(
        MySSHServer, '', 8022, server_host_keys=['ssh_host_key'],
        process_factory=ChatClient.handle_client
    )


loop = asyncio.get_event_loop()

try:
    loop.run_until_complete(start_server())
except (OSError, asyncssh.Error) as exc:
    sys.exit(f'Error starting server: {exc}')

loop.run_forever()
